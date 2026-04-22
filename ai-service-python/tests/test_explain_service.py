import re
import unittest
from unittest.mock import patch

from schemas.requests import TermExplainRequest
from services.chat_service import explain_term
from services.trace_service import clear_traces, get_trace_snapshot


class FakeRag:
    def __init__(self, results=None, error=None):
        self.results = results if results is not None else []
        self.error = error
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
        if self.error:
            raise self.error
        return self.results


class ExplainTermServiceTests(unittest.TestCase):
    def setUp(self):
        clear_traces()

    def tearDown(self):
        clear_traces()

    def test_explain_term_uses_current_pdf_rag_when_pdf_id_is_present(self):
        fake_rag = FakeRag(results=[{"text": "Current paper context about contrastive loss.", "metadata": {"id": "paper-1"}}])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value={
                "original": "original explain query",
                "rewritten": "contrastive loss query",
                "keywords": ["contrastive loss"],
                "taskType": "explain",
                "source": "llm",
            }),
            patch("services.chat_service.retrieve_hybrid_results") as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "这是当前论文中的术语解释。"

            response = explain_term(TermExplainRequest(
                term="contrastive loss",
                context="This page introduces contrastive learning.",
                pdfId="paper-1",
                pageNumber=4,
            ))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["explanation"], "这是当前论文中的术语解释。")
        self.assertEqual(response["rag_sources"][0]["sourceId"], "source-1")
        self.assertEqual(response["rag_sources"][0]["id"], "source-1")
        self.assertEqual(response["rag_sources"][0]["text"], "Current paper context about contrastive loss.")
        self.assertEqual(response["rag_sources"][0]["pdfId"], "paper-1")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "current_paper")
        self.assertEqual(response["queryPlan"]["rewritten"], "contrastive loss query")
        self.assertEqual(response["retrievalJudge"]["verdict"], "CORRECT")
        self.assertTrue(response["traceId"])
        self.assertEqual(fake_rag.retrieve_calls[0]["filter_metadata"], {"id": "paper-1"})
        self.assertEqual(fake_rag.retrieve_calls[0]["query"], "contrastive loss query")
        self.assertEqual(fake_rag.retrieve_calls[0]["top_k"], 5)
        mocked_hybrid.assert_not_called()
        trace = get_trace_snapshot(response["traceId"])
        self.assertEqual(trace["status"], "success")
        self.assertGreaterEqual(trace["counters"]["retrievalCalls"], 1)

    def test_explain_term_falls_back_to_literature_rag_when_pdf_rag_fails(self):
        fake_rag = FakeRag(error=RuntimeError("rag unavailable"))
        fallback_results = [{"text": "General literature context.", "metadata": {"id": "other-paper"}}]

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value={
                "original": "original attention query",
                "rewritten": "attention query",
                "keywords": ["attention"],
                "taskType": "explain",
                "source": "llm",
            }),
            patch(
                "services.chat_service.retrieve_hybrid_results",
                return_value={"vector": fallback_results, "bm25": []},
            ) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "这是兜底解释。"

            response = explain_term(TermExplainRequest(
                term="attention",
                context="The selected page context.",
                pdfId="paper-1",
                pageNumber=2,
            ))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["explanation"], "这是兜底解释。")
        self.assertEqual(response["rag_sources"][0]["text"], "General literature context.")
        self.assertEqual(response["rag_sources"][0]["pdfId"], "other-paper")
        self.assertEqual(response["rag_sources"][0]["sourceType"], "library")
        self.assertEqual(response["queryPlan"]["rewritten"], "attention query")
        self.assertIn(response["retrievalJudge"]["verdict"], ("AMBIGUOUS", "INCORRECT"))
        self.assertEqual(mocked_hybrid.call_count, 2)
        mocked_hybrid.assert_any_call("attention query", top_k=3)

    def test_explain_term_uses_fallback_query_plan_when_rewrite_fails(self):
        fake_rag = FakeRag(results=[{"text": "Original query evidence.", "metadata": {"id": "paper-1"}}])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.query_service.get_llm") as mocked_query_llm,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_query_llm.return_value._call.side_effect = RuntimeError("rewrite failed")
            mocked_get_llm.return_value._call.return_value = "原始查询解释。"

            response = explain_term(TermExplainRequest(
                term="attention",
                context="The selected page context.",
                pdfId="paper-1",
                pageNumber=2,
            ))

        self.assertEqual(response["queryPlan"]["source"], "fallback")
        self.assertIn("attention", response["queryPlan"]["rewritten"])
        self.assertEqual(fake_rag.retrieve_calls[0]["query"], response["queryPlan"]["rewritten"])
        self.assertEqual(response["explanation"], "原始查询解释。")

    def test_explain_term_retries_once_when_evidence_is_missing(self):
        fake_rag = FakeRag(results=[])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.build_retrieval_queries", return_value={
                "original": "original results query",
                "rewritten": "results query",
                "keywords": ["results"],
                "taskType": "explain",
                "source": "llm",
            }),
            patch("services.chat_service.retrieve_hybrid_results", return_value={"vector": [], "bm25": []}) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.return_value = "当前论文证据不足。"

            response = explain_term(TermExplainRequest(
                term="results",
                context="The selected page context.",
                pdfId="paper-1",
                pageNumber=3,
            ))

        self.assertEqual(response["retrievalJudge"]["verdict"], "INCORRECT")
        self.assertEqual(len(fake_rag.retrieve_calls), 2)
        self.assertEqual(mocked_hybrid.call_count, 2)
        final_prompt = mocked_get_llm.return_value._call.call_args[0][0]
        self.assertIn("当前论文或资料库证据不足", final_prompt)


if __name__ == "__main__":
    unittest.main()
