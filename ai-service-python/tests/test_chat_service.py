import re
import unittest
from unittest.mock import patch

from schemas.requests import ChatRequest, SocraticSessionAnswerRequest, SocraticSessionStartRequest
from services.chat_service import answer_socratic_question, chat, start_socratic_session


class FakeRag:
    def __init__(self, results=None):
        self.results = results if results is not None else []
        self.retrieve_calls = []

    @staticmethod
    def normalize_id(pdf_id):
        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(pdf_id)).lower()

    def retrieve(self, query, top_k=5, filter_metadata=None):
        self.retrieve_calls.append({
            "query": query,
            "top_k": top_k,
            "filter_metadata": filter_metadata,
        })
        if callable(self.results):
            return self.results(query, top_k=top_k, filter_metadata=filter_metadata)
        return self.results


def _mock_chat_plan(
    *,
    intent="解释方法",
    needs_retrieval=True,
    queries=None,
    answer_style="concise",
    keywords=None,
):
    return {
        "original": "original question",
        "rewritten": (queries or [{"query": "rewritten academic query"}])[0]["query"],
        "keywords": keywords or ["method", "architecture"],
        "taskType": "chat",
        "source": "llm",
        "intent": intent,
        "needsRetrieval": needs_retrieval,
        "queries": queries or [{
            "query": "rewritten academic query",
            "scope": "current_paper",
            "reason": "优先检查当前论文。",
        }],
        "answerStyle": answer_style,
    }


