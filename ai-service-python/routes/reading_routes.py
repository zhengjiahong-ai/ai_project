from typing import Annotated

try:
    from fastapi import APIRouter, Body, File, UploadFile
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - test-only fallback
    from tests.fastapi_stubs import (
        APIRouter,
        Body,
        File,
        JSONResponse,
        UploadFile,
    )

from schemas.requests import (
    BackgroundKnowledgeRequest,
    ChatRequest,
    DeepAnalysisRequest,
    PageTranslationRequest,
    PaperDraftRequest,
    SocraticQuestionRequest,
    SocraticSessionAnswerRequest,
    SocraticSessionStartRequest,
    TermExplainRequest,
)
from services import (
    analysis_service,
    chat_service,
    socratic_service,
    term_explanation_service,
)

reading_router = APIRouter()


@reading_router.post("/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    try:
        return JSONResponse(await analysis_service.analyze_pdf(file))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/background-knowledge")
async def background_knowledge(request: BackgroundKnowledgeRequest):
    try:
        return JSONResponse(analysis_service.get_background_knowledge(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/socratic-questions")
async def socratic_questions(request: SocraticQuestionRequest):
    try:
        return JSONResponse(socratic_service.generate_socratic_questions(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/socratic-session/start")
async def start_socratic_session(request: SocraticSessionStartRequest):
    try:
        return JSONResponse(socratic_service.start_socratic_session(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/socratic-session/answer")
async def answer_socratic_session(request: SocraticSessionAnswerRequest):
    try:
        return JSONResponse(socratic_service.answer_socratic_question(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/explain-term")
async def explain_term(request: TermExplainRequest):
    try:
        return JSONResponse(term_explanation_service.explain_term(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/chat")
async def chat(request: ChatRequest):
    try:
        return JSONResponse(chat_service.chat(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/translate-page")
async def translate_page(request: PageTranslationRequest):
    try:
        return JSONResponse(chat_service.translate_page(request))
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)


@reading_router.post("/deep-analysis")
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


@reading_router.post("/generate-paper-draft")
async def generate_paper_draft(request: PaperDraftRequest):
    try:
        from services.paper_writer import generate_paper_draft
        result = generate_paper_draft(
            question=request.question,
            findings=request.findings or [],
            evidence_items=request.evidenceItems or [],
            conflicts=request.conflicts or [],
            title=request.title or "",
            meta_analysis=request.metaAnalysis,
            adversarial_review=request.adversarialReview,
            section=request.section or "",
            existing_sections=request.existingSections,
        )
        return JSONResponse(result)
    except Exception as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=500)
