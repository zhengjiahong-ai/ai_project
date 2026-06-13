import copy
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import services.analysis_service as analysis_service
import services.background_knowledge_service as background_knowledge_service
import services.page_translation_service as page_translation_service
from rag.store import get_rag, retrieve_hybrid_results
from schemas.requests import BackgroundKnowledgeRequest, DeepAnalysisRequest, PageTranslationRequest
from services.evidence_service import normalize_evidence_items
from services.retrieval_judge_service import judge_evidence_quality
from services.trace_service import record_counter, sanitize_text, trace_step


Handler = Callable[[Dict[str, Any]], Any]

_DEFAULT_TOOL_REGISTRY = None


class ToolNotFoundError(KeyError):
    pass


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    inputSchema: Dict[str, Any]
    handler: Handler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Handler,
    ) -> ToolDefinition:
        tool_name = _clean_text(name)
        if not tool_name:
            raise ToolValidationError("Tool name cannot be empty.")
        if not callable(handler):
            raise ToolValidationError(f"Handler for tool '{tool_name}' must be callable.")

        definition = ToolDefinition(
            name=tool_name,
            description=_clean_text(description),
            inputSchema=copy.deepcopy(input_schema or {"type": "object"}),
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

    def list_tools(self) -> List[ToolDefinition]:
        return [self._tools[name] for name in sorted(self._tools)]

    def invoke(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        definition = self.get(name)
        normalized_payload = _normalize_payload(payload)
        _validate_payload(normalized_payload, definition.inputSchema)
        return definition.handler(copy.deepcopy(normalized_payload))


def get_tool_registry() -> ToolRegistry:
    global _DEFAULT_TOOL_REGISTRY
    if _DEFAULT_TOOL_REGISTRY is None:
        _DEFAULT_TOOL_REGISTRY = _build_default_tool_registry()
    return _DEFAULT_TOOL_REGISTRY


def reset_tool_registry() -> None:
    global _DEFAULT_TOOL_REGISTRY
    _DEFAULT_TOOL_REGISTRY = None


def _build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "retrieve_current_paper",
        "Retrieve evidence from the current indexed paper.",
        {
            "type": "object",
            "required": ["pdfId"],
            "properties": {
                "pdfId": {"type": "string"},
                "query": {"type": "string"},
                "topK": {"type": "integer"},
                "limit": {"type": "integer"},
                "maxTextChars": {"type": "integer"},
                "includeAll": {"type": "boolean"},
            },
        },
        _retrieve_current_paper_tool,
    )
    registry.register(
        "retrieve_library",
        "Retrieve evidence from the internal literature library.",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "excludePdfId": {"type": "string"},
                "topK": {"type": "integer"},
                "limit": {"type": "integer"},
                "maxTextChars": {"type": "integer"},
            },
        },
        _retrieve_library_tool,
    )
    registry.register(
        "read_paper_skeleton",
        "Normalize a paper skeleton into reusable planning context.",
        {
            "type": "object",
            "properties": {
                "paperSkeleton": {"type": "object"},
                "maxSections": {"type": "integer"},
                "maxCharsPerSection": {"type": "integer"},
            },
        },
        _read_paper_skeleton_tool,
    )
    registry.register(
        "judge_evidence",
        "Judge whether retrieved evidence is sufficient for a question.",
        {
            "type": "object",
            "required": ["question", "evidenceItems"],
            "properties": {
                "question": {"type": "string"},
                "evidenceItems": {"type": "array"},
                "keywords": {"type": "array"},
            },
        },
        _judge_evidence_tool,
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
        },
        _generate_background_graph_tool,
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
        },
        _run_critical_analysis_tool,
    )
    registry.register(
        "translate_page",
        "Translate a PDF page using the existing page translation service.",
        {
            "type": "object",
            "required": ["pageIndex", "pageText"],
            "properties": {
                "pdfId": {"type": "string"},
                "pageIndex": {"type": "integer"},
                "pageText": {"type": "string"},
                "paperSkeleton": {"type": "object"},
                "pageLayout": {"type": "object"},
            },
        },
        _translate_page_tool,
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


def _normalize_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ToolValidationError("Tool payload must be an object.")
    return payload


def _validate_payload(payload: Dict[str, Any], input_schema: Dict[str, Any]) -> None:
    schema = input_schema or {}
    schema_type = schema.get("type")
    if schema_type and schema_type != "object":
        raise ToolValidationError("Tool inputSchema.type must be 'object'.")

    required_fields = schema.get("required") or []
    for field in required_fields:
        if field not in payload:
            raise ToolValidationError(f"Missing required field: {field}")

    properties = schema.get("properties") or {}
    for key, value in payload.items():
        property_schema = properties.get(key) or {}
        expected_type = property_schema.get("type")
        if expected_type:
            _validate_value_type(key, value, expected_type)


def _validate_value_type(field: str, value: Any, expected_type: str) -> None:
    if value is None:
        return

    matches = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }
    if expected_type in matches and not matches[expected_type]:
        raise ToolValidationError(f"Field '{field}' must be of type {expected_type}.")


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
