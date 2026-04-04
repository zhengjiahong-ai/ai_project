from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TermExplainRequest(BaseModel):
    term: str
    context: str


class SocraticQuestionRequest(BaseModel):
    paper_content: str
    reading_progress: str


class BackgroundKnowledgeRequest(BaseModel):
    paper_topic: str
    user_knowledge_level: str


class ChatRequest(BaseModel):
    message: str
    pdfId: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    paperSkeleton: Optional[Dict[str, Any]] = None


class DeepAnalysisRequest(BaseModel):
    paper_content: Optional[str] = None
    pdf_id: Optional[str] = None
