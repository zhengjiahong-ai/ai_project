import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.api import router


class ApiRoutesTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_chat_route_returns_service_payload(self):
        with patch("routes.api.chat_service.chat", return_value={"status": "success", "message": "ok"}) as mocked:
            response = self.client.post(
                "/api/chat",
                json={"message": "hello", "pdfId": "paper-1", "history": [], "paperSkeleton": {}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "ok")
        mocked.assert_called_once()

    def test_translate_page_route_returns_service_payload(self):
        with patch(
            "routes.api.chat_service.translate_page",
            return_value={
                "status": "success",
                "pageIndex": 0,
                "translatedText": "译文",
                "sourceText": "source",
                "translatedBlocks": [{"id": "block-1", "translatedText": "译文"}],
                "renderMode": "overlay",
            },
        ) as mocked:
            response = self.client.post(
                "/api/translate-page",
                json={
                    "pdfId": "paper-1",
                    "pageIndex": 0,
                    "pageText": "source",
                    "paperSkeleton": {},
                    "pageLayout": {
                        "viewport": {"width": 600, "height": 800},
                        "blocks": [{"id": "block-1", "text": "source"}],
                        "excludedZonesVersion": 1,
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["translatedText"], "译文")
        self.assertEqual(response.json()["renderMode"], "overlay")
        mocked.assert_called_once()

    def test_translate_page_route_rejects_blank_text(self):
        with patch("routes.api.chat_service.translate_page", side_effect=ValueError("Page text cannot be empty.")):
            response = self.client.post(
                "/api/translate-page",
                json={"pdfId": "paper-1", "pageIndex": 0, "pageText": "   ", "paperSkeleton": {}},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["message"], "Page text cannot be empty.")

    def test_deep_analysis_accepts_pdf_id_payload(self):
        with patch(
            "routes.api.analysis_service.deep_analysis",
            return_value={"status": "success", "critical_analysis": "done"},
        ) as mocked:
            response = self.client.post("/api/deep-analysis", json={"pdf_id": "paper-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["critical_analysis"], "done")
        mocked.assert_called_once()

    def test_background_knowledge_accepts_pdf_payload(self):
        with patch(
            "routes.api.analysis_service.get_background_knowledge",
            return_value={
                "status": "success",
                "pdfId": "paper-1",
                "background_knowledge": ["RAG"],
                "graph": {"nodes": [], "links": []},
            },
        ) as mocked:
            response = self.client.post(
                "/api/background-knowledge",
                json={"pdfId": "paper-1", "paperSkeleton": {"abstract": "summary"}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pdfId"], "paper-1")
        mocked.assert_called_once()

    def test_analyze_pdf_route_uses_service(self):
        with patch(
            "routes.api.analysis_service.analyze_pdf",
            new=AsyncMock(return_value={"status": "success", "pdfId": "paper-1"}),
        ) as mocked:
            response = self.client.post(
                "/api/analyze-pdf",
                files={"file": ("paper.pdf", b"pdf", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pdfId"], "paper-1")
        mocked.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
