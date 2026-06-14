from typing import Annotated

from fastapi import APIRouter, Body, File, UploadFile
from fastapi.responses import JSONResponse

from schemas.requests import (
    BackgroundKnowledgeRequest,
    AgentProjectCreateRequest,
    AgentProjectPapersRequest,
    AgentProjectUpdateRequest,
    AgentTaskCreateRequest,
    ChatRequest,
    DeepAnalysisRequest,
    PageTranslationRequest,
    ResearchTaskBriefPreviewRequest,
    ResearchTaskCreateRequest,
    SocraticSessionAnswerRequest,
    SocraticSessionStartRequest,
    SocraticQuestionRequest,
    TermExplainRequest,
)
from services import agent_project_service, analysis_service, chat_service, rag_service, research_task_service, trace_service


router = APIRouter(prefix="/api")


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


@router.get("/agent-projects/{project_id}/tasks/latest")
async def get_latest_agent_task(project_id: str):
    try:
        return JSONResponse(agent_project_service.get_latest_agent_task(project_id))
    except (agent_project_service.AgentProjectNotFoundError, agent_project_service.AgentTaskNotFoundError) as error:
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
