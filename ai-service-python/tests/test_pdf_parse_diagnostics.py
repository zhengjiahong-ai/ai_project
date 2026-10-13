import asyncio
import io
import os
import threading
import unittest
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("fastapi", reason="FastAPI not available")

from fastapi import UploadFile

from services import analysis_service


class _NoOutputGrobidClient:
    def process(self, *args, **kwargs):
        return None


class PdfParseDiagnosticsTests(unittest.TestCase):
    def test_parse_does_not_block_other_event_loop_work(self):
        entered, release = threading.Event(), threading.Event()
        caller_thread = threading.get_ident()

        def blocking_parse(content, filename, *, include_ai_analysis):
            self.assertNotEqual(threading.get_ident(), caller_thread)
            self.assertEqual((content, filename, include_ai_analysis), (b'pdf', 'paper.pdf', False))
            entered.set()
            if not release.wait(2):
                raise AssertionError('Event loop did not release parsing worker')
            return {'status': 'success'}

        async def exercise():
            pending = asyncio.create_task(analysis_service.analyze_pdf(
                UploadFile(filename='paper.pdf', file=io.BytesIO(b'pdf')), include_ai_analysis=False))
            try:
                self.assertTrue(await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), 1.5))
                # A live request can execute while parsing remains blocked.
                self.assertFalse(pending.done())
            finally:
                release.set()
            self.assertEqual(await pending, {'status': 'success'})

        with patch.object(analysis_service, '_analyze_pdf_bytes', side_effect=blocking_parse):
            asyncio.run(exercise())

    def test_parse_only_indexes_and_builds_outline_without_any_model_call(self):
        class Grobid:
            def process(self, *args, **kwargs):
                with open(os.path.join(kwargs["output"], "paper.tei.xml"), "w", encoding="utf-8") as handle:
                    handle.write("<TEI><abstract>Abstract evidence</abstract></TEI>")

        class Rag:
            def add_sections_to_db(self, sections, path, metadata):
                self.sections = sections
                return 3
            def get_documents_by_metadata(self, metadata, limit):
                return [{"text": "indexed evidence"}]

        rag = Rag()
        sections = [{"title": "Methods", "content": "Method evidence " * 100}]
        outline = [{"id": "method", "title": "Methods"}]
        soup = Mock()
        soup.find.return_value.get_text.return_value = "Abstract evidence"
        with (
            patch.object(analysis_service, "get_grobid_client", return_value=Grobid()),
            patch.object(analysis_service, "_extract_pdf_text_stats", return_value={"pageCount": 2, "textCharCount": 2000}),
            patch.object(analysis_service, "parse_tei_xml", return_value=sections),
            patch.object(analysis_service, "extract_translation_layout_index", return_value={}),
            patch.object(analysis_service, "build_document_outline", return_value=outline),
            patch.object(analysis_service, "BeautifulSoup", return_value=soup),
            patch.object(analysis_service, "get_rag", return_value=rag),
            patch.object(analysis_service, "is_rag_available", return_value=True),
            patch.object(analysis_service, "get_llm", side_effect=AssertionError("Parsing must not call a model")) as model,
        ):
            response = asyncio.run(analysis_service.analyze_pdf(
                UploadFile(filename="paper.pdf", file=io.BytesIO(b"%PDF-test")), include_ai_analysis=False))
        model.assert_not_called()
        self.assertEqual(rag.sections, sections)
        self.assertEqual(response["paper_structure"]["sections"], outline)
        self.assertEqual(response["paper_skeleton"], {})
        self.assertEqual(response["aiAnalysisStatus"], "not_requested")
        self.assertTrue(response["readingReady"])
        self.assertTrue(response["questionReady"])
        self.assertEqual(response["ragChunkCount"], 3)

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
