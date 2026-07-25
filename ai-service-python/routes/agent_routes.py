try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        JSONResponse,
    )

from schemas.requests import (
    AgentClarificationRequest,
    AgentFinalReviewRequest,
    AgentPlanReviewRequest,
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentRunCreateRequest,
    AgentRunFinalReviewRequest,
    AgentRunPlanReviewRequest,
    AgentTaskCreateRequest,
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


# ── LangGraph Agent Graph routes ─────────────────────────────────────────


@agent_router.post("/agent-graph")
async def create_agent_graph(request: AgentRunCreateRequest):
    """Create a LangGraph agent research task and run to the first interrupt.

    The graph stops at plan_review (or final_review if plan already approved).
    Returns the current graph state as an API response.
    """
    import uuid as _uuid

    from services.agent_langgraph import (
        agent_graph_state_to_response,
        run_agent_graph,
    )

    thread_id = str(_uuid.uuid4())
    try:
        state = run_agent_graph(
            prompt=request.prompt,
            paper_ids=request.focusedPaperIds,
            constraints=request.constraints or "",
            allow_external_search=request.allowExternalSearch,
            allow_web_search=request.allowWebSearch,
            allow_iterative_search=request.allowIterativeSearch,
            domain=request.domain or "",
            thread_id=thread_id,
        )
        interrupted = state.get("status", "") == "awaiting_plan_review" or not state.get("plan_approved")
        response = agent_graph_state_to_response(state, interrupted=interrupted)
        response["threadId"] = thread_id
        return JSONResponse({"status": "success", "task": response})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.post("/agent-graph/{thread_id}/resume")
async def resume_agent_graph_route(thread_id: str, request):
    """Resume a LangGraph agent graph after human review.

    The body should contain the resume data: for plan review,
    ``{"plan_approved": True, "plan_review_notes": "...", ...}``;
    for final review,
    ``{"final_approved": True, "final_review_notes": "...", ...}``.
    """
    from services.agent_langgraph import (
        agent_graph_state_to_response,
        resume_agent_graph,
    )

    try:
        resume_data = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON body."}, status_code=400)

    try:
        state = resume_agent_graph(resume_data, thread_id=thread_id)
        interrupted = (
            state.get("status", "") == "awaiting_plan_review"
            or state.get("status", "") == "awaiting_final_review"
            or (not state.get("plan_approved") and not state.get("final_approved"))
        )
        response = agent_graph_state_to_response(state, interrupted=interrupted)
        response["threadId"] = thread_id
        return JSONResponse({"status": "success", "task": response})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/agent-graph/{thread_id}")
async def get_agent_graph(thread_id: str):
    """Get the current state of a LangGraph agent graph by thread ID."""
    from services.agent_langgraph import (
        agent_graph_state_to_response,
        build_agent_graph,
    )

    try:
        graph = build_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        if state is None or state.values is None or not state.values:
            return JSONResponse({"status": "error", "message": "Graph state not found."}, status_code=404)
        graph_state = state.values
        interrupted = len(state.next or []) > 0
        response = agent_graph_state_to_response(graph_state, interrupted=interrupted)
        response["threadId"] = thread_id
        return JSONResponse({"status": "success", "task": response})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


# ── 16-4: Share routes ──────────────────────────────────────────────────────

@agent_router.post("/agent-projects/{project_id}/share")
async def create_project_share(project_id: str):
    """Create a read-only share token for a project's latest report (16-4)."""
    try:
        from services.agent_state_repository import AgentStateRepository
        from services.agent_workspace_service import build_workspace_view
        from services.share_service import get_share_service

        repo = AgentStateRepository()
        workspace = build_workspace_view(repo, project_id)
        if not workspace or not workspace.get("project"):
            return JSONResponse({"status": "error", "message": "Project not found."}, status_code=404)

        project = workspace["project"]
        artifacts = workspace.get("latestArtifacts") or {}
        report = artifacts.get("draftReport") or ""
        if not report:
            return JSONResponse({"status": "error", "message": "No report available to share."}, status_code=400)

        share_svc = get_share_service()
        result = share_svc.create_share(project_id, report, project.get("title", ""))
        return JSONResponse({"status": "success", "share": result})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@agent_router.get("/shared/{token}")
async def get_shared_report(token: str):
    """Read a shared project report by token (read-only, no auth) (16-4)."""
    try:
        from services.share_service import get_share_service

        share_svc = get_share_service()
        share = share_svc.get_share(token)
        if share is None:
            return JSONResponse({"status": "error", "message": "分享链接不存在或已过期。"}, status_code=404)

        return JSONResponse({
            "status": "success",
            "share": {
                "projectId": share["projectId"],
                "projectTitle": share["projectTitle"],
                "report": share["report"],
                "expiresAt": share["expiresAt"],
                "readOnly": True,
            },
        })
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)

