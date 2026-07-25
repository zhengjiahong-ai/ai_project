"""
In-memory token-bucket rate limiter (15-3).

No Redis or external dependency required.  Buckets are keyed by client IP +
route prefix, with defaults tuned for a single-user research workstation.

Configuration (via environment / ``core.config.Settings``):
* ``PIXIU_RATE_LIMIT_ENABLED`` — ``true`` (default) to enable.
* ``PIXIU_RATE_LIMIT_GLOBAL_RPM`` — global requests/min/IP (default ``60``).
* ``PIXIU_RATE_LIMIT_AGENT_RPM`` — agent task creation (default ``10``).
* ``PIXIU_RATE_LIMIT_CHAT_RPM`` — chat / explain (default ``30``).
* ``PIXIU_RATE_LIMIT_TRANSLATE_RPM`` — page translation (default ``10``).

Usage in ``app.py``::

    from core.rate_limiter import RateLimiterMiddleware
    app.add_middleware(RateLimiterMiddleware)
"""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _get_settings():
    try:
        from core.config import settings

        return settings
    except Exception:
        return None


def _client_ip(request: Request) -> str:
    """Extract the best-guess client IP, preferring X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    host = request.client.host if request.client else "unknown"
    return host or "unknown"


def _route_bucket(request: Request) -> str:
    """Map a request path to a rate-limit bucket name."""
    path = request.url.path
    if path.startswith("/api/agent-") and ("tasks" in path or "runs" in path):
        return "agent"
    if "/chat" in path or "/explain" in path or "/socratic" in path:
        return "chat"
    if "/translate" in path:
        return "translate"
    return "global"


class TokenBucket:
    """Simple token bucket."""

    def __init__(self, rate_per_minute: int, burst: int = 0) -> None:
        self.rate = rate_per_minute
        self.burst = burst or max(1, rate_per_minute // 2)
        self.tokens = float(self.burst)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill = elapsed * (self.rate / 60.0)
        self.tokens = min(float(self.burst), self.tokens + refill)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True, 0.0

        # Estimate how long until a token is available.
        wait = (tokens - self.tokens) / (self.rate / 60.0) if self.rate > 0 else 60.0
        return False, round(wait, 1)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies per-IP + per-bucket rate limiting."""

    def __init__(self, app, **kwargs: Any) -> None:
        super().__init__(app)
        settings = _get_settings()
        self._enabled = str(
            settings.pixiu_rate_limit_enabled if settings else "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        self._buckets: dict[str, TokenBucket] = {}
        self._rates: dict[str, int] = {
            "global": int(settings.pixiu_rate_limit_global_rpm) if settings else 60,
            "agent": int(settings.pixiu_rate_limit_agent_rpm) if settings else 10,
            "chat": int(settings.pixiu_rate_limit_chat_rpm) if settings else 30,
            "translate": int(settings.pixiu_rate_limit_translate_rpm) if settings else 10,
        }

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        # Health check is exempt.
        if request.url.path == "/api/health":
            return await call_next(request)

        ip = _client_ip(request)
        bucket_name = _route_bucket(request)
        key = f"{ip}:{bucket_name}"

        if key not in self._buckets:
            self._buckets[key] = TokenBucket(self._rates.get(bucket_name, 60))
        allowed, retry_after = self._buckets[key].consume()

        if not allowed:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "请求过于频繁，请稍后重试。",
                    "retryAfter": round(retry_after, 1),
                },
                status_code=429,
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )

        return await call_next(request)