class ChatServiceTests(unittest.TestCase):
    def test_chat_uses_current_pdf_rag_with_pdf_id(self):
        fake_rag = FakeRag(results=[{
            "text": "Current paper evidence about the method.",
            "metadata": {"id": "paper-1", "chunk_index": 2},
            "similarity": 0.9,
        }])
        query_plan = _mock_chat_plan(
            queries=[{
                "query": "rewritten academic query",
                "scope": "current_paper",
                "reason": "优先检查当前论文。",
            }],
        )

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_chat_query_plan", return_value=query_plan) as mocked_plan,
            patch("services.chat_service.retrieve_hybrid_results") as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="这篇论文的方法是什么？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["message"], "回答")
        self.assertEqual(response["queryPlan"]["intent"], "解释方法")
        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "current_paper")
        self.assertEqual(response["rag_sources"][0]["chunkIndex"], 2)
        self.assertEqual(fake_rag.retrieve_calls[0]["query"], "rewritten academic query")
        self.assertEqual(fake_rag.retrieve_calls[0]["filter_metadata"], {"id": "paper-1"})
        self.assertEqual(fake_rag.retrieve_calls[0]["top_k"], 12)
        mocked_plan.assert_called_once()
        mocked_hybrid.assert_not_called()

    def test_chat_adds_library_follow_up_only_when_current_paper_evidence_is_not_enough(self):
        fake_rag = FakeRag(results=[{
            "text": "论文在 benchmark 上做了实验。",
            "metadata": {"id": "paper-1", "chunk_index": 1},
            "similarity": 0.56,
        }])
        query_plan = _mock_chat_plan(
            intent="总结实验",
            answer_style="detailed",
            keywords=["实验", "结果", "指标"],
            queries=[
                {"query": "paper experiment results", "scope": "current_paper", "reason": "先查当前论文"},
                {"query": "benchmark result metrics", "scope": "library", "reason": "补充文献指标"},
            ],
        )
        hybrid_results = {
            "vector": [{"text": "对比结果使用准确率和 F1 指标。", "metadata": {"id": "lib-1"}, "similarity": 0.83}],
            "bm25": [],
        }

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_chat_query_plan", return_value=query_plan),
            patch("services.chat_service.retrieve_hybrid_results", return_value=hybrid_results) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="这篇论文的实验结果和指标是什么？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(len(fake_rag.retrieve_calls), 1)
        mocked_hybrid.assert_called_once_with("benchmark result metrics", top_k=5)
        self.assertEqual(response["queryPlan"]["queries"][1]["scope"], "library")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "current_paper")
        self.assertEqual(response["rag_sources"][1]["sourceType"], "library")
        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")

    def test_chat_without_pdf_id_uses_library_query_plan(self):
        query_plan = _mock_chat_plan(
            intent="背景补课",
            keywords=["RAG", "检索增强生成"],
            queries=[{
                "query": "what is rag retrieval augmented generation",
                "scope": "library",
                "reason": "查询文献库背景材料",
            }],
        )
        hybrid_results = {
            "vector": [{"text": "RAG 是检索增强生成，用检索结果辅助生成。", "metadata": {"id": "lib-1"}, "similarity": 0.9}],
            "bm25": [],
        }

        with (
            patch("services.chat_service.build_chat_query_plan", return_value=query_plan),
            patch("services.chat_service.retrieve_hybrid_results", return_value=hybrid_results) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="什么是 RAG？", history=[], paperSkeleton={}))

        self.assertEqual(response["rag_sources"][0]["sourceType"], "library")
        self.assertEqual(response["queryPlan"]["intent"], "背景补课")
        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")
        mocked_hybrid.assert_called_once_with("what is rag retrieval augmented generation", top_k=5)

    def test_chat_with_insufficient_evidence_retries_once_and_adds_boundary_instruction(self):
        fake_rag = FakeRag(results=[])
        query_plan = _mock_chat_plan(
            intent="总结实验",
            keywords=["实验", "结果", "指标"],
            queries=[{
                "query": "missing experiment evidence",
                "scope": "current_paper",
                "reason": "先查当前论文",
            }],
        )

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_chat_query_plan", return_value=query_plan),
            patch("services.chat_service.retrieve_hybrid_results", return_value={"vector": [], "bm25": []}) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "当前证据不足。"

            response = chat(ChatRequest(message="这篇论文有哪些实验结果？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(response["retrievalJudge"]["verdict"], "INCORRECT")
        self.assertEqual(len(response["rag_sources"]), 0)
        self.assertEqual(len(fake_rag.retrieve_calls), 1)
        self.assertEqual(mocked_hybrid.call_count, 1)
        final_prompt = mocked_get_llm.return_value._call.call_args[0][0]
        self.assertIn("当前论文或资料库证据不足", final_prompt)

    def test_chat_uses_recent_history_in_planner_context_without_forcing_retrieval(self):
        captured = {}
        query_plan = _mock_chat_plan(
            intent="自由问答",
            needs_retrieval=False,
            queries=[],
            answer_style="concise",
            keywords=["history"],
        )

        def fake_planner(message, context=None, task_type="chat", has_pdf=False):
            captured["message"] = message
            captured["context"] = context
            captured["task_type"] = task_type
            captured["has_pdf"] = has_pdf
            return query_plan

        history = [
            {"role": "user", "content": "前面先讲一下论文目标。"},
            {"role": "assistant", "content": "论文目标是提升检索稳定性。"},
            {"role": "user", "content": "那它的方法呢？"},
        ]
        paper_skeleton = {"abstract": "这篇论文关注检索增强生成。"}

        with (
            patch("services.chat_service.build_chat_query_plan", side_effect=fake_planner),
            patch("services.chat_service.get_rag") as mocked_get_rag,
            patch("services.chat_service.retrieve_hybrid_results") as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="继续总结一下。", pdfId="paper-1", history=history, paperSkeleton=paper_skeleton))

        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")
        self.assertEqual(response["rag_sources"], [])
        self.assertIn("Paper summary:", captured["context"])
        self.assertIn("Recent conversation:", captured["context"])
        self.assertIn("user: 那它的方法呢？", captured["context"])
        self.assertEqual(captured["task_type"], "chat")
        self.assertTrue(captured["has_pdf"])
        mocked_get_rag.assert_not_called()
        mocked_hybrid.assert_not_called()
        final_prompt = mocked_get_llm.return_value._call.call_args[0][0]
        self.assertIn("论文目标是提升检索稳定性", final_prompt)

    def test_start_socratic_session_uses_current_paper_evidence_for_first_question(self):
        fake_rag = FakeRag(results=[{
            "text": "论文主要想解决检索稳定性问题，并强调这个问题对整体回答质量的重要性。",
            "metadata": {"id": "paper-1", "chunk_index": 1},
            "similarity": 0.92,
        }])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = (
                '{"intro":"我们先从论文要解决的问题切入。","currentQuestion":"这篇论文具体想解决什么问题，它为什么重要？"}'
            )

            response = start_socratic_session(
                SocraticSessionStartRequest(
                    pdfId="paper-1",
                    paperSkeleton={"abstract": "论文关注检索稳定性。"},
                    readingProgress="我刚读完摘要。",
                )
            )

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["currentIndex"], 1)
        self.assertEqual(response["currentQuestion"], "这篇论文具体想解决什么问题，它为什么重要？")
        self.assertEqual(fake_rag.retrieve_calls[0]["filter_metadata"], {"id": "paper-1"})
        prompt = mocked_get_llm.return_value._call.call_args[0][0]
        self.assertIn("研究问题与价值", prompt)
        self.assertIn("论文主要想解决检索稳定性问题", prompt)
        self.assertNotIn("相关文献线索", prompt)

    def test_answer_socratic_question_returns_evidence_quality_and_follow_up_focus(self):
        fake_rag = FakeRag(results=[{
            "text": "作者的核心方法是双阶段检索框架，关键创新在于引入重排序模块，并强调它与已有基线的差异。",
            "metadata": {"id": "paper-1", "chunk_index": 2},
            "similarity": 0.9,
        }])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.side_effect = RuntimeError("LLM unavailable")

            response = answer_socratic_question(
                SocraticSessionAnswerRequest(
                    pdfId="paper-1",
                    paperSkeleton={"methods": "作者提出双阶段检索和重排序模块。"},
                    readingProgress="我正在阅读方法部分。",
                    currentIndex=2,
                    currentQuestion="作者提出的方法或模型核心思路是什么？它和已有做法相比，最关键的变化在哪里？",
                    userAnswer="作者提出了一个新的检索方法。",
                    turns=[
                        {
                            "index": 1,
                            "question": "第一题",
                            "answer": "回答 1",
                            "masteryLevel": "一般",
                            "feedback": "反馈 1",
                            "hint": "提示 1",
                        }
                    ],
                )
            )

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["isComplete"], False)
        self.assertEqual(response["nextIndex"], 3)
        self.assertIn("这篇论文的方法是如何一步步发挥作用的", response["nextQuestion"])
        self.assertIn("关键创新", response["nextQuestion"])
        self.assertEqual(response["evaluation"]["evidenceQuality"]["verdict"], "CORRECT")
        self.assertIn("核心方法", response["evaluation"]["coveredAspects"])
        self.assertIn("关键创新", response["evaluation"]["missingAspects"])
        self.assertIn("与已有方法差异", response["evaluation"]["missingAspects"])

    def test_answer_socratic_question_final_summary_returns_review_suggestions(self):
        fake_rag = FakeRag(results=[])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.side_effect = RuntimeError("LLM unavailable")

            response = answer_socratic_question(
                SocraticSessionAnswerRequest(
                    pdfId="paper-1",
                    paperSkeleton={
                        "abstract": "摘要",
                        "methods": "方法",
                        "results": "结果",
                        "discussion": "讨论",
                    },
                    readingProgress="我已经读完全文。",
                    currentIndex=5,
                    currentQuestion="如果你来继续这项研究，这篇论文还有哪些局限、风险或可以改进的地方？",
                    userAnswer="我觉得还有一些局限，但没有完全想清楚。",
                    turns=[
                        {
                            "index": 1,
                            "question": "第一题",
                            "answer": "回答 1",
                            "masteryLevel": "一般",
                            "feedback": "反馈 1",
                            "hint": "提示 1",
                            "missingAspects": ["研究价值"],
                            "evidenceQuality": {"verdict": "CORRECT", "confidence": 0.74, "reason": "证据足够。"},
                        },
                        {
                            "index": 2,
                            "question": "第二题",
                            "answer": "回答 2",
                            "masteryLevel": "需加强",
                            "feedback": "反馈 2",
                            "hint": "提示 2",
                            "missingAspects": ["关键创新"],
                            "evidenceQuality": {"verdict": "AMBIGUOUS", "confidence": 0.46, "reason": "证据不完整。"},
                        },
                        {
                            "index": 3,
                            "question": "第三题",
                            "answer": "回答 3",
                            "masteryLevel": "一般",
                            "feedback": "反馈 3",
                            "hint": "提示 3",
                        },
                        {
                            "index": 4,
                            "question": "第四题",
                            "answer": "回答 4",
                            "masteryLevel": "需加强",
                            "feedback": "反馈 4",
                            "hint": "提示 4",
                            "missingAspects": ["评价指标"],
                            "evidenceQuality": {"verdict": "INCORRECT", "confidence": 0.18, "reason": "没有检索到证据。"},
                        },
                    ],
                )
            )

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["isComplete"], True)
        self.assertEqual(response["evaluation"]["evidenceQuality"]["verdict"], "INCORRECT")
        self.assertLessEqual(len(response["reviewSuggestions"]), 3)
        self.assertTrue(all(item.startswith("建议回读") for item in response["reviewSuggestions"]))
        self.assertIn("证据不足", response["finalSummary"])
        self.assertIn("优先按以下方向回读", response["finalSummary"])


if __name__ == "__main__":
    unittest.main()
