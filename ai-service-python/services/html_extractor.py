"""HTML content extractor: converts raw HTML to safe plain text.

Uses BeautifulSoup + lxml for parsing. Removes dangerous tags,
extracts clean text, and applies post-processing constraints.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup, CData, Comment


# Tags to decompose (remove tag + all content/descendants).
# These are container tags whose inner content must not leak.
_DECOMPOSE_TAGS = frozenset({
    "script", "style", "iframe", "object",
    "svg", "math", "form", "select", "textarea",
    "canvas", "video", "audio",
    "noscript",
})

# Tags to extract (remove the tag wrapper but preserve any inner text,
# or self-closing tags where decompose could eat neighboring elements).
_EXTRACT_TAGS = frozenset({
    "embed", "input", "button", "source", "link", "meta", "base",
})

_MAX_OUTPUT_CHARS = 50000

# Match non-printable characters except newline (\n, 0x0a) and carriage return (\r, 0x0d)
_NON_PRINTABLE_PATTERN = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Match 3+ consecutive newlines
_MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")

# Match multiple spaces / tabs
_MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_html_content(
    html: Any,
    *,
    url: str = "",
    fetched_at: Optional[str] = None,
    max_chars: int = _MAX_OUTPUT_CHARS,
) -> Dict[str, Any]:
    """Convert raw HTML to safe plain text.

    Args:
        html: Raw HTML content (str or None).
        url: Source URL (stored in metadata, not included in text).
        fetched_at: ISO 8601 fetch timestamp.
        max_chars: Maximum characters in output text.

    Returns:
        Dict with keys: text, title, url, extracted_at, char_count, truncated.
    """
    if not html or not isinstance(html, str) or not html.strip():
        return _empty_result(url, fetched_at)

    soup = BeautifulSoup(html, "lxml")

    # Step 1: Extract title before removing tags
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)[:500]

    # Step 2: Remove comment nodes and CDATA sections
    for node in soup.find_all(string=True):
        if isinstance(node, (Comment, CData)):
            node.extract()

    # Step 3a: Decompose container tags (tag + all descendants destroyed)
    for tag_name in _DECOMPOSE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Step 3b: Unwrap void/self-closing tags (remove tag wrapper, preserve children)
    for tag_name in _EXTRACT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.unwrap()

    # Step 4: Extract text (separator="\n" puts block elements on separate lines)
    raw_text = soup.get_text(separator="\n")

    # Step 5: Post-process
    text = _post_process_text(raw_text, max_chars=max_chars)

    return {
        "text": text,
        "title": title,
        "url": url or "",
        "extracted_at": fetched_at or _now_iso(),
        "char_count": len(text),
        "truncated": len(raw_text) > max_chars,
    }


def _post_process_text(text: str, *, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    """Clean and normalize extracted text."""
    # Step 1: Remove non-printable characters
    text = _NON_PRINTABLE_PATTERN.sub("", text)

    # Step 2: Replace tabs with spaces
    text = text.replace("\t", " ")

    # Step 3: Compress multiple spaces into single space
    text = _MULTI_SPACE_PATTERN.sub(" ", text)

    # Step 4: Deduplicate consecutive newlines (max 2)
    text = _MULTI_NEWLINE_PATTERN.sub("\n\n", text)

    # Step 5: Strip per-line whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)

    # Step 6: Strip excessive leading/trailing newlines
    text = text.strip("\n")

    # Step 7: Truncate to max_chars
    text = text[:max_chars]

    # Step 8: Final rstrip
    return text.rstrip()


def _empty_result(url: str = "", fetched_at: Optional[str] = None) -> Dict[str, Any]:
    return {
        "text": "",
        "title": "",
        "url": url or "",
        "extracted_at": fetched_at or _now_iso(),
        "char_count": 0,
        "truncated": False,
    }
