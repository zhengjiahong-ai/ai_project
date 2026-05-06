import unittest
from unittest.mock import patch

from schemas.requests import DeepAnalysisRequest
from services import analysis_service


class EmptyRAG:
    def get_documents_by_metadata(self, filter_metadata=None, limit=400):
        return []


class DeepAnalysisErrorTests(unittest.TestCase):
    def test_missing_pdf_index_raises_structured_error(self):
        with patch.object(analysis_service, "get_rag", return_value=EmptyRAG()):
            with self.assertRaises(analysis_service.PaperNotIndexedError) as context:
                analysis_service.deep_analysis(DeepAnalysisRequest(pdf_id="Paper Name.pdf"))

        error = context.exception
        self.assertEqual(error.error_code, analysis_service.PAPER_NOT_INDEXED_ERROR_CODE)
        self.assertEqual(error.pdf_id, "paper_name.pdf")
        self.assertTrue(error.trace_id)
        self.assertIn("status", error.to_response())
        self.assertEqual(error.to_response()["status"], "error")


if __name__ == "__main__":
    unittest.main()
