"""
Standardised error response helpers for the Pixiu API.

Every error returned to API clients follows the envelope:
    {"status": "error", "errorCode": "<machine-readable>", "message": "<user-facing>"}

Route handlers should continue to catch *specific* application errors and let
unknown exceptions propagate to the global handler registered in ``app.py``.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple, Type

# ── public helpers ────────────────────────────────────────────────────────


def error_response(
    status_code: int,
    error_code: str,
    user_message: str,
) -> Dict[str, Any]:
    """Build a standardised error envelope."""
    return {
        "status": "error",
        "errorCode": error_code,
        "message": user_message,
    }


def generate_trace_id() -> str:
    """Return a short hex identifier for correlating logs and responses."""
    return uuid.uuid4().hex[:12]


# ── exception → (HTTP status, error_code) mapping ─────────────────────────
#
# Each entry maps a known application exception class to its HTTP status code
# and machine-readable errorCode string.  The global exception handler walks
# this mapping in order; the first ``isinstance`` match wins.

_EXC = Type[Exception]
_SPEC = Tuple[int, str]

EXCEPTION_STATUS_MAP: Dict[_EXC, _SPEC] = {}

# Import lazily to avoid coupling every module that imports error_responses.
try:
    from services.agent_project_service import (
        AgentProjectNotFoundError,
        AgentTaskNotFoundError,
        AgentReviewConflictError,
    )

    EXCEPTION_STATUS_MAP.update(
        {
            AgentProjectNotFoundError: (404, "agent_project_not_found"),
            AgentTaskNotFoundError: (404, "agent_task_not_found"),
            AgentReviewConflictError: (409, "review_conflict"),
        }
    )
except ImportError:
    pass

try:
    from services.research_task_service import (
        ResearchTaskNotFoundError,
        ResearchReviewConflictError,
    )

    EXCEPTION_STATUS_MAP.update(
        {
            ResearchTaskNotFoundError: (404, "research_task_not_found"),
            ResearchReviewConflictError: (409, "review_conflict"),
        }
    )
except ImportError:
    pass

try:
    from services.trace_service import TraceNotFoundError

    EXCEPTION_STATUS_MAP[TraceNotFoundError] = (404, "trace_not_found")
except ImportError:
    pass

try:
    from services.analysis_service import PaperNotIndexedError

    EXCEPTION_STATUS_MAP[PaperNotIndexedError] = (409, "paper_not_indexed")
except ImportError:
    pass

try:
    from services.tool_registry import ToolNotFoundError, ToolValidationError

    EXCEPTION_STATUS_MAP.update(
        {
            ToolNotFoundError: (404, "tool_not_found"),
            ToolValidationError: (422, "tool_validation_error"),
        }
    )
except ImportError:
    pass

try:
    from services.external_search_provider import ExternalSearchConfigurationError

    EXCEPTION_STATUS_MAP[ExternalSearchConfigurationError] = (
        500,
        "external_search_config_error",
    )
except ImportError:
    pass

try:
    from llm.provider import LLMProviderError

    EXCEPTION_STATUS_MAP[LLMProviderError] = (502, "llm_provider_error")
except ImportError:
    pass

# Generic / built-in mappings — kept last so more-specific application
# errors take precedence.
EXCEPTION_STATUS_MAP.update(
    {
        ValueError: (422, "validation_error"),
        KeyError: (404, "not_found"),
        NotImplementedError: (501, "not_implemented"),
    }
)
