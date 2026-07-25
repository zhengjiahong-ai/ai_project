from typing import Literal, TypedDict

RunStatus = Literal[
    "draft",
    "awaiting_plan_review",
    "queued",
    "running",
    "awaiting_final_review",
    "completed",
    "failed",
    "cancelled",
]


ExecutionPhase = Literal[
    "",
    "planning_context",
    "retrieving_evidence",
    "synthesizing",
    "assembling_artifacts",
]


class AgentRunRecord(TypedDict, total=False):
    runId: str
    projectId: str
    status: RunStatus
    executionPhase: ExecutionPhase
    prompt: str
    focusedPaperIds: list[str]
    constraints: str
    context: dict
    traceId: str
