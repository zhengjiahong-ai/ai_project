import unittest

from services.evidence_service import (
    compact_evidence_for_response,
    format_evidence_context,
    normalize_evidence_items,
)


class EvidenceServiceTests(unittest.TestCase):
    def test_normalizes_vector_retrieval_result(self):
        results = normalize_evidence_items(
            [{
                "text": "Evidence text",
                "similarity": "0.83",
                "metadata": {"id": "paper-1", "chunk_index": 3},
            }],
            source_type="current_paper",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["sourceId"], "source-1")
        self.assertEqual(results[0]["text"], "Evidence text")
        self.assertEqual(results[0]["metadata"], {"id": "paper-1", "chunk_index": 3})
        self.assertEqual(results[0]["similarity"], 0.83)
        self.assertIsNone(results[0]["score"])
        self.assertEqual(results[0]["pdfId"], "paper-1")
        self.assertEqual(results[0]["chunkIndex"], 3)
        self.assertEqual(results[0]["sourceType"], "current_paper")

    def test_normalizes_bm25_retrieval_result(self):
        results = normalize_evidence_items(
            [{"text": "BM25 context", "score": 2}],
            source_type="library",
        )

        self.assertEqual(results[0]["sourceId"], "source-1")
        self.assertEqual(results[0]["score"], 2.0)
        self.assertIsNone(results[0]["similarity"])
        self.assertEqual(results[0]["sourceType"], "library")

    def test_normalizes_document_results_with_limits_and_text_truncation(self):
        results = normalize_evidence_items(
            [
                {"document": "abcdefghi", "metadata": {"pdfId": "paper-2", "chunkIndex": "7"}},
                {"text": "   ", "metadata": {"id": "empty"}},
                {"page_content": "third document", "metadata": {"id": "paper-3"}},
            ],
            limit=2,
            max_text_chars=5,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["text"], "abcde")
        self.assertEqual(results[0]["pdfId"], "paper-2")
        self.assertEqual(results[0]["chunkIndex"], 7)
        self.assertEqual(results[1]["text"], "third")
        self.assertEqual(results[1]["sourceId"], "source-2")

    def test_formats_context_and_compacts_response_fields(self):
        evidence = normalize_evidence_items(
            [{"text": "A useful source text.", "score": 1.5, "metadata": {"id": "paper-1"}}],
            source_type="library",
        )

        context = format_evidence_context(evidence, title="Evidence", max_items=1, max_text_chars=20)
        compacted = compact_evidence_for_response(evidence, max_items=1, max_text_chars=10)

        self.assertIn("Evidence", context)
        self.assertIn("source-1 [library]", context)
        self.assertIn("score=1.5000", context)
        self.assertEqual(compacted[0]["id"], "source-1")
        self.assertEqual(compacted[0]["sourceId"], "source-1")
        self.assertEqual(compacted[0]["text"], "A useful s")
        self.assertEqual(compacted[0]["sourceType"], "library")


if __name__ == "__main__":
    unittest.main()
