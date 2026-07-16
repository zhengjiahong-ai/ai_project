try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        JSONResponse,
    )

from schemas.requests import (
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentRunCreateRequest,
    AgentClarificationRequest,
    AgentRunFinalReviewRequest,
    AgentRunPlanReviewRequest,
    AgentTaskCreateRequest,
    AgentFinalReviewRequest,
    AgentPlanReviewRequest,
)
from services import (
    agent_artifact_service,
    agent_project_service,
    agent_review_service,
    agent_run_service,
    agent_timeline_service,
    agent_workspace_service,
)

agent_router = APIRouter()


@agent_router.post("/agent-projects")
async def create_agent_project(request: AgentProjectCreateRequest):
    try:
        return JSONResponse(agent_project_service.create_agent_project(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-projects")
async def list_agent_projects():
    try:
        return JSONResponse(agent_project_service.list_agent_projects())
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-projects/{project_id}")
async def get_agent_project(project_id: str):
    try:
        return JSONResponse(agent_project_service.get_agent_project(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.patch("/agent-projects/{project_id}")
async def update_agent_project(project_id: str, request: AgentProjectUpdateRequest):
    try:
        return JSONResponse(agent_project_service.update_agent_project(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.delete("/agent-projects/{project_id}")
async def delete_agent_project(project_id: str):
    try:
        return JSONResponse(agent_project_service.delete_agent_project(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-projects/{project_id}/papers")
async def add_project_papers(project_id: str, request: AgentProjectPapersRequest):
    try:
        return JSONResponse(agent_project_service.add_project_papers(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.delete("/agent-projects/{project_id}/papers/{pdf_id}")
async def remove_project_paper(project_id: str, pdf_id: str):
    try:
        return JSONResponse(agent_project_service.remove_project_paper(project_id, pdf_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-projects/{project_id}/tasks")
async def create_agent_task(project_id: str, request: AgentTaskCreateRequest):
    try:
        return JSONResponse(agent_project_service.create_agent_task(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-projects/{project_id}/runs")
async def create_agent_run(project_id: str, request: AgentRunCreateRequest):
    try:
        return JSONResponse(agent_run_service.create_run(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-projects/{project_id}/tasks")
async def list_agent_project_tasks(project_id: str, limit: int = 20):
    try:
        return JSONResponse(agent_project_service.list_agent_project_tasks(project_id, limit=limit))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-projects/{project_id}/workspace")
async def get_agent_workspace(project_id: str):
    try:
        return JSONResponse(agent_workspace_service.get_workspace(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-projects/{project_id}/tasks/latest")
async def get_latest_agent_task(project_id: str):
    try:
        return JSONResponse(agent_project_service.get_latest_agent_task(project_id))
    except (agent_project_service.AgentProjectNotFoundError, agent_project_service.AgentTaskNotFoundError) as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-runs/{run_id}")
async def get_agent_run(run_id: str):
    try:
        return JSONResponse(agent_run_service.get_run(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-runs/{run_id}/artifacts")
async def get_agent_run_artifacts(run_id: str):
    try:
        return JSONResponse(agent_artifact_service.get_artifacts(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-runs/{run_id}/timeline")
async def get_agent_run_timeline(run_id: str):
    try:
        return JSONResponse(agent_timeline_service.get_timeline(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-tasks/{task_id}")
async def get_agent_task(task_id: str):
    try:
        return JSONResponse(agent_project_service.get_agent_task(task_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-tasks/{task_id}/cancel")
async def cancel_agent_task(task_id: str):
    try:
        return JSONResponse(agent_project_service.cancel_agent_task(task_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-runs/{run_id}/plan-review")
async def review_agent_run_plan(run_id: str, request: AgentRunPlanReviewRequest):
    try:
        return JSONResponse(agent_review_service.review_plan(run_id, request))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except agent_project_service.AgentReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-tasks/{task_id}/plan-review")
async def review_agent_plan(task_id: str, request: AgentPlanReviewRequest):
    try:
        return JSONResponse(agent_project_service.review_agent_plan(task_id, request))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except agent_project_service.AgentReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-runs/{run_id}/final-review")
async def review_agent_run_final(run_id: str, request: AgentRunFinalReviewRequest):
    try:
        return JSONResponse(agent_review_service.review_final(run_id, request))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except agent_project_service.AgentReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-runs/{run_id}/clarification")
async def answer_agent_clarification(run_id: str, request: AgentClarificationRequest):
    try:
        return JSONResponse(agent_review_service.answer_clarification(run_id, request))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except agent_project_service.AgentReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-tasks/{task_id}/final-review")
async def review_agent_final(task_id: str, request: AgentFinalReviewRequest):
    try:
        return JSONResponse(agent_project_service.review_agent_final(task_id, request))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except agent_project_service.AgentReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
