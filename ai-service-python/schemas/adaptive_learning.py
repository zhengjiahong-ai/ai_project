"""Serializable learning activity contract, independent of the legacy five-question API."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class LearningConcept(BaseModel):
    id: str
    label: str
    question: str
    explanation: str = ""
    explanationReferences: list[dict[str, Any]] = Field(default_factory=list)
    explanationSources: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "needs_review", "demonstrated", "skipped"] = "pending"
    missingAspects: list[str] = Field(default_factory=list)
    attempts: int = 0


class LearningState(BaseModel):
    schemaVersion: Literal[1] = 1
    activityId: str
    taskId: str
    pdfId: str
    paperIds: list[str] = Field(default_factory=list)
    primaryPaperId: str | None = None
    mode: Literal["read", "quiz"] = "read"
    goal: str
    status: Literal["active", "paused", "finished"] = "active"
    revision: int = 0
    concepts: list[LearningConcept] = Field(default_factory=list)
    currentConceptId: str | None = None
    turns: list[dict[str, Any]] = Field(default_factory=list)
    evidenceSnapshot: list[dict[str, Any]] = Field(default_factory=list)
    finishReason: str | None = None


class AdaptiveLearningStartRequest(BaseModel):
    taskId: str = Field(min_length=1)
    pdfId: str = Field(min_length=1)
    mode: Literal["read", "quiz"] = "read"
    goal: str = "理解论文的关键问题、方法和证据"


class AdaptiveLearningActionRequest(BaseModel):
    taskId: str
    activityId: str
    expectedRevision: int = Field(ge=0)
    action: Literal["answer", "hint", "skip", "retry", "pause", "resume", "finish", "ask", "remediate"]
    text: str = ""
    state: LearningState
