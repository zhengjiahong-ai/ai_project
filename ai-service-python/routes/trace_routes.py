try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        JSONResponse,
    )

from services import trace_service

trace_router = APIRouter()


@trace_router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    try:
        return JSONResponse(trace_service.get_trace_summary(trace_id))
    except trace_service.TraceNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@trace_router.get("/agent-traces/{trace_id}")
async def get_agent_trace(trace_id: str):
    # Deprecated: use GET /api/traces/{trace_id} instead.
    try:
        return JSONResponse(trace_service.get_trace_summary(trace_id))
    except trace_service.TraceNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception:
        pass  # let the global exception handler produce a standardised 500
