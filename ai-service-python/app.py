from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.logging_config import configure_logging
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

    @app.on_event("startup")
    async def startup_event() -> None:
        _logger.info("Application startup: running warmup...")
        startup_warmup()
        try:
            from services.monitor_scheduler import start_scheduler
            start_scheduler()
        except Exception:
            pass

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        try:
            from services.monitor_scheduler import stop_scheduler
            stop_scheduler()
        except Exception:
            pass

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"message": "AI Paper Assistant Service is Running"}

    app.include_router(api_router)
    return app


app = create_app()
