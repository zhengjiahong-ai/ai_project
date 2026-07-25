try:
    from fastapi import APIRouter
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import APIRouter

from routes.agent_routes import agent_router
from routes.code_execution_routes import code_execution_router
from routes.feedback_routes import router as feedback_router
from routes.monitor_routes import monitor_router
from routes.rag_routes import rag_router
from routes.reading_routes import reading_router
from routes.research_routes import research_router
from routes.trace_routes import trace_router

router = APIRouter(prefix="/api")
router.include_router(code_execution_router)
router.include_router(feedback_router)
router.include_router(reading_router)
router.include_router(agent_router)
router.include_router(research_router)
router.include_router(monitor_router)
router.include_router(rag_router)
router.include_router(trace_router)
