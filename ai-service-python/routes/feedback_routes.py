"""
User feedback and error reporting endpoint.

Accepts sanitised error reports from the frontend and logs them
as structured JSON for operational visibility.  No sensitive data
(API keys, full page text, raw URLs) is accepted by design.
"""
import logging
import re
from datetime import datetime, timezone

try:
    from fastapi import APIRouter, Request
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import APIRouter, BaseModel, Field, Request

logger = logging.getLogger("pixiu.feedback")

router = APIRouter(tags=["feedback"])

# ── Patterns to strip ──────────────────────────────────────────────────────
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(?:api[_-]?key|token|secret|auth)\s*[:=]\s*\S+", re.IGNORECASE)


def _sanitize(value: str) -> str:
    """Remove URLs, apparent API keys, and truncate long text."""
    if not value:
        return value
    cleaned = URL_PATTERN.sub("[URL]", value)
    cleaned = API_KEY_PATTERN.sub("[CREDENTIAL]", cleaned)
    return cleaned[:2000]  # safety cap


class FeedbackPayload(BaseModel):
    error: str = Field(default="", max_length=2000)
    component_stack: str = Field(default="", alias="componentStack", max_length=4000)
    area: str = Field(default="", max_length=200)
    timestamp: str = Field(default="", max_length=64)


@router.post("/feedback")
async def submit_feedback(payload: FeedbackPayload, request: Request):
    entry = {
        "error": _sanitize(payload.error),
        "componentStack": _sanitize(payload.component_stack),
        "area": payload.area[:200] if payload.area else "",
        "clientTimestamp": payload.timestamp or datetime.now(timezone.utc).isoformat(),
        "clientIp": request.client.host if request.client else "unknown",
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }
    logger.warning("feedback.received", extra={"feedback": entry})
    return {"status": "received"}
