try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        JSONResponse,
    )

from schemas.requests import (
    ResearchFinalReviewRequest,
    ResearchPlanReviewRequest,
    ResearchTaskBriefPreviewRequest,
    ResearchTaskCreateRequest,
)
from services import research_task_service
from services.research_engine_dispatch import get_dispatcher
from services.deep_research.contracts import DeepResearchError, RunNotFoundError

research_router = APIRouter()


@research_router.post("/research-tasks")
async def create_research_task(request: dict):
    try:
        payload = request.model_dump() if hasattr(request, "model_dump") else request
        return JSONResponse(get_dispatcher().create(payload))
    except DeepResearchError as error:
        return _v2_error(error)
    except ValueError:
        return JSONResponse({"status": "error", "message": "研究请求格式无效"}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.post("/research-tasks/brief-preview")
async def preview_research_brief(request: ResearchTaskBriefPreviewRequest):
    try:
        return JSONResponse(research_task_service.preview_research_brief(request))
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.get("/research-tasks/latest")
async def get_latest_research_task(pdfId: str):
    try:
        return JSONResponse(research_task_service.get_latest_research_task(pdfId))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.get("/research-tasks/capabilities")
async def research_capabilities():
    from services.deep_research.external import capabilities
    return JSONResponse({"status": "success", **capabilities()})


@research_router.get("/research-tasks/{task_id}")
async def get_research_task(task_id: str):
    try:
        return JSONResponse(get_dispatcher().get(task_id))
    except DeepResearchError as error:
        return _v2_error(error)
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.post("/research-tasks/{task_id}/resume")
async def resume_research_task(task_id: str, request: dict | None = None):
    try:
        return JSONResponse(get_dispatcher().action(task_id, "resume", request))
    except DeepResearchError as error:
        return _v2_error(error)
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except research_task_service.ResearchReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)


@research_router.post("/research-tasks/{task_id}/cancel")
async def cancel_research_task(task_id: str, request: dict | None = None):
    try:
        return JSONResponse(get_dispatcher().action(task_id, "cancel", request))
    except DeepResearchError as error:
        return _v2_error(error)
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.post("/research-tasks/{task_id}/plan-review")
async def review_research_plan(task_id: str, request: ResearchPlanReviewRequest):
    try:
        return JSONResponse(research_task_service.review_research_plan(task_id, request))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except research_task_service.ResearchReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception:
        pass  # let the global exception handler produce a standardised 500


def _v2_error(error: DeepResearchError):
    status = 404 if isinstance(error, RunNotFoundError) else int(error.details.get("status_code", 409))
    if error.code in {"missing_request_id", "missing_workspace_task_id", "missing_operation_key", "unsupported_engine", "unsupported_action"}:
        status = 422
    return JSONResponse({"status": "error", "errorCode": error.code, "message": str(error)}, status_code=status)


async def _v2_action(task_id: str, name: str, request: dict):
    try:
        return JSONResponse(get_dispatcher().action(task_id, name, request))
    except DeepResearchError as error:
        return _v2_error(error)


@research_router.post("/research-tasks/{task_id}/pause")
async def pause_research_task(task_id: str, request: dict):
    return await _v2_action(task_id, "pause", request)


@research_router.post("/research-tasks/{task_id}/clarify")
async def clarify_research_task(task_id: str, request: dict):
    return await _v2_action(task_id, "clarify", request)


@research_router.post("/research-tasks/{task_id}/plan")
async def adjust_research_plan(task_id: str, request: dict):
    return await _v2_action(task_id, "plan", request)


@research_router.post("/research-tasks/{task_id}/continue")
async def continue_research_task(task_id: str, request: dict):
    return await _v2_action(task_id, "continue", request)


@research_router.get("/research-tasks/{task_id}/sources")
async def get_research_sources(task_id: str):
    try:
        return JSONResponse(get_dispatcher().detail(task_id, "sources"))
    except DeepResearchError as error:
        return _v2_error(error)


@research_router.get("/research-tasks/{task_id}/events")
async def get_research_events(task_id: str):
    try:
        return JSONResponse(get_dispatcher().detail(task_id, "events"))
    except DeepResearchError as error:
        return _v2_error(error)


@research_router.get("/research-tasks/{task_id}/sources/{source_id}/export")
async def export_research_source(task_id: str, source_id: str):
    try:
        from services.deep_research.external import export_saved_source
        dispatcher = get_dispatcher()
        if not dispatcher._is_v2(task_id):
            raise DeepResearchError("unsupported_action", "此来源不属于新版研究")
        return JSONResponse({"status": "success", "source": export_saved_source(dispatcher.facade._repo, task_id, source_id)})
    except DeepResearchError as error:
        return _v2_error(error)


@research_router.post("/research-tasks/{task_id}/final-review")
async def review_research_final(task_id: str, request: ResearchFinalReviewRequest):
    try:
        return JSONResponse(research_task_service.review_research_final(task_id, request))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except research_task_service.ResearchReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception:
        pass  # let the global exception handler produce a standardised 500
