from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.logging_config import configure_logging
from core.error_responses import error_response, EXCEPTION_STATUS_MAP
from routes.api import router as api_router
from services.analysis_service import startup_warmup

configure_logging()

import logging

_logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI()
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

    @app.on_event("startup")
    async def startup_event() -> None:
        _logger.info("Application startup: running warmup...")
        startup_warmup()
        try:
            from services.monitor_scheduler import start_scheduler

            start_scheduler()
        except Exception:
            _logger.error(
                "Failed to start monitor scheduler",
                exc_info=True,
            )

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        try:
            from services.monitor_scheduler import stop_scheduler

            stop_scheduler()
        except Exception:
            _logger.error(
                "Failed to stop monitor scheduler",
                exc_info=True,
            )

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"message": "AI Paper Assistant Service is Running"}

    app.include_router(api_router)
    return app


app = create_app()
