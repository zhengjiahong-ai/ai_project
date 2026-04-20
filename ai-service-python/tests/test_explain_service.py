import re
import unittest
from unittest.mock import patch

from schemas.requests import TermExplainRequest
from services.chat_service import explain_term


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
    def test_explain_term_uses_current_pdf_rag_when_pdf_id_is_present(self):
        fake_rag = FakeRag(results=[{"text": "Current paper context about contrastive loss.", "metadata": {"id": "paper-1"}}])

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.retrieve_hybrid_for_vector") as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.side_effect = ["contrastive loss query", "这是当前论文中的术语解释。"]

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
        self.assertEqual(fake_rag.retrieve_calls[0]["filter_metadata"], {"id": "paper-1"})
        self.assertEqual(fake_rag.retrieve_calls[0]["top_k"], 5)
        mocked_hybrid.assert_not_called()

    def test_explain_term_falls_back_to_literature_rag_when_pdf_rag_fails(self):
        fake_rag = FakeRag(error=RuntimeError("rag unavailable"))
        fallback_results = [{"text": "General literature context.", "metadata": {"id": "other-paper"}}]

        with (
            patch("services.chat_service.get_rag", return_value=fake_rag),
            patch("services.chat_service.retrieve_hybrid_for_vector", return_value=fallback_results) as mocked_hybrid,
            patch("services.chat_service.get_llm") as mocked_get_llm,
        ):
            mocked_get_llm.return_value._call.side_effect = ["attention query", "这是兜底解释。"]

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
        mocked_hybrid.assert_called_once_with("attention query", top_k=3)


if __name__ == "__main__":
    unittest.main()
