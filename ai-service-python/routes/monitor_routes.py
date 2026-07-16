try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        JSONResponse,
    )

from schemas.requests import ResearchMonitorCreateRequest
from services import research_monitor

monitor_router = APIRouter()


@monitor_router.post("/research-monitors")
async def create_monitor_route(request: ResearchMonitorCreateRequest):
    try:
        return JSONResponse(research_monitor.create_monitor(
            question=request.question,
            sources=request.sources or ["arxiv"],
            frequency=request.frequency or "manual",
        ))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@monitor_router.get("/research-monitors")
async def list_monitors_route():
    try:
        monitors = research_monitor.list_monitors()
        serializable = []
        for m in monitors:
            row = {}
            for k in m.keys():
                row[k] = m[k]
            serializable.append(row)
        return JSONResponse({"status": "success", "monitors": serializable})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@monitor_router.get("/research-monitors/{monitor_id}/check")
async def check_monitor_route(monitor_id: str):
    try:
        return JSONResponse(research_monitor.check_new_publications(monitor_id))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@monitor_router.get("/research-monitors/{monitor_id}/digest")
async def digest_monitor_route(monitor_id: str):
    try:
        return JSONResponse(research_monitor.get_monitor_digest(monitor_id))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@monitor_router.delete("/research-monitors/{monitor_id}")
async def deactivate_monitor_route(monitor_id: str):
    try:
        ok = research_monitor.deactivate_monitor(monitor_id)
        return JSONResponse({"status": "success" if ok else "error", "monitorId": monitor_id, "message": "" if ok else "Monitor not found."})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
