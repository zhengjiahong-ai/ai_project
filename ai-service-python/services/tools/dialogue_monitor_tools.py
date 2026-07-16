"""Research dialogue and monitor tools: clarification questions, user feedback
incorporation, research monitors (create/check/digest/list/deactivate), and
reproducibility verification.

All tool handlers and their registrations extracted from tool_registry.py.
"""

from typing import Any, Dict

from services.reproducibility_checker import verify_reproducibility
from services.research_dialogue import generate_clarification_question, incorporate_user_feedback
from services.research_monitor import (
    check_new_publications,
    create_monitor,
    deactivate_monitor,
    get_monitor_digest,
    list_monitors,
)
from services.trace_service import record_counter, trace_step
from services.tools._common import _clean_text
from services.tool_registry import ToolValidationError, _object_output, _safety_scope


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def _generate_clarification_question_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    if not question:
        raise ToolValidationError("generate_clarification_question requires a non-empty question.")
    findings = payload.get("findings") or []
    conflicts = payload.get("conflicts") or []
    gaps = payload.get("gaps") or []
    round_number = int(payload.get("roundNumber") or 1)

    with trace_step("tool_generate_clarification_question", input_size=len(question)) as step:
        record_counter("clarificationQuestionCalls")
        result = generate_clarification_question(question, findings, conflicts, gaps, round_number)
        step["outputSize"] = len(result.get("questions", []))
        if result["status"] != "success":
            record_counter("clarificationQuestionFailures")
        return result


def _incorporate_user_feedback_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    user_answer = (payload.get("userAnswer") or "").strip()
    if not question:
        raise ToolValidationError("incorporate_user_feedback requires a non-empty question.")
    if not user_answer:
        raise ToolValidationError("incorporate_user_feedback requires a non-empty userAnswer.")
    current_direction = (payload.get("currentDirection") or "").strip()

    with trace_step("tool_incorporate_user_feedback", input_size=len(user_answer)) as step:
        record_counter("userFeedbackCalls")
        result = incorporate_user_feedback(question, user_answer, current_direction)
        step["outputSize"] = len(result.get("refinedDirection", ""))
        if result["status"] != "success":
            record_counter("userFeedbackFailures")
        return result


def _create_research_monitor_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = (payload.get("question") or "").strip()
    if not question:
        raise ToolValidationError("create_research_monitor requires a non-empty question.")
    sources = payload.get("sources") or ["arxiv"]
    frequency = (payload.get("frequency") or "daily").strip()

    with trace_step("tool_create_monitor", input_size=len(question)) as step:
        record_counter("monitorCreateCalls")
        result = create_monitor(question, sources, frequency)
        step["outputSize"] = len(result.get("monitorId", ""))
        if result["status"] != "success":
            record_counter("monitorCreateFailures")
        return result


def _check_new_publications_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    monitor_id = (payload.get("monitorId") or "").strip()
    if not monitor_id:
        raise ToolValidationError("check_new_publications requires a non-empty monitorId.")

    with trace_step("tool_check_publications", input_size=len(monitor_id)) as step:
        record_counter("monitorCheckCalls")
        result = check_new_publications(monitor_id)
        step["outputSize"] = result.get("newCount", 0)
        if result["status"] != "success":
            record_counter("monitorCheckFailures")
        return result


def _get_monitor_digest_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    monitor_id = (payload.get("monitorId") or "").strip()
    if not monitor_id:
        raise ToolValidationError("get_monitor_digest requires a non-empty monitorId.")

    with trace_step("tool_monitor_digest", input_size=len(monitor_id)) as step:
        record_counter("monitorDigestCalls")
        result = get_monitor_digest(monitor_id)
        step["outputSize"] = len(result.get("digest", ""))
        if result["status"] != "success":
            record_counter("monitorDigestFailures")
        return result


def _list_research_monitors_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    with trace_step("tool_list_monitors", input_size=0) as step:
        record_counter("monitorListCalls")
        monitors = list_monitors()
        serializable = []
        for m in monitors:
            row = {}
            for k in m.keys():
                row[k] = m[k]
            serializable.append(row)
        step["outputSize"] = len(serializable)
        return {"status": "success", "monitors": serializable, "error": ""}


def _deactivate_research_monitor_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    monitor_id = (payload.get("monitorId") or "").strip()
    if not monitor_id:
        raise ToolValidationError("deactivate_research_monitor requires a non-empty monitorId.")

    with trace_step("tool_deactivate_monitor", input_size=len(monitor_id)) as step:
        record_counter("monitorDeactivateCalls")
        ok = deactivate_monitor(monitor_id)
        step["outputSize"] = 1 if ok else 0
        return {"status": "success" if ok else "error", "monitorId": monitor_id, "error": "" if ok else "Monitor not found."}


