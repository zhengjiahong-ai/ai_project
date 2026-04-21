import re
import unittest
from unittest.mock import patch

from schemas.requests import ChatRequest
from services.chat_service import chat


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


if __name__ == "__main__":
    unittest.main()
