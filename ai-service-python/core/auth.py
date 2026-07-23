"""
Optional Bearer-token authentication middleware (19-1).

When ``PIXIU_API_AUTH_TOKEN`` is set, write operations (POST/PATCH/DELETE)
on ``/api/agent-*`` paths require ``Authorization: Bearer <token>``.
Read operations (GET) and ``/api/health`` are always public.
When the token is NOT set, all requests pass through unchanged.

Usage in ``app.py``::

    from core.auth import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _get_token() -> str | None:
    try:
        from core.config import settings

        token = (settings.pixiu_api_auth_token or "").strip()
        return token or None
    except Exception:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token for write endpoints when configured."""

    async def dispatch(self, request: Request, call_next):
        token = _get_token()
        if not token:
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()

        # Always public.
        if path == "/api/health" or path.startswith("/api/shared/"):
            return await call_next(request)

        # Read-only operations are public.
        if method == "GET" or method == "HEAD" or method == "OPTIONS":
            return await call_next(request)

        # Write operations require auth.
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"status": "error", "message": "未提供认证凭据。"},
                status_code=401,
            )

        provided = auth_header[len("Bearer "):].strip()
        if provided != token:
            return JSONResponse(
                {"status": "error", "message": "认证凭据无效。"},
                status_code=401,
            )

        return await call_next(request)
