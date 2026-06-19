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
    global _DEFAULT_TOOL_REGISTRY
    _DEFAULT_TOOL_REGISTRY = None


def _safety_scope(data_scopes: List[str], *, network_access: bool, sensitive_output: bool) -> Dict[str, Any]:
    return {
        "access": "read_only",
        "dataScopes": data_scopes,
        "networkAccess": network_access,
        "sideEffects": False,
        "sensitiveOutput": sensitive_output,
    }


def _object_output(required: List[str], properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": True,
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
    return payload


_SUPPORTED_SCHEMA_KEYWORDS = {
    "type",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "enum",
    "minLength",
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
    for keyword in ("minLength", "minItems"):
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
    if scope["access"] != "read_only":
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope.access must be 'read_only'.")
    if not isinstance(scope["dataScopes"], list) or any(not _clean_text(item) for item in scope["dataScopes"]):
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope.dataScopes must be a list of non-empty strings.")
    for field in ("networkAccess", "sideEffects", "sensitiveOutput"):
        if not isinstance(scope[field], bool):
            raise ToolValidationError(f"Tool '{tool_name}' safetyScope.{field} must be boolean.")
    if scope["sideEffects"]:
        raise ToolValidationError(f"Tool '{tool_name}' safetyScope.sideEffects must be false.")
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
