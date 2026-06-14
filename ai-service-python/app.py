from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.api import router as api_router
from services.analysis_service import startup_warmup


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
        startup_warmup()

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"message": "AI Paper Assistant Service is Running"}

    app.include_router(api_router)
    return app


app = create_app()
