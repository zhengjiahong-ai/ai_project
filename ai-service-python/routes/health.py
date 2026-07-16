"""Health-check endpoint for container orchestration and monitoring."""
from __future__ import annotations

import time
import logging
from typing import Any, Dict

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover — test-only fallback
    from routes.api import APIRouter, JSONResponse  # type: ignore[assignment]

from rag.store import is_rag_available, get_rag_initialization_error

_logger = logging.getLogger(__name__)
_start_time = time.time()

router = APIRouter()

GROBID_SERVER_URL = "http://grobid:8070"


async def _check_grobid() -> Dict[str, Any]:
    """Lightweight liveness check against the GROBID server."""
    try:
        import urllib.request

        req = urllib.request.Request(
            f"{GROBID_SERVER_URL}/api/isalive",
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if 200 <= resp.status < 400:
                return {"status": "ok", "message": "GROBID is reachable."}
            return {
                "status": "degraded",
                "message": f"GROBID returned HTTP {resp.status}.",
            }
    except Exception as exc:
        return {"status": "unavailable", "message": f"GROBID unreachable: {exc}"}


def _check_rag() -> Dict[str, Any]:
    if is_rag_available():
        return {"status": "ok", "message": "RAG backend is ready."}
    err = get_rag_initialization_error()
    return {
        "status": "degraded",
        "message": f"RAG unavailable: {err or 'not initialized'}",
    }


@router.get("/health")
async def health_check():
    grobid = await _check_grobid()
    rag = _check_rag()

    checks = {"grobid": grobid, "rag": rag}

    # Compute aggregate status.
    statuses = {c["status"] for c in checks.values()}
    if "unavailable" in statuses:
        aggregate = "degraded"
    elif "degraded" in statuses:
        aggregate = "degraded"
    else:
        aggregate = "ok"

    return JSONResponse(
        {
            "status": aggregate,
            "checks": checks,
            "uptime_seconds": round(time.time() - _start_time, 1),
        }
    )
