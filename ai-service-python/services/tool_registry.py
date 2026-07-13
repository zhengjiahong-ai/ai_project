import copy
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import services.analysis_service as analysis_service
import services.background_knowledge_service as background_knowledge_service
import services.knowledge_graph_store as knowledge_graph_store
import services.page_translation_service as page_translation_service
from rag.store import get_rag, retrieve_hybrid_results
from schemas.requests import BackgroundKnowledgeRequest, DeepAnalysisRequest, PageTranslationRequest
from services.evidence_service import normalize_evidence_items
from services.external_evidence import normalize_external_evidence_items
from services.external_search_provider import create_external_search_provider
from services.retrieval_judge_service import judge_evidence_quality
from services.safety_service import sanitize_external_academic_query_text
from services.trace_service import (
    get_current_trace_id,
    get_trace_snapshot,
    record_counter,
    sanitize_text,
    summarize_external_search_query,
    trace_step,
)

from services.code_execution_models import IDENTIFIER_PATTERN, create_code_execution_job
from code_worker import FIXED_TEMPLATE_TEXT


Handler = Callable[[Dict[str, Any]], Any]

_DEFAULT_TOOL_REGISTRY = None
_DEFAULT_EXTERNAL_SEARCH_PROVIDER = None
EXTERNAL_SEARCH_CALL_BUDGET = 10
EXTERNAL_SEARCH_EVIDENCE_BUDGET = 40
WEB_SEARCH_CALL_BUDGET = 20
WEB_SEARCH_RESULT_BUDGET = 50
WEB_FETCH_CALL_BUDGET = 30
WEB_FETCH_CHAR_BUDGET = 200_000

_MAX_TOKENS_PER_TASK_DEFAULT = 500_000


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


class ToolNotFoundError(KeyError):
    pass


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    inputSchema: Dict[str, Any]
    outputSchema: Dict[str, Any]
    safetyScope: Dict[str, Any]
    handler: Handler


