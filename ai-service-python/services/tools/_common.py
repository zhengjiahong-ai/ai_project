"""Internal shared utilities for the tool registry and tool handlers.

This module contains constants, helpers, and utility functions that are
used by both the tool registry and individual tool handler implementations.
It is not part of the public API.
"""

import copy
import os
import re
from typing import Any

from services.external_search_provider import create_external_search_provider
from services.trace_service import (
    get_current_trace_id,
    get_trace_snapshot,
)

EXTERNAL_SEARCH_CALL_BUDGET = 10
EXTERNAL_SEARCH_EVIDENCE_BUDGET = 40
WEB_SEARCH_CALL_BUDGET = 20
WEB_SEARCH_RESULT_BUDGET = 50
WEB_FETCH_CALL_BUDGET = 30
WEB_FETCH_CHAR_BUDGET = 200_000

_MAX_TOKENS_PER_TASK_DEFAULT = 500_000

_DEFAULT_EXTERNAL_SEARCH_PROVIDER = None


def _env_max_tokens_per_task() -> int:
    val = os.environ.get("PIXIU_MAX_TOKENS_PER_TASK", "")
    try:
        parsed = int(val)
        if parsed >= 1:
            return parsed
    except (ValueError, TypeError):
        pass
    return _MAX_TOKENS_PER_TASK_DEFAULT


def _task_token_budget_exhausted() -> bool:
    """Check whether the task-level token budget has been exhausted.

    Reads the current trace counters for estimatedInputTokens + estimatedOutputTokens
    and compares against PIXIU_MAX_TOKENS_PER_TASK.
    Returns True when the cumulative token usage exceeds the budget.
    """
    max_tokens = _env_max_tokens_per_task()
    trace_id = get_current_trace_id()
    if not trace_id:
        return False
    try:
        snapshot = get_trace_snapshot(trace_id)
    except KeyError:
        return False
    counters = snapshot.get("counters") or {}
    consumed = (
        int(counters.get("estimatedInputTokens") or 0)
        + int(counters.get("estimatedOutputTokens") or 0)
    )
    return consumed >= max_tokens


def _get_external_search_provider() -> Any:
    global _DEFAULT_EXTERNAL_SEARCH_PROVIDER
    if _DEFAULT_EXTERNAL_SEARCH_PROVIDER is None:
        _DEFAULT_EXTERNAL_SEARCH_PROVIDER = create_external_search_provider()
    return _DEFAULT_EXTERNAL_SEARCH_PROVIDER


def reset_external_search_provider() -> None:
    global _DEFAULT_EXTERNAL_SEARCH_PROVIDER
    _DEFAULT_EXTERNAL_SEARCH_PROVIDER = None


def _resolve_provider_display_name(provider: Any) -> str:
    """Resolve a human-readable provider name for trace/log output.

    For a single provider, returns its name. For a registry, returns a
    comma-separated list of sub-provider names.
    """
    raw_name = _clean_text(getattr(provider, "name", "")) or "unknown"
    if raw_name == "multi":
        names = _resolve_provider_names_list(provider)
        if names:
            return ", ".join(names)
    return raw_name


def _resolve_provider_names_list(provider: Any) -> list:
    """Return the sorted list of individual provider names, or empty list."""
    try:
        return provider.provider_names
    except AttributeError:
        return []


def _external_search_budget_snapshot() -> dict[str, int]:
    return {
        "callLimit": EXTERNAL_SEARCH_CALL_BUDGET,
        "callsUsed": _trace_counter_value("externalSearchCalls"),
        "evidenceLimit": EXTERNAL_SEARCH_EVIDENCE_BUDGET,
        "evidenceUsed": _trace_counter_value("externalEvidenceCount"),
    }


def _external_search_budget_block_reason(requested_limit: int) -> str:
    if _task_token_budget_exhausted():
        return "Task token budget exhausted."
    snapshot = _external_search_budget_snapshot()
    if snapshot["callsUsed"] >= snapshot["callLimit"]:
        return "External academic search call budget exceeded."
    if snapshot["evidenceUsed"] + max(0, int(requested_limit or 0)) > snapshot["evidenceLimit"]:
        return "External academic search evidence budget exceeded."
    return ""


def _web_search_budget_snapshot() -> dict[str, int]:
    return {
        "callLimit": WEB_SEARCH_CALL_BUDGET,
        "callsUsed": _trace_counter_value("webSearchCalls"),
        "resultLimit": WEB_SEARCH_RESULT_BUDGET,
        "resultsUsed": _trace_counter_value("webSearchResults"),
    }


def _web_search_budget_block_reason(requested_limit: int) -> str:
    if _task_token_budget_exhausted():
        return "Task token budget exhausted."
    snapshot = _web_search_budget_snapshot()
    if snapshot["callsUsed"] >= snapshot["callLimit"]:
        return "Web search call budget exceeded (max 20 per task)."
    if snapshot["resultsUsed"] + max(0, int(requested_limit or 0)) > snapshot["resultLimit"]:
        return "Web search result budget exceeded (max 50 per task)."
    return ""


def _web_fetch_budget_snapshot() -> dict[str, int]:
    return {
        "callLimit": WEB_FETCH_CALL_BUDGET,
        "callsUsed": _trace_counter_value("webFetchCalls"),
        "charLimit": WEB_FETCH_CHAR_BUDGET,
        "charsUsed": _trace_counter_value("webFetchChars"),
    }


def _web_fetch_budget_block_reason(max_chars: int) -> str:
    if _task_token_budget_exhausted():
        return "Task token budget exhausted."
    snapshot = _web_fetch_budget_snapshot()
    if snapshot["callsUsed"] >= snapshot["callLimit"]:
        return "Web fetch call budget exceeded (max 30 per task)."
    if snapshot["charsUsed"] + max(0, int(max_chars or 0)) > snapshot["charLimit"]:
        return "Web fetch char budget exceeded (max 200000 per task)."
    return ""


def _trace_counter_value(name: str) -> int:
    trace_id = get_current_trace_id()
    if not trace_id:
        return 0
    try:
        snapshot = get_trace_snapshot(trace_id)
    except KeyError:
        return 0
    value = (snapshot.get("counters") or {}).get(name)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    return payload


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _ensure_stable_source_ids(items: list[dict[str, Any]], fallback_prefix: str) -> list[dict[str, Any]]:
    stabilized: list[dict[str, Any]] = []
    for index, item in enumerate(items or []):
        current = copy.deepcopy(item)
        base = str(current.get("sourceId") or "").strip()
        if not base or base.startswith("source-"):
            pdf_id = _slugify(current.get("pdfId") or fallback_prefix or "source")
            chunk_index = current.get("chunkIndex")
            if chunk_index is not None:
                base = f"{pdf_id}-chunk-{chunk_index}"
            else:
                base = f"{pdf_id}-{index + 1}"
        current["sourceId"] = base[:80]
        stabilized.append(current)
    return stabilized


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "source"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
