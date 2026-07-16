"""Lightweight telemetry helpers for Pixiu AI service.

Provides:
- ``SlowQueryLogger``: context manager that warns when a code block exceeds a threshold.
- ``log_request_metrics``: emit structured per-request counters after each response.
- ``RequestMetricsMiddleware``: pure-ASGI middleware that records duration + status.

These are intentionally dependency-free — they use only stdlib ``logging`` and
``time``. For production OpenTelemetry, replace the internals without changing
the call sites.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator

from core.config import settings

_logger = logging.getLogger(__name__)


@contextmanager
def slow_query_logger(
    label: str,
    threshold_ms: int | None = None,
    **meta: Any,
) -> Iterator[None]:
    """Warn if the enclosed block exceeds *threshold_ms* milliseconds.

    Usage::

        with slow_query_logger("rag_retrieve", pdf_id=pdf_id):
            results = rag.retrieve(query, top_k=8)
    """
    threshold = threshold_ms if threshold_ms is not None else settings.pixiu_slow_query_threshold_ms
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= threshold:
            _logger.warning(
                "slow_query label=%s elapsed_ms=%.1f threshold_ms=%d %s",
                label,
                elapsed_ms,
                threshold,
                " ".join(f"{k}={v}" for k, v in meta.items()),
            )


def log_request_metrics(
    path: str,
    method: str,
    status_code: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Emit a single structured log line summarising an HTTP request."""
    _logger.info(
        "request path=%s method=%s status=%d duration_ms=%.1f %s",
        path,
        method,
        status_code,
        duration_ms,
        " ".join(f"{k}={v}" for k, v in extra.items()),
    )


class RequestMetricsMiddleware:
    """Pure-ASGI middleware that logs every request with duration and status.

    Mount in app.py::

        from core.telemetry import RequestMetricsMiddleware
        app.add_middleware(RequestMetricsMiddleware)
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def _send(message: Dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            log_request_metrics(
                path=scope.get("path", ""),
                method=scope.get("method", ""),
                status_code=status_code,
                duration_ms=duration_ms,
            )
