from typing import Annotated

from fastapi import APIRouter, Body, File, UploadFile
from fastapi.responses import JSONResponse

from schemas.requests import (
    BackgroundKnowledgeRequest,
    ChatRequest,
    DeepAnalysisRequest,
    SocraticSessionAnswerRequest,
    SocraticSessionStartRequest,
    SocraticQuestionRequest,
    TermExplainRequest,
)
from services import analysis_service, chat_service, rag_service


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
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
