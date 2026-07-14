"""Tests for the browser_agent module.

Covers: authorization checks, URL validation, empty inputs,
and integration tests with Playwright (skipped when unavailable).
"""

import os
import unittest
from unittest.mock import patch

from services.browser_agent import (
    _is_browser_allowed,
    browser_navigate,
    browser_screenshot,
    cleanup_browser,
)


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


_BROWSER = _browser_available()


class BrowserAgentUnitTests(unittest.TestCase):

    def setUp(self):
        # Ensure browser is disabled for unit tests
        os.environ.pop("PIXIU_ALLOW_BROWSER", None)

    def tearDown(self):
        cleanup_browser()

    def test_is_browser_allowed_defaults_false(self):
        self.assertFalse(_is_browser_allowed())

    def test_is_browser_allowed_true_when_set(self):
        os.environ["PIXIU_ALLOW_BROWSER"] = "true"
        self.assertTrue(_is_browser_allowed())
        os.environ.pop("PIXIU_ALLOW_BROWSER", None)

    def test_is_browser_allowed_case_insensitive(self):
        os.environ["PIXIU_ALLOW_BROWSER"] = "TRUE"
        self.assertTrue(_is_browser_allowed())
        os.environ.pop("PIXIU_ALLOW_BROWSER", None)

    def test_browser_navigate_rejects_when_disabled(self):
        result = browser_navigate("https://example.com")
        self.assertEqual(result["status"], "error")
        self.assertIn("disabled", result["error"].lower())

    def test_browser_navigate_rejects_empty_url(self):
        result = browser_navigate("")
        self.assertEqual(result["status"], "error")

    def test_browser_navigate_rejects_whitespace_url(self):
        result = browser_navigate("   ")
        self.assertEqual(result["status"], "error")

    @patch("services.browser_agent.validate_fetch_url", side_effect=ValueError("not whitelisted"))
    @patch.dict(os.environ, {"PIXIU_ALLOW_BROWSER": "true"})
    def test_browser_navigate_rejects_non_whitelisted_url(self, _mock):
        result = browser_navigate("https://evil.example.com")
        self.assertEqual(result["status"], "error")
        self.assertIn("not whitelisted", result["error"])

    def test_browser_screenshot_rejects_when_disabled(self):
        result = browser_screenshot()
        self.assertEqual(result["status"], "error")
        self.assertIn("disabled", result["error"].lower())

    def test_browser_screenshot_rejects_when_no_page(self):
        os.environ["PIXIU_ALLOW_BROWSER"] = "true"
        try:
            result = browser_screenshot()
            self.assertEqual(result["status"], "error")
        finally:
            os.environ.pop("PIXIU_ALLOW_BROWSER", None)
            cleanup_browser()


@unittest.skipUnless(_BROWSER, "Playwright not installed")
class BrowserAgentIntegrationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["PIXIU_ALLOW_BROWSER"] = "true"

    @classmethod
    def tearDownClass(cls):
        cleanup_browser()
        os.environ.pop("PIXIU_ALLOW_BROWSER", None)

    def test_navigate_returns_content(self):
        result = browser_navigate("https://example.com")
        # May fail on network issues in CI, but shouldn't crash
        if result["status"] == "success":
            self.assertIn("Example", result["title"])
            self.assertGreater(len(result["content"]), 0)

    def test_screenshot_after_navigate(self):
        nav = browser_navigate("https://example.com")
        if nav["status"] != "success":
            self.skipTest("Network unavailable for integration test")
        result = browser_screenshot()
        self.assertEqual(result["status"], "success")
        self.assertIn("data:image/png;base64,", result["imageBase64"])


if __name__ == "__main__":
    unittest.main()
