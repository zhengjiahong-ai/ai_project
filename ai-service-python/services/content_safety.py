"""Fetched web content safety validation.

Performs prompt injection detection, content safety grading,
URL trust marking, and token-bounded text truncation.
"""
from __future__ import annotations

from typing import Any

from services.safety_service import detect_prompt_injection

# ---- Safety grades ----

SAFE = "safe"
FLAGGED = "flagged"
BLOCKED = "blocked"

# ---- URL trust tiers ----

TRUST_HIGH = "high"
TRUST_MEDIUM = "medium"
TRUST_LOW = "low"
TRUST_UNKNOWN = "unknown"

# ---- Blocked keywords (case-insensitive substring match) ----

_BLOCKED_KEYWORDS = (
    "malware", "phishing", "pornography", "porn", "xxx",
    "violence", "gore", "exploit kit", "botnet", "ransomware",
)

# ---- Token clamp defaults ----

_DEFAULT_MAX_TOKENS = 4000
_TOKEN_TO_CHAR_RATIO = 4  # rough estimate: 1 token ≈ 4 chars


def sanitize_fetched_web_content(
    text: Any,
    *,
    url: str = "",
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """Validate safety of fetched web page content.

    Args:
        text: Decoded text content from a fetched web page (str or None).
        url: Source URL (for trust-tier classification).
        max_tokens: Token limit for truncation (default 4000).

    Returns:
        Dict with keys: text, grade, trust, flags, truncated.
    """
    if not text or not isinstance(text, str) or not text.strip():
        return {
            "text": "",
            "grade": SAFE,
            "trust": _classify_url_trust(url),
            "flags": [],
            "truncated": False,
        }

    # Step 1: Prompt injection detection (reuse safety_service)
    injection_result = detect_prompt_injection(text)
    injection_flags = list(injection_result.get("flags") or [])

    # Step 2: Blocked content keyword check
    text_lower = text.lower()
    blocked_matches = [kw for kw in _BLOCKED_KEYWORDS if kw in text_lower]

    # Step 3: Determine grade
    if blocked_matches:
        return {
            "text": "",
            "grade": BLOCKED,
            "trust": _classify_url_trust(url),
            "flags": injection_flags + ["blocked_content"],
            "truncated": False,
        }

    if injection_flags:
        grade = FLAGGED
    else:
        grade = SAFE

    # Step 4: URL trust classification
    trust = _classify_url_trust(url)

    # Step 5: Token-bounded truncation
    max_chars = max_tokens * _TOKEN_TO_CHAR_RATIO
    truncated = len(text) > max_chars
    if truncated:
        text = _clamp_text(text, max_tokens=max_tokens)

    return {
        "text": text,
        "grade": grade,
        "trust": trust,
        "flags": injection_flags,
        "truncated": truncated,
    }


def _classify_url_trust(url: str) -> str:
    """Classify URL into trust tier based on domain patterns."""
    from urllib.parse import urlparse

    if not url:
        return TRUST_UNKNOWN

    hostname = ""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
    except Exception:
        return TRUST_UNKNOWN

    if not hostname:
        return TRUST_UNKNOWN

    # High trust: .gov, .edu, academic publishers
    if hostname.endswith(".gov") or hostname.endswith(".edu"):
        return TRUST_HIGH
    for domain in (
        "nature.com", "science.org", "ieee.org", "springer.com",
        "sciencedirect.com", "cell.com", "nejm.org", "thelancet.com",
        "jamanetwork.com", "wiley.com", "sagepub.com", "oup.com",
        "cambridge.org", "mit.edu", "pnas.org", "bmj.com",
        "plos.org", "frontiersin.org", "mdpi.com", "elifesciences.org",
        "arxiv.org", "semanticscholar.org", "crossref.org", "doi.org",
    ):
        if domain in hostname:
            return TRUST_HIGH

    # Medium trust: Wikipedia, GitHub, news
    for domain in (
        "wikipedia.org", "wikibooks.org", "github.com", "gitlab.com",
        "bitbucket.org", "britannica.com", "reuters.com", "apnews.com",
        "bbc.com", "bbc.co.uk", "npr.org", "scientificamerican.com",
    ):
        if domain in hostname:
            return TRUST_MEDIUM

    # Low trust: commercial .com, .co, .net
    if hostname.endswith(".com") or hostname.endswith(".co") or hostname.endswith(".net"):
        return TRUST_LOW

    return TRUST_UNKNOWN


def _clamp_text(text: str, *, max_tokens: int = _DEFAULT_MAX_TOKENS) -> str:
    """Truncate text to max_tokens using tiktoken, with char-ratio fallback."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens]
        return enc.decode(truncated_tokens)
    except Exception:
        max_chars = max_tokens * _TOKEN_TO_CHAR_RATIO
        return text[:max_chars]