def _verify_reproducibility_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    paper_id = (payload.get("paperId") or "").strip()
    if not paper_id:
        raise ToolValidationError("verify_reproducibility requires a non-empty paperId.")

    with trace_step("tool_verify_reproducibility", input_size=len(paper_id)) as step:
        record_counter("reproducibilityCalls")
        result = verify_reproducibility(paper_id)
        step["outputSize"] = len(result.get("verdict", ""))
        step["meta"] = {"verdict": result.get("verdict")}
        if result.get("status") == "error":
            record_counter("reproducibilityFailures")
        return result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_tools(registry) -> None:
    """Register all research dialogue and monitor tools on *registry*."""

    registry.register(
        "generate_clarification_question",
        "Generate 1-2 high-value clarification questions when research evidence is ambiguous or conflicting. "
        "Questions target ambiguity resolution, direction choice, and scope definition.",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "findings": {"type": "array", "items": {"type": "object"}},
                "conflicts": {"type": "array", "items": {"type": "object"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
                "roundNumber": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "additionalProperties": False,
        },
        _generate_clarification_question_tool,
        output_schema={
            "type": "object",
            "required": ["status", "questions", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "context": {"type": "string"},
                        },
                    },
                },
                "roundNumber": {"type": "integer"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_dialogue"],
            network_access=False,
            sensitive_output=False,
        ),
    )
    registry.register(
        "incorporate_user_feedback",
        "Incorporate user feedback into a refined research direction. "
        "Takes the original question, user's answer to a clarification question, "
        "and returns a refined direction with adjusted search queries.",
        {
            "type": "object",
            "required": ["question", "userAnswer"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "userAnswer": {"type": "string", "minLength": 1, "maxLength": 1000},
                "currentDirection": {"type": "string", "maxLength": 500},
            },
            "additionalProperties": False,
        },
        _incorporate_user_feedback_tool,
        output_schema={
            "type": "object",
            "required": ["status", "refinedDirection", "refinedQueries", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "refinedDirection": {"type": "string"},
                "refinedQueries": {"type": "array", "items": {"type": "string"}},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_dialogue"],
            network_access=False,
            sensitive_output=False,
        ),
    )
    registry.register(
        "create_research_monitor",
        "Create a research monitor to watch for new publications matching a research question. "
        "Supports arXiv and PubMed as sources. Returns a monitorId for subsequent checks.",
        {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 300},
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["arxiv", "pubmed"]},
                    "minItems": 1,
                },
                "frequency": {"type": "string", "enum": ["manual", "daily"]},
            },
            "additionalProperties": False,
        },
        _create_research_monitor_tool,
        output_schema={
            "type": "object",
            "required": ["status", "monitorId", "question", "sources", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "monitorId": {"type": "string"},
                "question": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "frequency": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_monitor_config"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "check_new_publications",
        "Check for new publications matching a research monitor's question. "
        "Deduplicates against previously checked papers and scores relevance.",
        {
            "type": "object",
            "required": ["monitorId"],
            "properties": {
                "monitorId": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "additionalProperties": False,
        },
        _check_new_publications_tool,
        output_schema={
            "type": "object",
            "required": ["status", "monitorId", "newPapers", "newCount", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "monitorId": {"type": "string"},
                "newPapers": {"type": "array", "items": {"type": "object"}},
                "newCount": {"type": "integer"},
                "recommended": {"type": "array", "items": {"type": "object"}},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_monitor_results"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "get_monitor_digest",
        "Generate a human-readable Markdown digest of recent findings for a research monitor.",
        {
            "type": "object",
            "required": ["monitorId"],
            "properties": {
                "monitorId": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "additionalProperties": False,
        },
        _get_monitor_digest_tool,
        output_schema={
            "type": "object",
            "required": ["status", "monitorId", "digest", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "monitorId": {"type": "string"},
                "newPapers": {"type": "array", "items": {"type": "object"}},
                "newCount": {"type": "integer"},
                "digest": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_monitor_results"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "list_research_monitors",
        "List all active research monitors.",
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        _list_research_monitors_tool,
        output_schema={
            "type": "object",
            "required": ["status", "monitors", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "monitors": {"type": "array", "items": {"type": "object"}},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_monitor_config"],
            network_access=False,
            sensitive_output=True,
        ),
    )
    registry.register(
        "deactivate_research_monitor",
        "Deactivate (soft-delete) a research monitor by its monitorId.",
        {
            "type": "object",
            "required": ["monitorId"],
            "properties": {
                "monitorId": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "additionalProperties": False,
        },
        _deactivate_research_monitor_tool,
        output_schema={
            "type": "object",
            "required": ["status", "monitorId", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error"]},
                "monitorId": {"type": "string"},
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["research_monitor_config"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "verify_reproducibility",
        "Verify whether a paper's claims are reproducible by searching for its code repository, "
        "cloning into a Docker sandbox, installing dependencies, and running experiments. "
        "Only available when PIXIU_ALLOW_REPRODUCIBILITY=true. "
        "Only standard-library Python projects can be verified automatically.",
        {
            "type": "object",
            "required": ["paperId"],
            "properties": {
                "paperId": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            "additionalProperties": False,
        },
        _verify_reproducibility_tool,
        output_schema={
            "type": "object",
            "required": ["status", "paperId", "verdict", "error"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "error", "disabled"]},
                "paperId": {"type": "string"},
                "repo": {"type": "string"},
                "build": {"type": "object"},
                "run": {"type": "object"},
                "comparison": {"type": "object"},
                "verdict": {
                    "type": "string",
                    "enum": [
                        "reproduced", "partial", "failed", "disabled",
                        "no_code_available", "clone_failed", "unable_to_verify",
                        "error",
                    ],
                },
                "error": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["code_execution_results", "external_code_repositories"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
