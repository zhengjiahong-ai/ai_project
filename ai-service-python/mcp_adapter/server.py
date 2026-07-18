import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_adapter.adapter import call_mcp_tool, list_mcp_tools, verify_auth_token
from services.tool_registry import ToolRegistry, get_tool_registry

_logger = logging.getLogger(__name__)

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


# ── SSE / HTTP Transport ─────────────────────────────────────────────────────

_SSE_AUTH_HEADER = "x-pixiu-mcp-auth"


def _extract_sse_auth_token(scope: Dict[str, Any]) -> Optional[str]:
    """Extract auth token from HTTP headers in SSE transport."""
    headers = dict(scope.get("headers", []))
    raw = headers.get(_SSE_AUTH_HEADER.encode("latin-1"))
    if raw is not None:
        return raw.decode("latin-1")
    return None


def build_sse_app(
    registry: Optional[ToolRegistry] = None,
    require_auth: bool = False,
):
    """Build a Starlette ASGI app serving the MCP server over SSE.

    Returns a Starlette app with two routes:
      - ``GET /sse`` — SSE event stream endpoint (client connects here)
      - ``POST /messages/`` — message endpoint (client sends requests here)

    The app can be mounted into an existing FastAPI/Starlette app with
    ``app.mount("/mcp", build_sse_app())`` or run standalone via uvicorn.
    """
    try:
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route
        from starlette.requests import Request
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "SSE transport requires starlette. Install with: pip install starlette"
        ) from exc

    from mcp.server.sse import SseServerTransport

    active_registry = registry or get_tool_registry()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        session_id = uuid.uuid4().hex[:12]
        await register_session(session_id)

        if require_auth:
            token = request.headers.get(_SSE_AUTH_HEADER)
            if not verify_auth_token(token):
                return JSONResponse(
                    {"error": "Authentication required."}, status_code=401
                )

        async with sse.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[arg-type]
        ) as streams:
            server = build_server(active_registry, require_auth=False)
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    async def handle_messages(request: Request):
        if require_auth:
            token = request.headers.get(_SSE_AUTH_HEADER)
            if not verify_auth_token(token):
                return JSONResponse(
                    {"error": "Authentication required."}, status_code=401
                )

        await sse.handle_post_message(
            request.scope, request.receive, request._send  # type: ignore[arg-type]
        )

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )


def run_sse_server(
    host: str = "127.0.0.1",
    port: int = 8001,
    registry: Optional[ToolRegistry] = None,
    require_auth: bool = False,
) -> None:
    """Run the MCP server over SSE/HTTP (standalone via uvicorn)."""
    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        raise ImportError(
            "SSE server requires uvicorn. Install with: pip install uvicorn"
        )

    app = build_sse_app(registry=registry, require_auth=require_auth)
    _logger.info("Starting MCP SSE server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
