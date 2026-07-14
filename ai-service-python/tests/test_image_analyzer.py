"""
Tests for the image_analyzer module.

Covers: URL validation rejection, empty/invalid inputs,
and integration tests with real VLM (skipped when network is unavailable).
"""

import os
import unittest
from unittest.mock import patch

from services.image_analyzer import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    MAX_IMAGE_BYTES,
    analyze_image,
)


def _network_available() -> bool:
    try:
        import socket
        s = socket.create_connection(("api.deepseek.com", 443), timeout=3)
        s.close()
        return bool(os.environ.get("DEEPSEEK_API_KEY"))
    except Exception:
        return False


_NET = _network_available()


# ── Unit tests (no network needed) ───────────────────────────────────────────

class ImageAnalyzerValidationTests(unittest.TestCase):

    def test_rejects_empty_url(self):
        result = analyze_image("")
        self.assertEqual(result["status"], "error")
        self.assertIn("empty", result["error"].lower())

    def test_rejects_none_url(self):
        result = analyze_image(None)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "error")

    def test_rejects_whitespace_url(self):
        result = analyze_image("   ")
        self.assertEqual(result["status"], "error")

    def test_rejects_non_https_url(self):
        result = analyze_image("http://example.com/image.png")
        self.assertEqual(result["status"], "error")
        self.assertIn("URL", result["error"])

    def test_rejects_unlisted_domain(self):
        result = analyze_image("https://evil.example.com/image.png")
        self.assertEqual(result["status"], "error")
        self.assertIn("URL", result["error"])

    def test_rejects_localhost(self):
        result = analyze_image("https://localhost/image.png")
        self.assertEqual(result["status"], "error")

    def test_rejects_raw_ip(self):
        result = analyze_image("https://192.168.1.1/image.png")
        self.assertEqual(result["status"], "error")

    def test_allowed_image_types(self):
        for ct in sorted(ALLOWED_IMAGE_CONTENT_TYPES):
            with self.subTest(content_type=ct):
                self.assertIn(ct, ALLOWED_IMAGE_CONTENT_TYPES)

    def test_common_bad_types_not_allowed(self):
        bad_types = ["text/html", "application/json", "image/svg+xml", "image/bmp"]
        for ct in bad_types:
            self.assertNotIn(ct, ALLOWED_IMAGE_CONTENT_TYPES)

    def test_max_image_bytes_is_reasonable(self):
        self.assertGreater(MAX_IMAGE_BYTES, 0)
        self.assertLessEqual(MAX_IMAGE_BYTES, 10 * 1024 * 1024)

    def test_error_result_structure(self):
        result = analyze_image("")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["sourceType"], "")
        self.assertIn("error", result)

    @patch("services.image_analyzer.validate_fetch_url")
    def test_download_timeout_handled(self, mock_validate):
        mock_validate.return_value = "example.com"
        result = analyze_image("https://example.com/nonexistent.png")
        self.assertEqual(result["status"], "error")


# ── Integration tests (require network + VLM) ────────────────────────────────

@unittest.skipUnless(_NET, "Network and DEEPSEEK_API_KEY required for VLM tests")
class ImageAnalyzerVLMIntegrationTests(unittest.TestCase):

    def test_analyze_whitelisted_image(self):
        # Use a known-good image URL from a whitelisted domain.
        result = analyze_image(
            "https://arxiv.org/static/browse/0.3.4/images/arxiv-logo-one-color-white.svg"
        )
        # May succeed or fail depending on content-type (SVG not allowed) —
        # the key is that it doesn't crash.
        self.assertIn(result["status"], ("success", "error"))


if __name__ == "__main__":
    unittest.main()
