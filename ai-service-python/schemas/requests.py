from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
    coveredAspects: Optional[List[str]] = None
    missingAspects: Optional[List[str]] = None
    evidenceQuality: Optional[Dict[str, Any]] = None


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
    paper_topic: Optional[Any] = None
    user_knowledge_level: Optional[Any] = "普通/一般"
    reader_profile: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None
    pdfId: Optional[str] = None
    paperSkeleton: Optional[Dict[str, Any]] = None
    paperStructure: Optional[Dict[str, Any]] = None
    include_library_papers: bool = False


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


class ResearchTaskCreateRequest(BaseModel):
    question: str
    pdfId: str
    paperSkeleton: Optional[Dict[str, Any]] = None
    userConstraints: Optional[str] = ""
    briefPreview: Optional[Dict[str, Any]] = None
    allowExternalSearch: bool = Field(default=False)
    allowWebSearch: bool = Field(default=False)


class ResearchTaskBriefPreviewRequest(BaseModel):
    question: str
    pdfId: str
    paperSkeleton: Optional[Dict[str, Any]] = None
    userConstraints: Optional[str] = ""


class RiskReviewItem(BaseModel):
    riskId: str
    reviewStatus: str


class ResearchPlanReviewRequest(BaseModel):
    subQuestions: List[str]
    reviewNotes: Optional[str] = ""


class ResearchFinalReviewRequest(BaseModel):
    reviewNotes: Optional[str] = ""
    riskReviews: Optional[List[RiskReviewItem]] = None


class AgentProjectCreateRequest(BaseModel):
    title: Optional[str] = ""
    goal: Optional[str] = ""
    paperIds: Optional[List[str]] = None


class AgentProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    defaultConstraints: Optional[str] = None


class AgentProjectPapersRequest(BaseModel):
    paperIds: List[str]


class AgentTaskCreateRequest(BaseModel):
    prompt: str
    focusedPaperIds: Optional[List[str]] = None
    constraints: Optional[str] = ""
    context: Optional[Dict[str, Any]] = None
    allowExternalSearch: bool = Field(default=False)
    allowCodeExecution: bool = Field(default=False)
    allowWebSearch: bool = Field(default=False)
    allowIterativeSearch: bool = Field(default=False)


class AgentRunCreateRequest(BaseModel):
    prompt: str
    taskId: Optional[str] = ""
    reviewMode: Literal["auto", "manual"] = "manual"
    idempotencyKey: Optional[str] = ""
    focusedPaperIds: Optional[List[str]] = None
    constraints: Optional[str] = ""
    context: Optional[Dict[str, Any]] = None
    allowExternalSearch: bool = Field(default=False)
    allowCodeExecution: bool = Field(default=False)
    allowWebSearch: bool = Field(default=False)
    allowIterativeSearch: bool = Field(default=False)
    domain: Optional[str] = Field(default="")


class AgentPlanItemRequest(BaseModel):
    id: Optional[str] = ""
    label: str
    detail: Optional[str] = ""
    allowExternalSearch: Optional[bool] = Field(default=False)
    allowCodeExecution: Optional[bool] = Field(default=False)
    allowWebSearch: Optional[bool] = Field(default=False)
    allowIterativeSearch: Optional[bool] = Field(default=False)


class AgentPlanReviewRequest(BaseModel):
    planItems: List[AgentPlanItemRequest]
    focusedPaperIds: List[str]
    constraints: Optional[str] = ""
    reviewNotes: Optional[str] = ""


class AgentRunPlanReviewRequest(BaseModel):
    planItems: List[AgentPlanItemRequest]
    focusedPaperIds: List[str]
    constraints: Optional[str] = ""
    reviewNotes: Optional[str] = ""
    allowExternalSearch: bool = Field(default=False)
    allowCodeExecution: bool = Field(default=False)
    allowWebSearch: bool = Field(default=False)


class AgentFinalReviewRequest(BaseModel):
    reviewNotes: Optional[str] = ""
    riskReviews: Optional[List[RiskReviewItem]] = None


class AgentRunFinalReviewRequest(BaseModel):
    reviewNotes: Optional[str] = ""
    riskReviews: Optional[List[RiskReviewItem]] = None


class AgentClarificationRequest(BaseModel):
    userAnswer: str
    question: Optional[str] = ""
    currentDirection: Optional[str] = ""


class CodeExecutionJobCreateRequest(BaseModel):
    artifactId: str = Field(pattern=r"^artifact-[a-z0-9-]{1,120}$")


class CodeExecutionReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    expectedTaskDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Optional[str] = Field(default=None, max_length=500)


class CodePublicationReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    expectedPublicationDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Optional[str] = Field(default=None, max_length=500)


class PaperDraftRequest(BaseModel):
    question: str
    title: Optional[str] = ""
    findings: Optional[List[Dict[str, Any]]] = None
    evidenceItems: Optional[List[Dict[str, Any]]] = None
    conflicts: Optional[List[Dict[str, Any]]] = None
    sourceIds: Optional[List[str]] = None
    metaAnalysis: Optional[Dict[str, Any]] = None
    adversarialReview: Optional[Dict[str, Any]] = None
    section: Optional[str] = ""
    existingSections: Optional[Dict[str, str]] = None


class ResearchMonitorCreateRequest(BaseModel):
    question: str
    sources: Optional[List[str]] = Field(default=["arxiv"])
    frequency: Optional[str] = Field(default="manual")
