from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TermExplainRequest(BaseModel):
    term: str
    context: Optional[str] = ""
    pdfId: Optional[str] = None
    pageNumber: Optional[int] = None


class SocraticQuestionRequest(BaseModel):
    paper_content: str
    reading_progress: str


class SocraticTurn(BaseModel):
    index: int
    question: str
    answer: str
    masteryLevel: Optional[str] = None
    feedback: Optional[str] = None
    hint: Optional[str] = None


class SocraticSessionStartRequest(BaseModel):
    pdfId: Optional[str] = None
    paperSkeleton: Optional[Dict[str, Any]] = None
    readingProgress: str


class SocraticSessionAnswerRequest(BaseModel):
    pdfId: Optional[str] = None
    paperSkeleton: Optional[Dict[str, Any]] = None
    readingProgress: str
    currentIndex: int
    currentQuestion: str
    userAnswer: str
    turns: Optional[List[SocraticTurn]] = None


class BackgroundKnowledgeRequest(BaseModel):
    paper_topic: Optional[str] = None
    user_knowledge_level: Optional[str] = "普通/一般"
    pdfId: Optional[str] = None
    paperSkeleton: Optional[Dict[str, Any]] = None
    paperStructure: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str
    pdfId: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    paperSkeleton: Optional[Dict[str, Any]] = None


class PageTranslationRequest(BaseModel):
    pdfId: Optional[str] = None
    pageIndex: int
    pageText: str
    paperSkeleton: Optional[Dict[str, Any]] = None
    pageLayout: Optional[Dict[str, Any]] = None


class DeepAnalysisRequest(BaseModel):
    paper_content: Optional[str] = None
    pdf_id: Optional[str] = None
