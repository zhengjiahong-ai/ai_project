import unittest
from unittest.mock import Mock, patch
from core.pdf_evidence_pages import extract_evidence_pages
from core.smart_chunker import chunk_sections


class EvidencePageTests(unittest.TestCase):
    def test_chunks_keep_real_zero_based_page_with_blank_pages(self):
        pages = [Mock(), Mock(), Mock()]
        pages[0].extract_text.return_value = "Method evidence " * 180
        pages[1].extract_text.return_value = ""
        pages[2].extract_text.return_value = "Experiment evidence"
        with patch("core.pdf_evidence_pages.PdfReader", return_value=Mock(pages=pages)):
            chunks = chunk_sections(extract_evidence_pages("paper.pdf"))
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks[-1]["pageIndex"], 2)
        self.assertEqual(chunks[-1]["text"], "Experiment evidence")
        self.assertTrue(all(item["pageIndex"] == 0 for item in chunks[:-1]))
