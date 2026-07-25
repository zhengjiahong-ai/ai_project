"""Structured chart understanding — extracts quantitative data from chart images.

Goes beyond descriptive VLM output to produce machine-readable JSON:
chart type, axis labels, data points with error bars, legend items, and captions.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

import requests

from services.safety_service import sanitize_untrusted_text
from services.url_whitelist import validate_fetch_url

# ── Constants ────────────────────────────────────────────────────────────────

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
DOWNLOAD_TIMEOUT = (5.0, 15.0)
VLM_TIMEOUT = 45  # chart analysis needs more thinking time

CHART_PROMPT = (
    "Analyze this chart image and extract ALL quantitative information. "
    "Return a JSON object with these fields:\n"
    "- chartType: one of [bar, line, scatter, pie, heatmap, boxplot, other]\n"
    "- title: the chart title text\n"
    "- xAxis: {label, type(numeric|categorical|time), values: [...]}  (for bar/line/scatter/boxplot)\n"
    "- yAxis: {label, unit, scale(linear|log)}\n"
    "- dataSeries: [{name, color, dataPoints: [{x, y, yError}]}]\n"
    "- legend: [{label, color}]\n"
    "- caption: any figure caption text\n"
    "- summary: one-sentence description of the main finding shown\n\n"
    "IMPORTANT: Extract numerical values precisely. If error bars are visible, "
    "estimate yError for each data point. If values cannot be read, use null. "
    "Reply with ONLY the JSON, no markdown fences."
)


# ── Public API ───────────────────────────────────────────────────────────────

def extract_chart_data(image_url: str) -> dict[str, Any]:
    """Download *image_url*, send to VLM, return structured chart data."""
    if not image_url or not isinstance(image_url, str) or not image_url.strip():
        return _error("Image URL cannot be empty.")
    try:
        validate_fetch_url(image_url)
    except ValueError as exc:
        return _error(f"URL validation failed: {exc}")

    # Download
    try:
        resp = requests.get(
            image_url,
            headers={"User-Agent": "Pixiu-ChartAnalyzer/1.0"},
            timeout=DOWNLOAD_TIMEOUT, allow_redirects=False, stream=True,
        )
    except requests.Timeout:
        return _error("Image download timed out.")
    except requests.RequestException as exc:
        return _error(f"Download failed: {exc}")

    try:
        if resp.status_code >= 400:
            return _error(f"HTTP {resp.status_code}")
        ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ct not in ALLOWED_TYPES:
            return _error(f"Unsupported type: {ct}")
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(65536):
            if chunk:
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return _error("Image too large")
                chunks.append(chunk)
        image_bytes = b"".join(chunks)
    finally:
        resp.close()

    data_uri = f"data:{ct or 'image/png'};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    # VLM call
    try:
        from llm.client import get_llm

        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": CHART_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]},
        ]

        def _call():
            return get_llm().invoke(messages=messages, temperature=0.0)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            result = future.result(timeout=VLM_TIMEOUT)
        raw = (result.content or "").strip()
    except (FutureTimeout, Exception):
        return _error("VLM call failed")

    # Parse JSON
    try:
        raw = raw.split("```json")[-1].split("```")[0].strip() if "```" in raw else raw
        data = json.loads(raw)
        data["imageUrl"] = image_url
        data["status"] = "success"
        data["error"] = ""
        return data
    except (json.JSONDecodeError, TypeError):
        return {"status": "success", "imageUrl": image_url, "chartType": "other",
                "title": "", "summary": sanitize_untrusted_text(raw, max_tokens=200),
                "dataSeries": [], "error": ""}


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "chartType": "", "title": "", "dataSeries": [],
            "imageUrl": "", "summary": "", "error": message}