class ToolRegistry:
    schemaVersion = "1.0"

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Handler,
        version: str = "1.0.0",
        output_schema: Optional[Dict[str, Any]] = None,
        safety_scope: Optional[Dict[str, Any]] = None,
    ) -> ToolDefinition:
        tool_name = _clean_text(name)
        if not tool_name:
            raise ToolValidationError("Tool name cannot be empty.")
        if tool_name in self._tools:
            raise ToolValidationError(f"Tool '{tool_name}' is already registered.")
        tool_version = _clean_text(version)
        if not re.fullmatch(r"\d+\.\d+\.\d+", tool_version):
            raise ToolValidationError(f"Tool '{tool_name}' version must use SemVer (for example 1.0.0).")
        tool_description = _clean_text(description)
        if not tool_description:
            raise ToolValidationError(f"Tool '{tool_name}' description cannot be empty.")
        if not callable(handler):
            raise ToolValidationError(f"Handler for tool '{tool_name}' must be callable.")

        normalized_input_schema = copy.deepcopy(input_schema or {"type": "object"})
        normalized_output_schema = copy.deepcopy(output_schema or {"type": "object"})
        _validate_schema_definition(normalized_input_schema, f"tool '{tool_name}' inputSchema", require_object_root=True)
        _validate_schema_definition(normalized_output_schema, f"tool '{tool_name}' outputSchema", require_object_root=True)
        normalized_safety_scope = _validate_safety_scope(tool_name, safety_scope)

        definition = ToolDefinition(
            name=tool_name,
            version=tool_version,
            description=tool_description,
            inputSchema=normalized_input_schema,
            outputSchema=normalized_output_schema,
            safetyScope=normalized_safety_scope,
            handler=handler,
        )
        self._tools[tool_name] = definition
        return definition

    def get(self, name: str) -> ToolDefinition:
        tool_name = _clean_text(name)
        definition = self._tools.get(tool_name)
        if definition is None:
            raise ToolNotFoundError(f"Unknown tool: {tool_name}")
        return definition

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "version": definition.version,
                "description": definition.description,
                "inputSchema": copy.deepcopy(definition.inputSchema),
                "outputSchema": copy.deepcopy(definition.outputSchema),
                "safetyScope": copy.deepcopy(definition.safetyScope),
            }
            for name in sorted(self._tools)
            for definition in [self._tools[name]]
        ]

    def invoke(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        definition = self.get(name)
        normalized_payload = _normalize_payload(payload)
        _validate_value(normalized_payload, definition.inputSchema, definition.name, "input", "$")
        response = definition.handler(copy.deepcopy(normalized_payload))
        _validate_value(response, definition.outputSchema, definition.name, "output", "$")
        return copy.deepcopy(response)


def get_tool_registry() -> ToolRegistry:
    global _DEFAULT_TOOL_REGISTRY
    if _DEFAULT_TOOL_REGISTRY is None:
        _DEFAULT_TOOL_REGISTRY = _build_default_tool_registry()
    return _DEFAULT_TOOL_REGISTRY


def reset_tool_registry() -> None:
    global _DEFAULT_TOOL_REGISTRY, _DEFAULT_EXTERNAL_SEARCH_PROVIDER
    _DEFAULT_TOOL_REGISTRY = None
    _DEFAULT_EXTERNAL_SEARCH_PROVIDER = None


def _safety_scope(
    data_scopes: List[str],
    *,
    network_access: bool,
    sensitive_output: bool,
    access: str = "read_only",
    side_effects: bool = False,
) -> Dict[str, Any]:
    return {
        "access": access,
        "dataScopes": data_scopes,
        "networkAccess": network_access,
        "sideEffects": side_effects,
        "sensitiveOutput": sensitive_output,
    }


def _object_output(required: List[str], properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": True,
    }


def _external_evidence_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "sourceId", "sourceType", "provider", "providerId", "title", "authors",
            "year", "abstract", "doi", "url", "retrievedAt", "query", "license",
        ],
        "properties": {
            "sourceId": {"type": "string", "minLength": 1},
            "sourceType": {"type": "string", "enum": ["external_academic"]},
            "provider": {"type": "string", "minLength": 1},
            "providerId": {"type": "string"},
            "title": {"type": "string"},
            "authors": {"type": "array", "items": {"type": "string"}},
            "year": {"type": ["integer", "null"], "minimum": 1000, "maximum": 9999},
            "abstract": {"type": "string"},
            "doi": {"type": "string"},
            "url": {"type": "string"},
            "retrievedAt": {"type": "string"},
            "query": {"type": "string"},
            "license": {"type": "string"},
            "provenance": {
                "type": "object",
                "required": [
                    "discoveryPath", "searchQuery", "searchIteration",
                    "sourceUrl", "retrievalTimestamp",
                ],
                "properties": {
                    "discoveryPath": {"type": "string"},
                    "searchQuery": {"type": "string"},
                    "searchIteration": {"type": ["integer", "null"]},
                    "sourceUrl": {"type": "string"},
                    "retrievalTimestamp": {"type": "string"},
                },
            },
        },
        "additionalProperties": False,
    }


