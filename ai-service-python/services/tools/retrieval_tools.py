"""Retrieval and search tool handlers.

This module contains the handler functions and registration for retrieval/search
related tools: retrieve_current_paper, retrieve_library, retrieve_external_academic,
search_web, and fetch_web_page.

These are extracted from services.tool_registry to keep the tool registry
manageable.
"""

import time
from typing import Any, Dict, List

from rag.store import get_rag, retrieve_hybrid_results
from services.evidence_service import normalize_evidence_items
from services.external_evidence import normalize_external_evidence_items
from services.safety_service import sanitize_external_academic_query_text
from services.tool_registry import (
    ToolValidationError,
    _external_evidence_schema,
    _object_output,
    _safety_scope,
)
from services.tools._common import (
    _clean_text,
    _coerce_positive_int,
    _ensure_stable_source_ids,
    _external_search_budget_block_reason,
    _external_search_budget_snapshot,
    _get_external_search_provider,
    _resolve_provider_display_name,
    _resolve_provider_names_list,
    _web_fetch_budget_block_reason,
    _web_fetch_budget_snapshot,
    _web_search_budget_block_reason,
    _web_search_budget_snapshot,
)
from services.trace_service import (
    record_counter,
    sanitize_text,
    summarize_external_search_query,
    trace_step,
)


