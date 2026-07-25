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

research_router = APIRouter()


@research_router.post("/research-tasks")
async def create_research_task(request: ResearchTaskCreateRequest):
    try:
        return JSONResponse(research_task_service.create_research_task(request))
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


@research_router.get("/research-tasks/{task_id}")
async def get_research_task(task_id: str):
    try:
        return JSONResponse(research_task_service.get_research_task(task_id))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@research_router.post("/research-tasks/{task_id}/cancel")
async def cancel_research_task(task_id: str):
    try:
        return JSONResponse(research_task_service.cancel_research_task(task_id))
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
