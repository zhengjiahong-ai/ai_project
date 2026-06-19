import copy
import json
import os
from typing import Any, Dict, List, Optional

from services.tool_registry import ToolRegistry, ToolValidationError, get_tool_registry


MCP_ALLOWED_TOOL_NAMES = (
    "read_paper_skeleton",
    "retrieve_current_paper",
    "retrieve_library",
)

_ALLOWED_DATA_SCOPES = {
    "request_paper_skeleton",
    "current_paper_index",
    "internal_library_index",
}

_MCP_BUDGETS = {
    "retrieve_current_paper": {
        "topK": 8,
        "limit": 5,
        "maxTextChars": 900,
    },
    "retrieve_library": {
        "topK": 5,
        "limit": 4,
        "maxTextChars": 700,
    },
    "read_paper_skeleton": {
        "maxSections": 6,
        "maxCharsPerSection": 220,
    },
}


def is_mcp_enabled() -> bool:
    return os.getenv("PIXIU_MCP_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def list_mcp_tools(registry: Optional[ToolRegistry] = None) -> List[Dict[str, Any]]:
    active_registry = registry or get_tool_registry()
    contracts = {contract["name"]: contract for contract in active_registry.list_tools()}
    tools: List[Dict[str, Any]] = []
    for name in MCP_ALLOWED_TOOL_NAMES:
        contract = contracts.get(name)
        if contract is None or not _is_safe_contract(contract):
            continue
        tools.append({
            "name": contract["name"],
            "description": contract["description"],
            "inputSchema": copy.deepcopy(contract["inputSchema"]),
            "outputSchema": copy.deepcopy(contract["outputSchema"]),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
            "_meta": {
                "pixiu": {
                    "schemaVersion": active_registry.schemaVersion,
                    "version": contract["version"],
                    "safetyScope": copy.deepcopy(contract["safetyScope"]),
                    "runtimeBudgets": copy.deepcopy(_MCP_BUDGETS[name]),
                }
            },
        })
    return tools


def call_mcp_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    if name not in MCP_ALLOWED_TOOL_NAMES:
        return _error_result(f"Tool '{name}' is not available through the read-only MCP adapter.")

    payload = arguments if isinstance(arguments, dict) else arguments
    try:
        _enforce_runtime_policy(name, payload)
        result = (registry or get_tool_registry()).invoke(name, payload)
    except ToolValidationError as error:
        return _error_result(str(error))
    except Exception:
        return _error_result(f"Tool '{name}' failed safely.")

    return {
        "content": [{"type": "text", "text": _json_text(result)}],
        "structuredContent": copy.deepcopy(result),
        "isError": False,
    }


def _is_safe_contract(contract: Dict[str, Any]) -> bool:
    scope = contract.get("safetyScope") or {}
    data_scopes = set(scope.get("dataScopes") or [])
    return (
        scope.get("access") == "read_only"
        and scope.get("sideEffects") is False
        and scope.get("networkAccess") is False
        and data_scopes.issubset(_ALLOWED_DATA_SCOPES)
    )


def _enforce_runtime_policy(name: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    if name == "retrieve_current_paper" and payload.get("includeAll") is True:
        raise ToolValidationError(
            "tool 'retrieve_current_paper' input $.includeAll: full-paper export is disabled for MCP."
        )
    for field, maximum in _MCP_BUDGETS[name].items():
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value > maximum:
            raise ToolValidationError(
                f"tool '{name}' input $.{field}: MCP value must be at most {maximum}."
            )


def _error_result(message: str) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