def register_tools(registry: Any) -> None:
    """Register all retrieval/search tools on the given ToolRegistry."""
    registry.register(
        "retrieve_current_paper",
        "Retrieve evidence from the current indexed paper.",
        {
            "type": "object",
            "required": ["pdfId"],
            "properties": {
                "pdfId": {"type": "string", "minLength": 1},
                "query": {"type": "string", "minLength": 1},
                "topK": {"type": "integer", "minimum": 1, "maximum": 200},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "maxTextChars": {"type": "integer", "minimum": 1, "maximum": 5000},
                "includeAll": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        _retrieve_current_paper_tool,
        output_schema=_object_output(
            ["items", "pdfId"],
            {
                "items": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "pdfId": {"type": "string", "minLength": 1},
            },
        ),
        safety_scope=_safety_scope(["current_paper_index"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "retrieve_library",
        "Retrieve evidence from the internal literature library.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "excludePdfId": {"type": "string", "minLength": 1},
                "topK": {"type": "integer", "minimum": 1, "maximum": 100},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "maxTextChars": {"type": "integer", "minimum": 1, "maximum": 5000},
            },
            "additionalProperties": False,
        },
        _retrieve_library_tool,
        output_schema=_object_output(
            ["items"],
            {"items": {"type": "array", "items": {"type": "object", "additionalProperties": True}}},
        ),
        safety_scope=_safety_scope(["internal_library_index"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "retrieve_external_academic",
        "Retrieve read-only academic metadata from the configured external provider.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                "yearFrom": {"type": "integer", "minimum": 1000, "maximum": 9999},
                "yearTo": {"type": "integer", "minimum": 1000, "maximum": 9999},
            },
            "additionalProperties": False,
        },
        _retrieve_external_academic_tool,
        output_schema={
            "type": "object",
            "required": ["status", "provider", "items"],
            "properties": {
                "status": {"type": "string", "enum": ["disabled", "success", "budget_exceeded", "failed"]},
                "provider": {"type": "string", "minLength": 1},
                "items": {"type": "array", "items": _external_evidence_schema()},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["external_academic_metadata"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "search_web",
        "Search the web for supplementary evidence. "
        "Only available when allowWebSearch is authorized and a web-capable provider is configured.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 300},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "searchType": {
                    "type": "string",
                    "enum": ["general", "academic", "news"],
                },
            },
            "additionalProperties": False,
        },
        _search_web_tool,
        output_schema={
            "type": "object",
            "required": ["status", "provider", "items"],
            "properties": {
                "status": {"type": "string", "enum": ["disabled", "success", "budget_exceeded", "failed"]},
                "provider": {"type": "string", "minLength": 1},
                "items": {"type": "array", "items": _external_evidence_schema()},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["web_search_results"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )
    registry.register(
        "fetch_web_page",
        "Fetch and extract text content from a whitelisted web page URL. "
        "Only available when allowWebSearch is authorized and a web-capable provider is configured.",
        {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "minLength": 1, "maxLength": 2048},
                "maxChars": {"type": "integer", "minimum": 1000, "maximum": 16000},
            },
            "additionalProperties": False,
        },
        _fetch_web_page_tool,
        output_schema={
            "type": "object",
            "required": ["status", "url", "content"],
            "properties": {
                "status": {"type": "string", "enum": ["success", "disabled", "budget_exceeded", "failed"]},
                "url": {"type": "string"},
                "content": {"type": "string"},
                "content_type": {"type": "string"},
                "content_length": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["web_page_content"],
            network_access=True,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
        ),
    )


def _retrieve_current_paper_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    pdf_id = _clean_text(payload.get("pdfId"))
    if not pdf_id:
        raise ToolValidationError("retrieve_current_paper requires a non-empty pdfId.")

    include_all = bool(payload.get("includeAll"))
    max_text_chars = _coerce_positive_int(payload.get("maxTextChars"), 900 if include_all else 700)
    rag = get_rag()
    normalized_pdf_id = rag.normalize_id(pdf_id)

    with trace_step(
        "tool_retrieve_current_paper",
        input_size=len(str(payload.get("query") or "")),
        meta={
            "pdfId": sanitize_text(normalized_pdf_id, max_chars=80),
            "includeAll": include_all,
        },
    ) as step:
        record_counter("retrievalCalls")
        if include_all:
            fetch_limit = _coerce_positive_int(payload.get("topK"), 120)
            normalize_limit = _coerce_positive_int(payload.get("limit"), 80)
            raw_items = rag.get_documents_by_metadata({"id": normalized_pdf_id}, limit=fetch_limit)
        else:
            query = _clean_text(payload.get("query"))
            if not query:
                raise ToolValidationError("retrieve_current_paper requires a non-empty query when includeAll is false.")
            top_k = _coerce_positive_int(payload.get("topK"), 8)
            normalize_limit = _coerce_positive_int(payload.get("limit"), 5)
            raw_items = rag.retrieve(query, top_k=top_k, filter_metadata={"id": normalized_pdf_id})

        normalized_items = normalize_evidence_items(
            raw_items,
            source_type="current_paper",
            pdf_id=normalized_pdf_id,
            limit=normalize_limit,
            max_text_chars=max_text_chars,
        )
        items = _ensure_stable_source_ids(normalized_items, fallback_prefix=normalized_pdf_id or "current-paper")
        step["outputSize"] = len(items)
        return {
            "items": items,
            "pdfId": normalized_pdf_id,
        }


def _retrieve_library_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = _clean_text(payload.get("query"))
    if not query:
        raise ToolValidationError("retrieve_library requires a non-empty query.")

    top_k = _coerce_positive_int(payload.get("topK"), 5)
    limit = _coerce_positive_int(payload.get("limit"), 4)
    max_text_chars = _coerce_positive_int(payload.get("maxTextChars"), 700)
    exclude_pdf_id = _clean_text(payload.get("excludePdfId"))

    with trace_step("tool_retrieve_library", input_size=len(query)) as step:
        record_counter("retrievalCalls")
        hybrid_results = retrieve_hybrid_results(query, top_k=top_k)
        vector_items = hybrid_results.get("vector", []) if isinstance(hybrid_results, dict) else []
        bm25_items = hybrid_results.get("bm25", []) if isinstance(hybrid_results, dict) else []
        normalized = normalize_evidence_items(
            [*vector_items, *bm25_items],
            source_type="library",
            limit=limit * 2,
            max_text_chars=max_text_chars,
        )

        rag = get_rag()
        normalized_exclude = rag.normalize_id(exclude_pdf_id) if exclude_pdf_id else None
        filtered: List[Dict[str, Any]] = []
        seen = set()
        for item in _ensure_stable_source_ids(normalized, fallback_prefix="library"):
            item_pdf_id = rag.normalize_id(item.get("pdfId")) if item.get("pdfId") else None
            if normalized_exclude and item_pdf_id == normalized_exclude:
                continue
            key = (str(item.get("sourceId") or ""), str(item.get("text") or "")[:120])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(item)
            if len(filtered) >= limit:
                break
        step["outputSize"] = len(filtered)
        return {"items": filtered}


def _retrieve_external_academic_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = _clean_text(payload.get("query"))
    safe_query = sanitize_external_academic_query_text(query, max_chars=256)
    if not query or safe_query != query:
        raise ToolValidationError(
            "retrieve_external_academic requires a safe academic query produced by the bounded query planner."
        )

    limit = int(payload.get("limit") or 5)
    year_from = payload.get("yearFrom")
    year_to = payload.get("yearTo")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ToolValidationError("retrieve_external_academic yearFrom must not exceed yearTo.")

    provider = _get_external_search_provider()
    provider_name = _resolve_provider_display_name(provider)
    query_summary = summarize_external_search_query(query)
    with trace_step(
        "tool_retrieve_external_academic",
        input_size=len(query),
        meta={
            "provider": provider_name if provider.enabled is True else "disabled",
            "querySummary": query_summary,
            "limit": limit,
            "budget": _external_search_budget_snapshot(),
        },
    ) as step:
        if provider.enabled is not True:
            step["meta"] = {
                **step.get("meta", {}),
                "status": "disabled",
                "reason": "external_search_disabled",
            }
            return {"status": "disabled", "provider": "disabled", "items": []}

        budget_reason = _external_search_budget_block_reason(limit)
        if budget_reason:
            record_counter("externalSearchBudgetBlocks")
            step["meta"] = {
                **step.get("meta", {}),
                "status": "budget_exceeded",
                "reason": budget_reason,
                "budget": _external_search_budget_snapshot(),
            }
            return {
                "status": "budget_exceeded",
                "provider": provider_name,
                "items": [],
                "reason": budget_reason,
            }

        started_at = time.perf_counter()
        try:
            raw_items = provider.search(query, limit)
        except Exception:
            record_counter("externalSearchFailures")
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            record_counter("externalSearchLatencyMs", elapsed_ms)
            step["meta"] = {
                **step.get("meta", {}),
                "status": "failed",
                "reason": "provider_failure",
                "latencyMs": elapsed_ms,
            }
            return {
                "status": "failed",
                "provider": provider_name,
                "items": [],
                "reason": "External academic provider failed.",
            }

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        record_counter("externalSearchCalls")
        record_counter("externalSearchLatencyMs", elapsed_ms)
        items = normalize_external_evidence_items(raw_items)
        if year_from is not None or year_to is not None:
            items = [
                item
                for item in items
                if item.get("year") is not None
                and (year_from is None or item["year"] >= year_from)
                and (year_to is None or item["year"] <= year_to)
            ]
        items = items[:limit]
        record_counter("externalEvidenceCount", len(items))
        step["outputSize"] = len(items)
        step["meta"] = {
            **step.get("meta", {}),
            "status": "success",
            "latencyMs": elapsed_ms,
            "providers": _resolve_provider_names_list(provider),
            "budget": _external_search_budget_snapshot(),
        }
        return {
            "status": "success",
            "provider": provider_name,
            "items": items,
        }


def _search_web_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    from services.safety_service import sanitize_web_search_query_text

    query = _clean_text(payload.get("query"))
    safe_query = sanitize_web_search_query_text(query, max_chars=300)
    if not query or safe_query != query:
        raise ToolValidationError(
            "search_web requires a safe query produced by the bounded query planner."
        )

    limit = int(payload.get("limit") or 5)
    search_type = _clean_text(payload.get("searchType") or "general")
    if search_type not in ("general", "academic", "news"):
        search_type = "general"

    provider = _get_external_search_provider()
    provider_name = _resolve_provider_display_name(provider)
    query_summary = summarize_external_search_query(query)
    with trace_step(
        "tool_search_web",
        input_size=len(query),
        meta={
            "provider": provider_name if provider.enabled is True else "disabled",
            "querySummary": query_summary,
            "limit": limit,
            "searchType": search_type,
            "budget": _web_search_budget_snapshot(),
        },
    ) as step:
        if provider.enabled is not True:
            step["meta"] = {**step.get("meta", {}), "status": "disabled", "reason": "web_search_disabled"}
            return {"status": "disabled", "provider": "disabled", "items": []}

        web_capable = bool(getattr(provider, "supports_web_search", False))
        if not web_capable:
            step["meta"] = {**step.get("meta", {}), "status": "disabled", "reason": "no_web_capable_provider"}
            return {
                "status": "disabled",
                "provider": provider_name,
                "items": [],
                "reason": "No web-capable provider configured.",
            }

        budget_reason = _web_search_budget_block_reason(limit)
        if budget_reason:
            record_counter("webSearchBudgetBlocks")
            step["meta"] = {
                **step.get("meta", {}),
                "status": "budget_exceeded",
                "reason": budget_reason,
                "budget": _web_search_budget_snapshot(),
            }
            return {
                "status": "budget_exceeded",
                "provider": provider_name,
                "items": [],
                "reason": budget_reason,
            }

        started_at = time.perf_counter()
        try:
            raw_items = provider.search(query, limit)
        except Exception:
            record_counter("webSearchFailures")
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            record_counter("webSearchLatencyMs", elapsed_ms)
            step["meta"] = {**step.get("meta", {}), "status": "failed", "reason": "provider_failure", "latencyMs": elapsed_ms}
            return {
                "status": "failed",
                "provider": provider_name,
                "items": [],
                "reason": "Web search provider failed.",
            }

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        record_counter("webSearchCalls")
        record_counter("webSearchLatencyMs", elapsed_ms)
        items = normalize_external_evidence_items(raw_items)
        items = items[:limit]
        record_counter("webSearchResults", len(items))
        step["outputSize"] = len(items)
        step["meta"] = {
            **step.get("meta", {}),
            "status": "success",
            "latencyMs": elapsed_ms,
            "providers": _resolve_provider_names_list(provider),
            "budget": _web_search_budget_snapshot(),
        }
        return {
            "status": "success",
            "provider": provider_name,
            "items": items,
        }


def _fetch_web_page_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    from services.url_whitelist import validate_fetch_url
    from services.web_fetcher import fetch_web_page as _fetch_page

    url = _clean_text(payload.get("url"))
    if not url:
        raise ToolValidationError("fetch_web_page requires a non-empty url.")

    # Validate URL through whitelist before any network access
    try:
        validate_fetch_url(url)
    except ValueError:
        raise ToolValidationError("fetch_web_page url must pass whitelist validation.")

    max_chars = int(payload.get("maxChars") or 16000)

    provider = _get_external_search_provider()
    provider_name = _resolve_provider_display_name(provider)

    with trace_step(
        "tool_fetch_web_page",
        input_size=len(url),
        meta={
            "provider": provider_name if provider.enabled is True else "disabled",
            "maxChars": max_chars,
            "budget": _web_fetch_budget_snapshot(),
        },
    ) as step:
        if provider.enabled is not True:
            return {"status": "disabled", "url": "", "content": "", "reason": "Web fetch is not enabled."}

        web_capable = bool(getattr(provider, "supports_web_search", False))
        if not web_capable:
            return {"status": "disabled", "url": "", "content": "", "reason": "No web-capable provider configured."}

        budget_reason = _web_fetch_budget_block_reason(max_chars)
        if budget_reason:
            record_counter("webFetchBudgetBlocks")
            return {
                "status": "budget_exceeded",
                "url": "",
                "content": "",
                "reason": budget_reason,
            }

        try:
            result = _fetch_page(url, max_chars=max_chars)
        except Exception:
            record_counter("webFetchFailures")
            return {"status": "failed", "url": "", "content": "", "reason": "Web fetch provider failed."}

        record_counter("webFetchCalls")
        content_len = len(result.content or "")
        record_counter("webFetchChars", content_len)
        record_counter("webFetchBytes", result.content_length or 0)
        if getattr(result, "cache_hit", False):
            record_counter("webFetchCacheHits")

        step["outputSize"] = content_len
        step["meta"] = {
            **step.get("meta", {}),
            "status": result.status,
            "latencyMs": result.elapsed_ms,
            "budget": _web_fetch_budget_snapshot(),
        }
        if result.status != "success":
            return {
                "status": "failed",
                "url": "",
                "content": "",
                "reason": result.status,
            }
        return {
            "status": "success",
            "url": result.url,
            "content": result.content,
            "content_type": result.content_type,
            "content_length": result.content_length,
        }
