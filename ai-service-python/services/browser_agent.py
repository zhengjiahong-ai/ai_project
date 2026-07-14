"""Headless browser agent using Playwright for JS-rendered page access.

Controlled by ``PIXIU_ALLOW_BROWSER=true`` (default: disabled).
Provides ``browser_navigate`` and ``browser_screenshot`` tools.
Session state is maintained in a module-level singleton.
"""

from __future__ import annotations

import base64
import os
import threading
from typing import Any

from bs4 import BeautifulSoup

from services.url_whitelist import validate_fetch_url

# ── Constants ────────────────────────────────────────────────────────────────

NAVIGATE_TIMEOUT_MS: int = 30000  # 30s
SCREENSHOT_TIMEOUT_MS: int = 15000  # 15s
MAX_CONTENT_CHARS: int = 50000
MAX_SCREENSHOT_BYTES: int = 5 * 1024 * 1024  # 5 MiB

_BROWSER_ENV_KEY: str = "PIXIU_ALLOW_BROWSER"

# ── Module-level browser singleton ───────────────────────────────────────────

_lock = threading.Lock()
_playwright = None
_browser = None
_page = None
_current_url: str = ""


def _is_browser_allowed() -> bool:
    return os.environ.get(_BROWSER_ENV_KEY, "").strip().lower() == "true"


def _get_page():
    """Return the module-level Playwright page singleton (lazy init)."""
    global _playwright, _browser, _page
    if _page is not None:
        return _page

    if not _is_browser_allowed():
        return None

    with _lock:
        if _page is not None:
            return _page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        _page = _browser.new_page()
    return _page


# ── Public API ───────────────────────────────────────────────────────────────

def browser_navigate(url: str) -> dict[str, Any]:
    """Navigate to *url* and return the JS-rendered text content.

    Returns ``{status, url, content, title, error}``.
    """
    if not _is_browser_allowed():
        return _error("Browser is disabled. Set PIXIU_ALLOW_BROWSER=true to enable.")

    if not url or not isinstance(url, str) or not url.strip():
        return _error("URL cannot be empty.")

    try:
        hostname = validate_fetch_url(url)
    except ValueError as exc:
        return _error(f"URL validation failed: {exc}")

    page = _get_page()
    if page is None:
        return _error(
            "Browser not available. Install playwright: pip install playwright && playwright install chromium"
        )

    global _current_url

    try:
        # Block non-whitelisted outbound requests via route interception
        def _route_handler(route):
            req_url = route.request.url
            try:
                validate_fetch_url(req_url)
                route.continue_()
            except ValueError:
                route.abort()

        page.route("**/*", _route_handler)

        page.goto(url, timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
        _current_url = url

        title = page.title()[:500]
        html = page.content()

        # Extract text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)[:MAX_CONTENT_CHARS]

        return {
            "status": "success",
            "url": hostname,
            "content": content,
            "title": title,
            "error": "",
        }
    except Exception as exc:
        return _error(f"Navigation failed: {exc}")


def browser_screenshot() -> dict[str, Any]:
    """Capture a screenshot of the current page viewport.

    Returns ``{status, imageBase64, error}``.
    """
    if not _is_browser_allowed():
        return _error("Browser is disabled. Set PIXIU_ALLOW_BROWSER=true to enable.")

    page = _get_page()
    if page is None or not _current_url:
        return _error("No active page. Call browser_navigate first.")

    try:
        screenshot_bytes = page.screenshot(
            type="png", full_page=False, timeout=SCREENSHOT_TIMEOUT_MS
        )
        if len(screenshot_bytes) > MAX_SCREENSHOT_BYTES:
            return _error(f"Screenshot exceeds maximum of {MAX_SCREENSHOT_BYTES} bytes.")

        data_uri = f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('ascii')}"
        return {
            "status": "success",
            "imageBase64": data_uri,
            "error": "",
        }
    except Exception as exc:
        return _error(f"Screenshot failed: {exc}")


def cleanup_browser() -> None:
    """Close browser and Playwright instance (call on process shutdown)."""
    global _playwright, _browser, _page, _current_url
    try:
        if _page is not None:
            _page.close()
    except Exception:
        pass
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright is not None:
            _playwright.stop()
    except Exception:
        pass
    _page = None
    _browser = None
    _playwright = None
    _current_url = ""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "url": "", "content": "", "title": "", "imageBase64": "", "error": message}
