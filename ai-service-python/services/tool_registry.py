"""Pixiu Tool Registry – central tool registration and dispatch.

All tool handler functions have been extracted to services.tools.* sub-modules.
Shared utilities (budget tracking, text helpers, external search provider) live in
services.tools._common.
"""

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.tools._common import (
    _clean_text,
    _normalize_payload,
    reset_external_search_provider,
)

Handler = Callable[[dict[str, Any]], Any]

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
    inputSchema: dict[str, Any]
    outputSchema: dict[str, Any]
    safetyScope: dict[str, Any]
    handler: Handler


class ToolRegistry:
    schemaVersion = "1.0"

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Handler,
        version: str = "1.0.0",
        output_schema: dict[str, Any] | None = None,
        safety_scope: dict[str, Any] | None = None,
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

    def list_tools(self) -> list[dict[str, Any]]:
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

    def invoke(self, name: str, payload: dict[str, Any] | None = None) -> Any:
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
    reset_external_search_provider()


def _safety_scope(
    data_scopes: list[str],
    *,
    network_access: bool,
    sensitive_output: bool,
    access: str = "read_only",
    side_effects: bool = False,
) -> dict[str, Any]:
    return {
        "access": access,
        "dataScopes": data_scopes,
        "networkAccess": network_access,
        "sideEffects": side_effects,
        "sensitiveOutput": sensitive_output,
    }


def _object_output(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": True,
    }


def _external_evidence_schema() -> dict[str, Any]:
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
    """Build the default tool registry by delegating to each sub-module."""
    registry = ToolRegistry()

    from services.tools.code_tools import register_tools as _reg_code
    from services.tools.dialogue_monitor_tools import (
        register_tools as _reg_dialogue_monitor,
    )
    from services.tools.paper_tools import register_tools as _reg_paper
    from services.tools.research_tools import register_tools as _reg_research
    from services.tools.retrieval_tools import register_tools as _reg_retrieval

    _reg_retrieval(registry)
    _reg_paper(registry)
    _reg_code(registry)
    _reg_research(registry)
    _reg_dialogue_monitor(registry)

    return registry


# ── Schema validation helpers ───────────────────────────────────────────────

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


def _schema_types(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if not values or any(item not in _SUPPORTED_SCHEMA_TYPES for item in values):
        raise ToolValidationError(f"{label}.type must use supported schema types.")
    return values


def _validate_safety_scope(tool_name: str, safety_scope: dict[str, Any] | None) -> dict[str, Any]:
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


def _validate_value(value: Any, schema: dict[str, Any], tool_name: str, direction: str, path: str) -> None:
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
