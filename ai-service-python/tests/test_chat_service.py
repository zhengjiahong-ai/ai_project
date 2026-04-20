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
        return self.results


def _mock_query_plan(rewritten="rewritten academic query"):
    return {
        "original": "original question",
        "rewritten": rewritten,
        "keywords": ["rewritten", "academic"],
        "taskType": "chat",
        "source": "llm",
    }


class ChatServiceTests(unittest.TestCase):
    def test_chat_uses_current_pdf_rag_with_pdf_id(self):
        fake_rag = FakeRag(results=[{
            "text": "Current paper evidence about the method.",
            "metadata": {"id": "paper-1", "chunk_index": 2},
            "similarity": 0.9,
        }])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value=_mock_query_plan()) as mocked_plan,
            patch("services.chat_service.retrieve_hybrid_results") as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="这篇论文的方法是什么？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["message"], "回答")
        self.assertEqual(response["queryPlan"]["rewritten"], "rewritten academic query")
        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "current_paper")
        self.assertEqual(response["rag_sources"][0]["chunkIndex"], 2)
        self.assertEqual(fake_rag.retrieve_calls[0]["query"], "rewritten academic query")
        self.assertEqual(fake_rag.retrieve_calls[0]["filter_metadata"], {"id": "paper-1"})
        self.assertEqual(fake_rag.retrieve_calls[0]["top_k"], 12)
        mocked_plan.assert_called_once()
        mocked_hybrid.assert_not_called()

    def test_chat_falls_back_to_library_when_current_pdf_has_no_results(self):
        fake_rag = FakeRag(results=[])
        hybrid_results = {
            "vector": [{"text": "Library vector evidence.", "metadata": {"id": "lib-1"}, "similarity": 0.7}],
            "bm25": [{"text": "Library BM25 evidence.", "score": 2.5}],
        }

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value=_mock_query_plan("fallback query")),
            patch("services.chat_service.retrieve_hybrid_results", return_value=hybrid_results) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="证据在哪里？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(response["rag_sources"][0]["sourceType"], "library")
        self.assertEqual(response["rag_sources"][0]["text"], "Library vector evidence.")
        self.assertEqual(response["rag_sources"][1]["score"], 2.5)
        self.assertIn(response["retrievalJudge"]["verdict"], ("AMBIGUOUS", "INCORRECT"))
        self.assertEqual(mocked_hybrid.call_count, 2)
        mocked_hybrid.assert_any_call("fallback query", top_k=5)

    def test_chat_without_pdf_id_uses_library_hybrid_retrieval(self):
        hybrid_results = {
            "vector": [],
            "bm25": [{"text": "BM25-only evidence.", "score": 4.0}],
        }

        with (
            patch("services.chat_service.build_retrieval_queries", return_value=_mock_query_plan("library query")),
            patch("services.chat_service.retrieve_hybrid_results", return_value=hybrid_results) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "回答"

            response = chat(ChatRequest(message="什么是 RAG？", history=[], paperSkeleton={}))

        self.assertEqual(response["rag_sources"][0]["text"], "BM25-only evidence.")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "library")
        self.assertEqual(response["queryPlan"]["source"], "llm")
        self.assertIn(response["retrievalJudge"]["verdict"], ("AMBIGUOUS", "INCORRECT"))
        self.assertEqual(mocked_hybrid.call_count, 2)
        mocked_hybrid.assert_any_call("library query", top_k=5)

    def test_chat_with_insufficient_evidence_retries_once_and_adds_boundary_instruction(self):
        fake_rag = FakeRag(results=[])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value=_mock_query_plan("missing query")),
            patch("services.chat_service.retrieve_hybrid_results", return_value={"vector": [], "bm25": []}) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "当前证据不足。"

            response = chat(ChatRequest(message="这篇论文有哪些实验结果？", pdfId="paper-1", history=[], paperSkeleton={}))

        self.assertEqual(response["retrievalJudge"]["verdict"], "INCORRECT")
        self.assertEqual(len(response["rag_sources"]), 0)
        self.assertEqual(len(fake_rag.retrieve_calls), 2)
        self.assertEqual(mocked_hybrid.call_count, 2)
        final_prompt = mocked_get_llm.return_value._call.call_args[0][0]
        self.assertIn("当前论文或资料库证据不足", final_prompt)


if __name__ == "__main__":
    unittest.main()
