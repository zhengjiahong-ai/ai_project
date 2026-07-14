from typing import Annotated

try:
    from fastapi import APIRouter, Body, File, UploadFile
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:
    class UploadFile:  # pragma: no cover - test-only fallback
        filename: str = ""

        async def read(self, *_args, **_kwargs):
            return b""

    class JSONResponse:  # pragma: no cover - test-only fallback
        def __init__(self, content, status_code=200):
            import json as _json

            self.status_code = status_code
            self.body = _json.dumps(content, ensure_ascii=False).encode("utf-8")

    class _Route:  # pragma: no cover - test-only fallback
        def __init__(self, path, methods):
            self.path = path
            self.methods = methods

    class APIRouter:  # pragma: no cover - test-only fallback
        def __init__(self, prefix=""):
            self.prefix = prefix
            self.routes = []

        def _register(self, path, method, func):
            self.routes.append(_Route(f"{self.prefix}{path}", {method}))
            return func

        def post(self, path):
            return lambda func: self._register(path, "POST", func)

        def get(self, path):
            return lambda func: self._register(path, "GET", func)

        def patch(self, path):
            return lambda func: self._register(path, "PATCH", func)

        def delete(self, path):
            return lambda func: self._register(path, "DELETE", func)

    def Body(default=None):
        return default

    def File(default=None):
        return default

from schemas.requests import (
    BackgroundKnowledgeRequest,
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
    ChatRequest,
    CodeExecutionJobCreateRequest,
    CodeExecutionReviewRequest,
    CodePublicationReviewRequest,
    DeepAnalysisRequest,
    PageTranslationRequest,
    ResearchTaskBriefPreviewRequest,
    ResearchTaskCreateRequest,
    ResearchFinalReviewRequest,
    ResearchPlanReviewRequest,
    SocraticSessionAnswerRequest,
    SocraticSessionStartRequest,
    SocraticQuestionRequest,
    TermExplainRequest,
)
from services import (
    agent_artifact_service,
    agent_project_service,
    agent_review_service,
    agent_run_service,
    agent_timeline_service,
    agent_workspace_service,
    analysis_service,
    chat_service,
    code_execution_service,
    rag_service,
    research_monitor,
    research_task_service,
    trace_service,
)


router = APIRouter(prefix="/api")


@router.post("/code-execution-artifacts")
async def upload_code_execution_artifact(file: UploadFile = File(...)):
    try:
        content = await file.read(code_execution_service.MAX_ARTIFACT_BYTES + 1)
        artifact = code_execution_service.stage_csv_artifact(file.filename or "", content)
        return JSONResponse({"status": "success", "artifact": artifact})
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.post("/code-execution-jobs")
async def create_code_execution_job(request: CodeExecutionJobCreateRequest):
    try:
        return JSONResponse(code_execution_service.create_job(request.artifactId))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.get("/code-execution-jobs")
async def list_code_execution_jobs():
    return JSONResponse(code_execution_service.list_jobs())


@router.get("/code-execution-jobs/{job_id}")
async def get_code_execution_job(job_id: str):
    try:
        return JSONResponse(code_execution_service.get_job(job_id))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)


@router.post("/code-execution-jobs/{job_id}/execution-review")
async def review_code_execution(job_id: str, request: CodeExecutionReviewRequest):
    try:
        return JSONResponse(code_execution_service.review_execution(
            job_id, request.decision, request.expectedTaskDigest, request.reason
        ))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except code_execution_service.ReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.post("/code-execution-jobs/{job_id}/publication-review")
