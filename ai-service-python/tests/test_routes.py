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

    def test_deep_analysis_accepts_pdf_id_payload(self):
        with patch(
            "routes.api.analysis_service.deep_analysis",
            return_value={"status": "success", "critical_analysis": "done"},
        ) as mocked:
            response = self.client.post("/api/deep-analysis", json={"pdf_id": "paper-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["critical_analysis"], "done")
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
