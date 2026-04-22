import re
import unittest
from unittest.mock import Mock, patch

from schemas.requests import ResearchTaskCreateRequest
from services.research_task_service import (
    ResearchTaskNotFoundError,
    cancel_research_task,
    clear_research_tasks,
    create_research_task,
    get_research_task,
    run_research_task_now,
)


class FakeRag:
    def __init__(self, documents=None, retrieve_handler=None):
        self.documents = documents if documents is not None else []
        self.retrieve_handler = retrieve_handler or (lambda query, top_k=3, filter_metadata=None: [])
        self.retrieve_calls = []
        self.document_calls = []

    @staticmethod
    def normalize_id(pdf_id):
        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(pdf_id)).lower()

    def get_documents_by_metadata(self, filter_metadata=None, limit=200):
        self.document_calls.append({"filter_metadata": filter_metadata, "limit": limit})
        return self.documents[:limit]

    def retrieve(self, query, top_k=3, filter_metadata=None):
        self.retrieve_calls.append({
            "query": query,
            "top_k": top_k,
            "filter_metadata": filter_metadata,
        })
        return self.retrieve_handler(query, top_k=top_k, filter_metadata=filter_metadata)


class ResearchTaskServiceTests(unittest.TestCase):
    def setUp(self):
        clear_research_tasks()

    def tearDown(self):
        clear_research_tasks()

    def test_create_research_task_returns_deterministic_initial_snapshot(self):
        response = create_research_task(
            ResearchTaskCreateRequest(question="研究这个方法", pdfId="paper-1", paperSkeleton={"abstract": "summary"}),
            start_async=False,
        )

        task = response["task"]
        self.assertEqual(response["status"], "success")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["stage"], "planning")
        self.assertEqual(task["progress"], 0.0)
        self.assertEqual(task["question"], "研究这个方法")
        self.assertEqual(task["pdfId"], "paper-1")
        self.assertEqual(task["plan"], [])
        self.assertEqual(task["findings"], [])
        self.assertEqual(task["report"], "")
        self.assertEqual(task["error"], "")

    def test_research_task_succeeds_and_uses_current_paper_before_library(self):
        fake_rag = FakeRag(
            documents=[
                {"document": "当前论文介绍了研究目标和方法概览。", "metadata": {"id": "paper-1", "chunk_index": 0}},
            ],
            retrieve_handler=lambda query, top_k=3, filter_metadata=None: [
                {
                    "text": "当前论文提到了 benchmark，但没有给出完整指标。",
                    "metadata": {"id": "paper-1", "chunk_index": 1},
                    "similarity": 0.56,
                }
            ],
        )
        planner_llm = Mock()
        planner_llm._call.return_value = (
            '{"brief":"围绕问题做研究。","subQuestions":["实验支撑是否充分？","方法证据是什么？","结论边界在哪里？"]}'
        )

        def fake_query_plan(question, context=None, task_type="research"):
            return {
                "original": question,
                "rewritten": question,
                "keywords": ["benchmark", "metric"],
                "taskType": task_type,
                "source": "fallback",
            }

        with (
            patch("services.research_task_service.get_rag", return_value=fake_rag),
            patch("services.research_task_service.get_llm", return_value=planner_llm),
            patch("services.research_task_service.build_retrieval_queries", side_effect=fake_query_plan),
            patch(
                "services.research_task_service.retrieve_hybrid_results",
                return_value={
                    "vector": [
                        {
                            "text": "内部文献库给出了 benchmark 的 metric、accuracy 和 F1 结果。",
                            "metadata": {"id": "lib-1", "chunk_index": 2},
                            "similarity": 0.83,
                        }
                    ],
                    "bm25": [],
                },
            ) as mocked_hybrid,
        ):
            created = create_research_task(
                ResearchTaskCreateRequest(question="这篇论文的实验是否可靠？", pdfId="paper-1"),
                start_async=False,
            )
            task_id = created["task"]["taskId"]
            run_research_task_now(task_id)
            task = get_research_task(task_id)["task"]

        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["stage"], "done")
        self.assertEqual(task["progress"], 1.0)
        self.assertEqual(len(task["plan"]), 3)
        self.assertEqual(len(task["findings"]), 3)
        self.assertIn("## 研究 brief", task["report"])
        self.assertTrue(any(call["filter_metadata"] == {"id": "paper-1"} for call in fake_rag.retrieve_calls))
        self.assertGreaterEqual(mocked_hybrid.call_count, 1)
        self.assertTrue(any(item["sourceIds"] for item in task["findings"]))

    def test_research_task_retries_only_once_with_missing_aspects(self):
        fake_rag = FakeRag(
            documents=[
                {"document": "当前论文关注实验设计。", "metadata": {"id": "paper-1", "chunk_index": 0}},
            ],
            retrieve_handler=lambda query, top_k=3, filter_metadata=None: (
                [
                    {
                        "text": "retry evidence with metric and ablation details.",
                        "metadata": {"id": "paper-1", "chunk_index": 4},
                        "similarity": 0.88,
                    }
                ]
                if "missing-metric" in query
                else []
            ),
        )
        planner_llm = Mock()
        planner_llm._call.return_value = '{"brief":"brief","subQuestions":["实验指标是否充分？","第二问","第三问"]}'

        def fake_query_plan(question, context=None, task_type="research"):
            return {
                "original": "baseline query",
                "rewritten": "baseline query",
                "keywords": ["missing-metric"],
                "taskType": task_type,
                "source": "fallback",
            }

        with (
            patch("services.research_task_service.get_rag", return_value=fake_rag),
            patch("services.research_task_service.get_llm", return_value=planner_llm),
            patch("services.research_task_service.build_retrieval_queries", side_effect=fake_query_plan),
            patch("services.research_task_service.retrieve_hybrid_results", return_value={"vector": [], "bm25": []}),
        ):
            created = create_research_task(
                ResearchTaskCreateRequest(question="实验指标是否充分？", pdfId="paper-1"),
                start_async=False,
            )
            task_id = created["task"]["taskId"]
            run_research_task_now(task_id)
            task = get_research_task(task_id)["task"]

        self.assertEqual(task["status"], "succeeded")
        self.assertGreaterEqual(len(fake_rag.retrieve_calls), 2)
        self.assertTrue(any("missing-metric" in call["query"] for call in fake_rag.retrieve_calls[1:]))
        self.assertIn(task["findings"][0]["verdict"], {"CORRECT", "AMBIGUOUS"})

    def test_cancelled_task_is_not_overwritten_by_later_execution(self):
        fake_rag = FakeRag(
            documents=[
                {"document": "当前论文内容。", "metadata": {"id": "paper-1", "chunk_index": 0}},
            ],
            retrieve_handler=lambda query, top_k=3, filter_metadata=None: [
                {"text": "evidence", "metadata": {"id": "paper-1", "chunk_index": 1}, "similarity": 0.9}
            ],
        )
        planner_llm = Mock()
        planner_llm._call.return_value = '{"brief":"brief","subQuestions":["Q1","Q2","Q3"]}'

        with (
            patch("services.research_task_service.get_rag", return_value=fake_rag),
            patch("services.research_task_service.get_llm", return_value=planner_llm),
            patch(
                "services.research_task_service.build_retrieval_queries",
                return_value={
                    "original": "Q1",
                    "rewritten": "Q1",
                    "keywords": ["evidence"],
                    "taskType": "research",
                    "source": "fallback",
                },
            ),
            patch("services.research_task_service.retrieve_hybrid_results", return_value={"vector": [], "bm25": []}),
        ):
            created = create_research_task(
                ResearchTaskCreateRequest(question="取消测试", pdfId="paper-1"),
                start_async=False,
            )
            task_id = created["task"]["taskId"]
            cancel_research_task(task_id)
            run_research_task_now(task_id)
            task = get_research_task(task_id)["task"]

        self.assertEqual(task["status"], "cancelled")
        self.assertEqual(task["stage"], "done")
        self.assertEqual(task["report"], "")

    def test_research_task_fails_when_current_paper_is_not_indexed(self):
        fake_rag = FakeRag(documents=[], retrieve_handler=lambda query, top_k=3, filter_metadata=None: [])

        with patch("services.research_task_service.get_rag", return_value=fake_rag):
            created = create_research_task(
                ResearchTaskCreateRequest(question="没有索引怎么办？", pdfId="paper-missing"),
                start_async=False,
            )
            task_id = created["task"]["taskId"]
            run_research_task_now(task_id)
            task = get_research_task(task_id)["task"]

        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["stage"], "done")
        self.assertIn("indexed", task["error"])

    def test_unknown_task_raises_not_found(self):
        with self.assertRaises(ResearchTaskNotFoundError):
            get_research_task("missing-task")


if __name__ == "__main__":
    unittest.main()