def _build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
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
        "read_paper_skeleton",
        "Normalize a paper skeleton into reusable planning context.",
        {
            "type": "object",
            "properties": {
                "paperSkeleton": {"type": "object"},
                "maxSections": {"type": "integer", "minimum": 1, "maximum": 50},
                "maxCharsPerSection": {"type": "integer", "minimum": 1, "maximum": 5000},
            },
            "additionalProperties": False,
        },
        _read_paper_skeleton_tool,
        output_schema=_object_output(
            ["text", "sections"],
            {
                "text": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        safety_scope=_safety_scope(["request_paper_skeleton"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "judge_evidence",
        "Judge whether retrieved evidence is sufficient for a question.",
        {
            "type": "object",
            "required": ["question", "evidenceItems"],
            "properties": {
                "question": {"type": "string", "minLength": 1},
                "evidenceItems": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "keywords": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "additionalProperties": False,
        },
        _judge_evidence_tool,
        output_schema=_object_output(
            ["verdict", "confidence", "reason", "missingAspects", "shouldRetry", "judgeScore", "coverage", "retryReason"],
            {
                "verdict": {"type": "string", "enum": ["CORRECT", "AMBIGUOUS", "INCORRECT"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
                "missingAspects": {"type": "array", "items": {"type": "string"}},
                "shouldRetry": {"type": "boolean"},
                "judgeScore": {"type": "integer", "minimum": 0, "maximum": 100},
                "coverage": {"type": "object", "additionalProperties": True},
                "retryReason": {"type": "string"},
                "reflection": {"type": "string"},
                "suggestedQueries": {"type": "array", "items": {"type": "string"}},
            },
        ),
        safety_scope=_safety_scope(["provided_evidence"], network_access=False, sensitive_output=False),
    )
    registry.register(
        "generate_background_graph",
        "Generate prerequisite background knowledge graph and learning path.",
        {
            "type": "object",
            "properties": {
                "paper_topic": {},
                "user_knowledge_level": {},
                "reader_profile": {"type": "object"},
                "behavior_signals": {"type": "object"},
                "pdfId": {"type": "string"},
                "paperSkeleton": {"type": "object"},
                "paperStructure": {"type": "object"},
            },
            "additionalProperties": False,
        },
        _generate_background_graph_tool,
        output_schema=_object_output(
            ["background_knowledge"],
            {"background_knowledge": {"type": "array", "items": {"type": "string"}}},
        ),
        safety_scope=_safety_scope(
            ["request_context", "current_paper_index", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "run_critical_analysis",
        "Run evidence-based critical analysis for a paper.",
        {
            "type": "object",
            "properties": {
                "paper_content": {"type": "string"},
                "pdf_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        _run_critical_analysis_tool,
        output_schema=_object_output(
            ["claimed_contributions", "evidence_based_contributions", "overclaim_risks", "missing_evidence", "rag_sources"],
            {
                "claimed_contributions": {"type": "string"},
                "evidence_based_contributions": {"type": "string"},
                "overclaim_risks": {"type": "array", "items": {"type": "string"}},
                "missing_evidence": {"type": "array", "items": {"type": "string"}},
                "rag_sources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
        ),
        safety_scope=_safety_scope(
            ["request_content", "current_paper_index", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "translate_page",
        "Translate a PDF page using the existing page translation service.",
        {
            "type": "object",
            "required": ["pageIndex", "pageText"],
            "properties": {
                "pdfId": {"type": "string", "minLength": 1},
                "pageIndex": {"type": "integer", "minimum": 0},
                "pageText": {"type": "string", "minLength": 1},
                "paperSkeleton": {"type": "object"},
                "pageLayout": {"type": "object"},
            },
            "additionalProperties": False,
        },
        _translate_page_tool,
        output_schema=_object_output(
            ["status", "pageIndex", "sourceText", "translatedText", "translatedBlocks", "renderMode"],
            {
                "status": {"type": "string", "enum": ["success"]},
                "pageIndex": {"type": "integer", "minimum": 0},
                "sourceText": {"type": "string"},
                "translatedText": {"type": "string"},
                "translatedBlocks": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "renderMode": {"type": "string", "enum": ["overlay", "plain"]},
            },
        ),
        safety_scope=_safety_scope(
            ["request_page_text", "model_provider"],
            network_access=True,
            sensitive_output=True,
        ),
    )
    registry.register(
        "read_knowledge_graph_neighborhood",
        "Read a bounded one-hop neighborhood from persisted background knowledge graphs.",
        {
            "type": "object",
            "properties": {
                "paperIds": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "sourceIds": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "seedTerms": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": 8},
                "maxEdges": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "additionalProperties": False,
        },
        _read_knowledge_graph_neighborhood_tool,
        output_schema=_object_output(
            ["status", "paperIds", "seedTerms", "nodes", "edges", "sourceIds", "provenanceSummary", "contextNote"],
            {
                "status": {"type": "string", "enum": ["available", "partial", "unavailable"]},
                "paperIds": {"type": "array", "items": {"type": "string"}},
                "seedTerms": {"type": "array", "items": {"type": "string"}},
                "nodes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "edges": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "provenanceSummary": {"type": "object", "additionalProperties": True},
                "contextNote": {"type": "string", "minLength": 1},
            },
        ),
        safety_scope=_safety_scope(["knowledge_graph_snapshots"], network_access=False, sensitive_output=True),
    )
    registry.register(
        "run_descriptive_statistics",
        "Create a sandboxed descriptive-statistics job for an approved CSV artifact. "
        "Execution requires human approval and runs without network access.",
        {
            "type": "object",
            "required": ["artifactId"],
            "properties": {
                "artifactId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "additionalProperties": False,
        },
        _run_descriptive_statistics_tool,
        output_schema={
            "type": "object",
            "required": ["status", "jobId", "artifactId", "templateId"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "awaiting_approval", "approved", "queued", "running",
                        "succeeded", "failed", "cancelled", "rejected",
                    ],
                },
                "jobId": {"type": "string", "minLength": 1},
                "artifactId": {"type": "string", "minLength": 1},
                "templateId": {"type": "string"},
                "statistics": {"type": "object"},
                "message": {"type": "string"},
            },
            "additionalProperties": False,
        },
        safety_scope=_safety_scope(
            ["code_execution_artifact"],
            network_access=False,
            sensitive_output=True,
            access="restricted",
            side_effects=True,
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
    return registry


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


def _get_external_search_provider() -> Any:
    global _DEFAULT_EXTERNAL_SEARCH_PROVIDER
    if _DEFAULT_EXTERNAL_SEARCH_PROVIDER is None:
        _DEFAULT_EXTERNAL_SEARCH_PROVIDER = create_external_search_provider()
    return _DEFAULT_EXTERNAL_SEARCH_PROVIDER


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


def _external_search_budget_snapshot() -> Dict[str, int]:
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


def _web_search_budget_snapshot() -> Dict[str, int]:
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


def _web_fetch_budget_snapshot() -> Dict[str, int]:
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


def _read_paper_skeleton_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    paper_skeleton = payload.get("paperSkeleton") if isinstance(payload.get("paperSkeleton"), dict) else {}
    max_sections = _coerce_positive_int(payload.get("maxSections"), 6)
    max_chars_per_section = _coerce_positive_int(payload.get("maxCharsPerSection"), 220)

    with trace_step("tool_read_paper_skeleton", input_size=len(paper_skeleton)) as step:
        sections = []
        for key, value in paper_skeleton.items():
            text = _clean_text(value)
            if not text:
                continue
            sections.append({
                "key": str(key),
                "text": text[:max_chars_per_section],
            })
            if len(sections) >= max_sections:
                break
        rendered_text = "\n".join(f"{section['key']}: {section['text']}" for section in sections)
        step["outputSize"] = len(sections)
        return {
            "text": rendered_text,
            "sections": sections,
        }


def _judge_evidence_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = _clean_text(payload.get("question"))
    evidence_items = payload.get("evidenceItems")
    if not question:
        raise ToolValidationError("judge_evidence requires a non-empty question.")
    if not isinstance(evidence_items, list):
        raise ToolValidationError("judge_evidence requires evidenceItems to be a list.")

    with trace_step("tool_judge_evidence", input_size=len(evidence_items)) as step:
        result = judge_evidence_quality(question, evidence_items, keywords=payload.get("keywords") or [])
        step["outputSize"] = len(result.get("missingAspects") or [])
        return result


def _read_knowledge_graph_neighborhood_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    with trace_step("tool_read_knowledge_graph_neighborhood", input_size=len(payload)) as step:
        result = knowledge_graph_store.read_graph_neighborhood(payload)
        step["outputSize"] = len(result.get("nodes") or [])
        return result


def _generate_background_graph_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    with trace_step("tool_generate_background_graph", input_size=len(payload)) as step:
        response = background_knowledge_service.get_background_knowledge(BackgroundKnowledgeRequest(**payload))
        step["outputSize"] = len(response.get("background_knowledge") or [])
        return response


def _run_critical_analysis_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    with trace_step("tool_run_critical_analysis", input_size=len(payload)) as step:
        response = analysis_service.deep_analysis(DeepAnalysisRequest(**payload))
        step["outputSize"] = len(response.get("rag_sources") or [])
        return response


def _translate_page_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    with trace_step("tool_translate_page", input_size=len(str(payload.get("pageText") or ""))) as step:
        response = page_translation_service.translate_page(PageTranslationRequest(**payload))
        step["outputSize"] = len(str(response.get("translatedText") or ""))
        return response


def _run_descriptive_statistics_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    artifact_id = _clean_text(payload.get("artifactId"))
    if not artifact_id:
        raise ToolValidationError("run_descriptive_statistics requires a non-empty artifactId.")
    if not IDENTIFIER_PATTERN.fullmatch(artifact_id):
        raise ToolValidationError(
            "run_descriptive_statistics artifactId must be an opaque identifier, not a path or URI."
        )
    if len(artifact_id) > 128:
        raise ToolValidationError("run_descriptive_statistics artifactId exceeds maximum length.")

    script_text = FIXED_TEMPLATE_TEXT

    with trace_step("tool_run_descriptive_statistics", input_size=len(artifact_id)) as step:
        job = create_code_execution_job(
            job_id=f"job-{artifact_id}",
            artifact_id=artifact_id,
            artifact_digest="0" * 64,
            script_text=script_text,
        )
        step["outputSize"] = 1
        return {
            "status": job.status,
            "jobId": job.job_id,
            "artifactId": artifact_id,
            "templateId": job.runtime.template_id,
            "message": "Job created. Requires execution approval before the sandbox runs.",
        }


def _normalize_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {}
    return payload


_SUPPORTED_SCHEMA_KEYWORDS = {
    "type",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "enum",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
}
_SUPPORTED_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}
_SAFETY_SCOPE_FIELDS = {"access", "dataScopes", "networkAccess", "sideEffects", "sensitiveOutput"}


def _validate_schema_definition(schema: Any, label: str, *, require_object_root: bool = False) -> None:
    if not isinstance(schema, dict):
        raise ToolValidationError(f"{label} must be an object.")
    unsupported = sorted(set(schema) - _SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        raise ToolValidationError(f"{label} uses unsupported schema keyword '{unsupported[0]}'.")

    declared_types = _schema_types(schema.get("type"), label)
    if require_object_root and declared_types != ["object"]:
        raise ToolValidationError(f"{label}.type must be 'object'.")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
            raise ToolValidationError(f"{label}.required must be a list of non-empty strings.")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise ToolValidationError(f"{label}.properties must be an object.")
        for key, child_schema in properties.items():
            if not isinstance(key, str) or not key:
                raise ToolValidationError(f"{label}.properties keys must be non-empty strings.")
            _validate_schema_definition(child_schema, f"{label}.properties.{key}")
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise ToolValidationError(f"{label}.additionalProperties must be boolean.")
    if "items" in schema:
        _validate_schema_definition(schema["items"], f"{label}.items")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ToolValidationError(f"{label}.enum must be a non-empty list.")
    for keyword in ("minLength", "maxLength", "minItems"):
        if keyword in schema and (not isinstance(schema[keyword], int) or isinstance(schema[keyword], bool) or schema[keyword] < 0):
            raise ToolValidationError(f"{label}.{keyword} must be a non-negative integer.")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and (not isinstance(schema[keyword], (int, float)) or isinstance(schema[keyword], bool)):
            raise ToolValidationError(f"{label}.{keyword} must be numeric.")


def _schema_types(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if not values or any(item not in _SUPPORTED_SCHEMA_TYPES for item in values):
        raise ToolValidationError(f"{label}.type must use supported schema types.")
    return values


def _validate_safety_scope(tool_name: str, safety_scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scope = copy.deepcopy(safety_scope or {})
    missing = sorted(_SAFETY_SCOPE_FIELDS - set(scope))
    if missing:
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope is missing field '{missing[0]}'.")
    unknown = sorted(set(scope) - _SAFETY_SCOPE_FIELDS)
    if unknown:
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope has unknown field '{unknown[0]}'.")
    if scope["access"] not in ("read_only", "restricted"):
        raise ToolValidationError(
            f"Tool '{tool_name}' safetyScope.access has unknown access level '{scope['access']}'."
        )
    if not isinstance(scope["dataScopes"], list) or any(not _clean_text(item) for item in scope["dataScopes"]):
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope.dataScopes must be a list of non-empty strings.")
    for field in ("networkAccess", "sideEffects", "sensitiveOutput"):
        if not isinstance(scope[field], bool):
            raise ToolValidationError(f"Tool '{tool_name}' safetyScope.{field} must be boolean.")
    if scope["sideEffects"] and scope["access"] != "restricted":
        raise ToolValidationError(
            f"Tool '{tool_name}' safetyScope.sideEffects must be false for '{scope['access']}' access."
        )
    if scope["access"] == "restricted" and not scope["sideEffects"]:
        raise ToolValidationError(
            f"Tool '{tool_name}' safetyScope.sideEffects must be true for restricted access."
        )
    return scope


def _validate_value(value: Any, schema: Dict[str, Any], tool_name: str, direction: str, path: str) -> None:
    types = _schema_types(schema.get("type"), f"tool '{tool_name}' {direction} schema at {path}")
    if types and not any(_matches_schema_type(value, expected_type) for expected_type in types):
        expected = " or ".join(types)
        raise ToolValidationError(f"tool '{tool_name}' {direction} {path}: expected {expected}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(f"tool '{tool_name}' {direction} {path}: value must be one of {schema['enum']}.")
    if isinstance(value, str) and "minLength" in schema and len(value.strip()) < schema["minLength"]:
        raise ToolValidationError(
            f"tool '{tool_name}' {direction} {path}: length must be at least {schema['minLength']}."
        )
    if isinstance(value, str) and "maxLength" in schema and len(value) > schema["maxLength"]:
        raise ToolValidationError(
            f"tool '{tool_name}' {direction} {path}: maxLength must be at most {schema['maxLength']}."
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolValidationError(
                f"tool '{tool_name}' {direction} {path}: value must be at least {schema['minimum']}."
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolValidationError(
                f"tool '{tool_name}' {direction} {path}: value must be at most {schema['maximum']}."
            )
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for field in schema.get("required") or []:
            if field not in value:
                raise ToolValidationError(f"tool '{tool_name}' {direction} {path}.{field}: required field is missing.")
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    raise ToolValidationError(f"tool '{tool_name}' {direction} {path}.{field}: unknown field.")
        for field, child_value in value.items():
            if field in properties:
                _validate_value(child_value, properties[field], tool_name, direction, f"{path}.{field}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ToolValidationError(
                f"tool '{tool_name}' {direction} {path}: item count must be at least {schema['minItems']}."
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate_value(item, item_schema, tool_name, direction, f"{path}[{index}]")


def _matches_schema_type(value: Any, expected_type: str) -> bool:
    return {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "null": value is None,
    }[expected_type]


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _ensure_stable_source_ids(items: List[Dict[str, Any]], fallback_prefix: str) -> List[Dict[str, Any]]:
    stabilized: List[Dict[str, Any]] = []
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
