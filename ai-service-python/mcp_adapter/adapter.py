import copy
import json
import os
from typing import Any, Dict, List, Optional

from services.tool_registry import ToolRegistry, ToolValidationError, get_tool_registry

# ── Configuration ───────────────────────────────────────────────────────────

DEFAULT_ALLOWED_TOOLS = (
    "read_paper_skeleton",
    "retrieve_current_paper",
    "retrieve_library",
)

DEFAULT_BUDGETS = {
    "retrieve_current_paper": {"topK": 8, "limit": 5, "maxTextChars": 900},
    "retrieve_library": {"topK": 5, "limit": 4, "maxTextChars": 700},
    "read_paper_skeleton": {"maxSections": 6, "maxCharsPerSection": 220},
}

_ALLOWED_DATA_SCOPES = {
    "request_paper_skeleton",
    "current_paper_index",
    "internal_library_index",
}

_config_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = os.getenv("PIXIU_MCP_CONFIG", "")
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                _config_cache = json.load(fh)
            return _config_cache
        except (json.JSONDecodeError, OSError):
            pass

    _config_cache = {}
    return _config_cache


def _get_config_value(key: str, default: Any) -> Any:
    config = _load_config()
    env_key = f"PIXIU_MCP_{key.upper()}"
    env_val = os.getenv(env_key, "").strip()
    if env_val:
        try:
            return json.loads(env_val)
        except json.JSONDecodeError:
            return env_val
    return config.get(key, default)


# ── Public API ──────────────────────────────────────────────────────────────

def is_mcp_enabled() -> bool:
    return os.getenv("PIXIU_MCP_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def get_allowed_tools() -> List[str]:
    configured = _get_config_value("tools", None)
    if isinstance(configured, list):
        return [t for t in configured if t in DEFAULT_ALLOWED_TOOLS]
    return list(DEFAULT_ALLOWED_TOOLS)


def get_tool_budgets() -> Dict[str, Dict[str, int]]:
    configured = _get_config_value("budgets", None)
    if isinstance(configured, dict):
        merged = copy.deepcopy(DEFAULT_BUDGETS)
        for tool_name, limits in configured.items():
            if tool_name in merged and isinstance(limits, dict):
                merged[tool_name].update({k: v for k, v in limits.items() if isinstance(v, int)})
        return merged
    return copy.deepcopy(DEFAULT_BUDGETS)


def verify_auth_token(token: Optional[str]) -> bool:
    expected = os.getenv("PIXIU_MCP_AUTH_TOKEN", "").strip()
    if not expected:
        return True  # no auth configured → open access
    return token == expected


def list_mcp_tools(registry: Optional[ToolRegistry] = None) -> List[Dict[str, Any]]:
    active_registry = registry or get_tool_registry()
    contracts = {contract["name"]: contract for contract in active_registry.list_tools()}
    budgets = get_tool_budgets()
    allowed = get_allowed_tools()

    tools: List[Dict[str, Any]] = []
    for name in allowed:
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
                    "runtimeBudgets": copy.deepcopy(budgets.get(name, {})),
                }
            },
        })
    return tools


def call_mcp_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    allowed = get_allowed_tools()
    if name not in allowed:
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


# ── Internal helpers ────────────────────────────────────────────────────────

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
    budgets = get_tool_budgets()
    for field, maximum in budgets.get(name, {}).items():
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
