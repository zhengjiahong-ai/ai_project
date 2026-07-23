from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging_config import configure_logging
from core.error_responses import error_response, EXCEPTION_STATUS_MAP
from routes.api import router as api_router
from routes.health import router as health_router
from services.analysis_service import startup_warmup

configure_logging()

import logging

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    # ── startup ───────────────────────────────────────────────────────
    _logger.info("Application startup: running warmup...")
    startup_warmup()
    try:
        from services.monitor_scheduler import start_scheduler

        start_scheduler()
        _logger.info("Monitor scheduler started.")
    except Exception:
        _logger.error("Failed to start monitor scheduler", exc_info=True)

    yield

    # ── shutdown ──────────────────────────────────────────────────────
    try:
        from services.monitor_scheduler import stop_scheduler

        stop_scheduler()
        _logger.info("Monitor scheduler stopped.")
    except Exception:
        _logger.error("Failed to stop monitor scheduler", exc_info=True)


def create_app() -> FastAPI:
    app = FastAPI(lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 15-3: rate limiter middleware ─────────────────────────────────
    try:
        from core.rate_limiter import RateLimiterMiddleware

        app.add_middleware(RateLimiterMiddleware)
    except Exception:
        pass

    # ── global exception handler ──────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        for exc_type, (status_code, error_code) in EXCEPTION_STATUS_MAP.items():
            if isinstance(exc, exc_type):
                _logger.error(
                    "%s (status=%d): %s",
                    error_code,
                    status_code,
                    exc,
                    exc_info=True,
                )
                return JSONResponse(
                    error_response(status_code, error_code, str(exc)),
                    status_code=status_code,
                )

        # Unmapped / unexpected exception — hide internal details.
        _logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            error_response(500, "internal_error", "服务器内部错误，请稍后重试。"),
            status_code=500,
        )

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"message": "AI Paper Assistant Service is Running"}

    app.include_router(health_router)
    app.include_router(api_router)

    # ── MCP SSE transport (conditional mount) ──────────────────────────
    if settings.pixiu_mcp_enabled and settings.pixiu_mcp_transport == "sse":
        try:
            from mcp_adapter.server import build_sse_app

            _logger.info(
                "Mounting MCP SSE transport at /mcp (auth=%s)",
                "required" if settings.pixiu_mcp_auth_token else "disabled",
            )
            app.mount(
                "/mcp",
                build_sse_app(
                    require_auth=bool(settings.pixiu_mcp_auth_token.strip()),
                ),
            )
        except ImportError as exc:
            _logger.warning(
                "MCP SSE transport could not be mounted: %s. "
                "Install starlette and mcp dependencies.",
                exc,
            )

    return app


app = create_app()
