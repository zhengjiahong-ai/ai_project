import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from services import analysis_service


class _NoOutputGrobidClient:
    def process(self, *args, **kwargs):
        return None


class PdfParseDiagnosticsTests(unittest.TestCase):
    def test_digital_pdf_is_parsed_when_pdf_text_reaches_threshold(self):
        diagnostics = analysis_service._build_parse_diagnostics(
            page_count=10,
            pdf_text_char_count=500,
            tei_text_char_count=0,
        )

        self.assertEqual(diagnostics["parseStatus"], "parsed")
        self.assertNotIn("parseMessage", diagnostics)

    def test_multi_page_pdf_with_no_text_needs_ocr(self):
        diagnostics = analysis_service._build_parse_diagnostics(
            page_count=12,
            pdf_text_char_count=0,
            tei_text_char_count=0,
        )

        self.assertEqual(diagnostics["textThreshold"], 600)
        self.assertEqual(diagnostics["parseStatus"], "scanned_or_low_text")
        self.assertIn("OCR", diagnostics["parseMessage"])

    def test_tei_text_prevents_false_positive_when_pdf_text_is_sparse(self):
        diagnostics = analysis_service._build_parse_diagnostics(
            page_count=20,
            pdf_text_char_count=10,
            tei_text_char_count=1000,
        )

        self.assertEqual(diagnostics["parseStatus"], "parsed")

    def test_missing_tei_and_low_pdf_text_returns_successful_degraded_response(self):
        upload = UploadFile(filename="scan.pdf", file=io.BytesIO(b"fake-pdf"))

        with (
            patch.object(analysis_service, "get_grobid_client", return_value=_NoOutputGrobidClient()),
            patch.object(
                analysis_service,
                "_extract_pdf_text_stats",
                return_value={"pageCount": 4, "textCharCount": 0},
            ),
        ):
            response = asyncio.run(analysis_service.analyze_pdf(upload))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["parseStatus"], "scanned_or_low_text")
        self.assertEqual(response["paper_structure"]["sections"], [])
        self.assertFalse(response["ragIndexed"])
        self.assertEqual(response["ragChunkCount"], 0)

    def test_missing_tei_with_sufficient_pdf_text_remains_an_error(self):
        upload = UploadFile(filename="digital.pdf", file=io.BytesIO(b"fake-pdf"))

        with (
            patch.object(analysis_service, "get_grobid_client", return_value=_NoOutputGrobidClient()),
            patch.object(
                analysis_service,
                "_extract_pdf_text_stats",
                return_value={"pageCount": 2, "textCharCount": 300},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "GROBID did not produce"):
                asyncio.run(analysis_service.analyze_pdf(upload))


if __name__ == "__main__":
    unittest.main()
