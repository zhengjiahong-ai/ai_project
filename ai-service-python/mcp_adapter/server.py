import asyncio
from typing import Any, Dict, Optional, Set

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_adapter.adapter import call_mcp_tool, list_mcp_tools, verify_auth_token
from services.tool_registry import ToolRegistry, get_tool_registry

# ── Session registry (for multi-client support) ─────────────────────────────

_active_sessions: Dict[str, Dict[str, Any]] = {}
_session_lock = asyncio.Lock()


async def register_session(session_id: str) -> None:
    async with _session_lock:
        _active_sessions[session_id] = {
            "toolsCalled": 0,
            "errors": 0,
        }


async def record_tool_call(session_id: str, is_error: bool = False) -> None:
    async with _session_lock:
        session = _active_sessions.get(session_id)
        if session is None:
            return
        session["toolsCalled"] += 1
        if is_error:
            session["errors"] += 1


def get_session_count() -> int:
    return len(_active_sessions)


def build_server(
    registry: Optional[ToolRegistry] = None,
    require_auth: bool = False,
) -> Server:
    active_registry = registry or get_tool_registry()
    server = Server(
        "pixiu-readonly",
        version="0.2.0",
        instructions="Read-only access to bounded Pixiu paper skeleton and retrieval tools.",
    )

    @server.list_tools()
    async def handle_list_tools():
        return [types.Tool(**contract) for contract in list_mcp_tools(active_registry)]

    async def handle_call_tool(request: types.CallToolRequest):
        # Extract auth token from meta if present
        meta = getattr(request.params, "_meta", None) or {}
        session_id = meta.get("sessionId", "default")
        token = meta.get("authToken")

        if require_auth and not verify_auth_token(token):
            await record_tool_call(session_id, is_error=True)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text="Authentication required.")],
                isError=True,
            ))

        result = call_mcp_tool(
            request.params.name,
            request.params.arguments or {},
            active_registry,
        )
        await record_tool_call(session_id, is_error=result.get("isError", False))

        content = [types.TextContent(**item) for item in result["content"]]
        response_data: Dict[str, Any] = {
            "content": content,
            "isError": result["isError"],
        }
        if "structuredContent" in result:
            response_data["structuredContent"] = result["structuredContent"]
        return types.ServerResult(types.CallToolResult(**response_data))

    server.request_handlers[types.CallToolRequest] = handle_call_tool
    return server


async def _serve_stdio() -> None:
    import uuid

    session_id = uuid.uuid4().hex[:12]
    await register_session(session_id)
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_stdio_server() -> None:
    asyncio.run(_serve_stdio())
