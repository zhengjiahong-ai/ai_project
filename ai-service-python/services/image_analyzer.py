"""Image analysis via VLM: downloads an image from a whitelisted URL,
encodes it as base64, sends it to a vision-capable LLM, and returns
a sanitized text description tagged with ``sourceType="image_analysis"``.
"""

from __future__ import annotations

import base64
from typing import Any

import requests

from services.safety_service import sanitize_untrusted_text
from services.url_whitelist import validate_fetch_url

# ── Constants ────────────────────────────────────────────────────────────────

MAX_IMAGE_BYTES: int = 5 * 1024 * 1024  # 5 MiB
ALLOWED_IMAGE_CONTENT_TYPES: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
})
IMAGE_DOWNLOAD_TIMEOUT: tuple[float, float] = (5.0, 15.0)  # (connect, read)
VLM_TIMEOUT: int = 60
MAX_DESCRIPTION_CHARS: int = 2000

VLM_SYSTEM_PROMPT: str = (
    "You are an image analysis assistant. "
    "Describe the image concisely and objectively. "
    "Focus on factual content: text, charts, diagrams, data, labels, and visual structure. "
    "Do not speculate beyond what is visible. "
    "Reply in the same language as the image content."
)


# ── Public API ───────────────────────────────────────────────────────────────

def analyze_image(image_url: str) -> dict[str, Any]:
    """Download *image_url*, send it to a VLM, and return a description.

    Parameters
    ----------
    image_url
        Absolute HTTPS URL of the image.  Must pass :func:`validate_fetch_url`.

    Returns
    -------
    dict
        ``status``      – ``"success"`` or ``"error"``.
        ``description`` – sanitized VLM text description (empty on error).
        ``imageUrl``    – the validated image URL.
        ``sourceType``  – always ``"image_analysis"``.
        ``error``       – human-readable error (empty on success).
    """
    # ── Validate URL ─────────────────────────────────────────────────────
    if not image_url or not isinstance(image_url, str) or not image_url.strip():
        return _error_result("Image URL cannot be empty.")
    try:
        validate_fetch_url(image_url)
    except ValueError as exc:
        return _error_result(f"URL validation failed: {exc}")

    # ── Download image ───────────────────────────────────────────────────
    try:
        resp = requests.get(
            image_url,
            headers={"User-Agent": "Pixiu-ImageAnalyzer/1.0"},
            timeout=IMAGE_DOWNLOAD_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
    except requests.Timeout:
        return _error_result("Image download timed out.")
    except requests.RequestException as exc:
        return _error_result(f"Image download failed: {exc}")

    try:
        if 300 <= resp.status_code <= 399:
            return _error_result("Image URL redirected; only direct URLs are allowed.")
        if resp.status_code >= 400:
            return _error_result(f"Image server returned HTTP {resp.status_code}.")

        # Content-Type pre-check
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            return _error_result(
                f"Unsupported image type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_CONTENT_TYPES))}."
            )

        # Size check via Content-Length
        content_length_str = resp.headers.get("Content-Length", "")
        if content_length_str:
            try:
                if int(content_length_str) > MAX_IMAGE_BYTES:
                    return _error_result(
                        f"Image size exceeds maximum of {MAX_IMAGE_BYTES} bytes."
                    )
            except (ValueError, TypeError):
                pass

        # Read image bytes with size enforcement
        chunks: list[bytes] = []
        total_bytes = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                total_bytes += len(chunk)
                if total_bytes > MAX_IMAGE_BYTES:
                    return _error_result(
                        f"Image size exceeds maximum of {MAX_IMAGE_BYTES} bytes."
                    )
                chunks.append(chunk)

        image_bytes = b"".join(chunks)
        if not image_bytes:
            return _error_result("Downloaded image is empty.")

    finally:
        resp.close()

    # ── Encode as base64 data URI ────────────────────────────────────────
    media_type = content_type or "image/png"
    data_uri = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    # ── Call VLM ─────────────────────────────────────────────────────────
    try:
        description = _call_vision_model(data_uri, media_type)
    except Exception as exc:
        return _error_result(f"VLM call failed: {exc}")

    # ── Sanitize ─────────────────────────────────────────────────────────
    description = description[:MAX_DESCRIPTION_CHARS]
    sanitized = sanitize_untrusted_text(description, max_tokens=1000)

    return {
        "status": "success",
        "description": sanitized,
        "imageUrl": image_url,
        "sourceType": "image_analysis",
        "error": "",
    }


# ── VLM Call ─────────────────────────────────────────────────────────────────

def _call_vision_model(data_uri: str, media_type: str) -> str:
    """Send the image to the vision-capable LLM and return the description text."""
    from llm.client import get_llm

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": VLM_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please describe this image in detail. Include any visible text, "
                            "data, labels, chart elements, or key visual information.",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                },
            ],
        },
    ]

    llm = get_llm()
    result = llm.invoke(messages=messages, temperature=0.1)
    return result.content.strip()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _error_result(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "description": "",
        "imageUrl": "",
        "sourceType": "",
        "error": message,
    }