async def review_code_publication(job_id: str, request: CodePublicationReviewRequest):
    try:
        return JSONResponse(code_execution_service.review_publication(
            job_id, request.decision, request.expectedPublicationDigest, request.reason
        ))
    except KeyError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except code_execution_service.ReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.post("/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    try:
        return JSONResponse(await analysis_service.analyze_pdf(file))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/background-knowledge")
async def background_knowledge(request: BackgroundKnowledgeRequest):
    try:
        return JSONResponse(analysis_service.get_background_knowledge(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/socratic-questions")
async def socratic_questions(request: SocraticQuestionRequest):
    try:
        return JSONResponse(chat_service.generate_socratic_questions(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/socratic-session/start")
async def start_socratic_session(request: SocraticSessionStartRequest):
    try:
        return JSONResponse(chat_service.start_socratic_session(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/socratic-session/answer")
async def answer_socratic_session(request: SocraticSessionAnswerRequest):
    try:
        return JSONResponse(chat_service.answer_socratic_question(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/explain-term")
async def explain_term(request: TermExplainRequest):
    try:
        return JSONResponse(chat_service.explain_term(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        return JSONResponse(chat_service.chat(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/research-tasks")
async def create_research_task(request: ResearchTaskCreateRequest):
    try:
        return JSONResponse(research_task_service.create_research_task(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-projects")
async def create_agent_project(request: AgentProjectCreateRequest):
    try:
        return JSONResponse(agent_project_service.create_agent_project(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-projects")
async def list_agent_projects():
    try:
        return JSONResponse(agent_project_service.list_agent_projects())
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-projects/{project_id}")
async def get_agent_project(project_id: str):
    try:
        return JSONResponse(agent_project_service.get_agent_project(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.patch("/agent-projects/{project_id}")
async def update_agent_project(project_id: str, request: AgentProjectUpdateRequest):
    try:
        return JSONResponse(agent_project_service.update_agent_project(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.delete("/agent-projects/{project_id}")
async def delete_agent_project(project_id: str):
    try:
        return JSONResponse(agent_project_service.delete_agent_project(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-projects/{project_id}/papers")
async def add_project_papers(project_id: str, request: AgentProjectPapersRequest):
    try:
        return JSONResponse(agent_project_service.add_project_papers(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.delete("/agent-projects/{project_id}/papers/{pdf_id}")
async def remove_project_paper(project_id: str, pdf_id: str):
    try:
        return JSONResponse(agent_project_service.remove_project_paper(project_id, pdf_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-projects/{project_id}/tasks")
async def create_agent_task(project_id: str, request: AgentTaskCreateRequest):
    try:
        return JSONResponse(agent_project_service.create_agent_task(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-projects/{project_id}/runs")
async def create_agent_run(project_id: str, request: AgentRunCreateRequest):
    try:
        return JSONResponse(agent_run_service.create_run(project_id, request))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-projects/{project_id}/tasks")
async def list_agent_project_tasks(project_id: str, limit: int = 20):
    try:
        return JSONResponse(agent_project_service.list_agent_project_tasks(project_id, limit=limit))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-projects/{project_id}/workspace")
async def get_agent_workspace(project_id: str):
    try:
        return JSONResponse(agent_workspace_service.get_workspace(project_id))
    except agent_project_service.AgentProjectNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-projects/{project_id}/tasks/latest")
async def get_latest_agent_task(project_id: str):
    try:
        return JSONResponse(agent_project_service.get_latest_agent_task(project_id))
    except (agent_project_service.AgentProjectNotFoundError, agent_project_service.AgentTaskNotFoundError) as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-runs/{run_id}")
async def get_agent_run(run_id: str):
    try:
        return JSONResponse(agent_run_service.get_run(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-runs/{run_id}/artifacts")
async def get_agent_run_artifacts(run_id: str):
    try:
        return JSONResponse(agent_artifact_service.get_artifacts(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-runs/{run_id}/timeline")
async def get_agent_run_timeline(run_id: str):
    try:
        return JSONResponse(agent_timeline_service.get_timeline(run_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/agent-tasks/{task_id}")
async def get_agent_task(task_id: str):
    try:
        return JSONResponse(agent_project_service.get_agent_task(task_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-tasks/{task_id}/cancel")
async def cancel_agent_task(task_id: str):
    try:
        return JSONResponse(agent_project_service.cancel_agent_task(task_id))
    except agent_project_service.AgentTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/agent-runs/{run_id}/plan-review")
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


@router.post("/agent-tasks/{task_id}/plan-review")
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


@router.post("/agent-runs/{run_id}/final-review")
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


@router.post("/agent-runs/{run_id}/clarification")
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


@router.post("/agent-tasks/{task_id}/final-review")
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


@router.get("/agent-traces/{trace_id}")
async def get_agent_trace(trace_id: str):
    try:
        return JSONResponse(trace_service.get_trace_summary(trace_id))
    except trace_service.TraceNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/research-tasks/brief-preview")
async def preview_research_brief(request: ResearchTaskBriefPreviewRequest):
    try:
        return JSONResponse(research_task_service.preview_research_brief(request))
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/research-tasks/latest")
async def get_latest_research_task(pdfId: str):
    try:
        return JSONResponse(research_task_service.get_latest_research_task(pdfId))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/research-tasks/{task_id}")
async def get_research_task(task_id: str):
    try:
        return JSONResponse(research_task_service.get_research_task(task_id))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/research-tasks/{task_id}/cancel")
async def cancel_research_task(task_id: str):
    try:
        return JSONResponse(research_task_service.cancel_research_task(task_id))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/research-tasks/{task_id}/plan-review")
async def review_research_plan(task_id: str, request: ResearchPlanReviewRequest):
    try:
        return JSONResponse(research_task_service.review_research_plan(task_id, request))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except research_task_service.ResearchReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.post("/research-tasks/{task_id}/final-review")
async def review_research_final(task_id: str, request: ResearchFinalReviewRequest):
    try:
        return JSONResponse(research_task_service.review_research_final(task_id, request))
    except research_task_service.ResearchTaskNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except research_task_service.ResearchReviewConflictError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    try:
        return JSONResponse(trace_service.get_trace_summary(trace_id))
    except trace_service.TraceNotFoundError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=404)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/translate-page")
async def translate_page(request: PageTranslationRequest):
    try:
        return JSONResponse(chat_service.translate_page(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/rag/add-literature")
async def rag_add_literature(file: UploadFile = File(...), metadata: dict | None = None):
    try:
        return JSONResponse(await rag_service.add_literature(file, metadata))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/rag/retrieve")
async def rag_retrieve(query: str, top_k: int = 5, filter_metadata: dict | None = None):
    try:
        return JSONResponse(rag_service.retrieve(query, top_k=top_k, filter_metadata=filter_metadata))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.post("/deep-analysis")
async def deep_analysis(request: Annotated[DeepAnalysisRequest | str, Body(...)]):
    try:
        payload = request if isinstance(request, DeepAnalysisRequest) else DeepAnalysisRequest(paper_content=request)
        return JSONResponse(analysis_service.deep_analysis(payload))
    except analysis_service.PaperNotIndexedError as error:
        return JSONResponse(error.to_response(), status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "errorCode": "bad_request", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


# ── Research Monitor API ──────────────────────────────────────────────────

@router.post("/research-monitors")
async def create_monitor_route(request: dict):
    try:
        return JSONResponse(research_monitor.create_monitor(
            question=request.get("question", ""),
            sources=request.get("sources", ["arxiv"]),
            frequency=request.get("frequency", "manual"),
        ))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/research-monitors")
async def list_monitors_route():
    try:
        monitors = research_monitor.list_monitors()
        serializable = []
        for m in monitors:
            row = {}
            for k in m.keys():
                row[k] = m[k]
            serializable.append(row)
        return JSONResponse({"status": "success", "monitors": serializable, "error": ""})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/research-monitors/{monitor_id}/check")
async def check_monitor_route(monitor_id: str):
    try:
        return JSONResponse(research_monitor.check_new_publications(monitor_id))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.get("/research-monitors/{monitor_id}/digest")
async def digest_monitor_route(monitor_id: str):
    try:
        return JSONResponse(research_monitor.get_monitor_digest(monitor_id))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@router.delete("/research-monitors/{monitor_id}")
async def deactivate_monitor_route(monitor_id: str):
    try:
        ok = research_monitor.deactivate_monitor(monitor_id)
        return JSONResponse({"status": "success" if ok else "error", "monitorId": monitor_id, "error": "" if ok else "Monitor not found."})
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
