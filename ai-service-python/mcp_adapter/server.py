import asyncio
from typing import Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_adapter.adapter import call_mcp_tool, list_mcp_tools
from services.tool_registry import ToolRegistry, get_tool_registry


def build_server(registry: Optional[ToolRegistry] = None) -> Server:
    active_registry = registry or get_tool_registry()
    server = Server(
        "pixiu-readonly",
        version="0.1.0",
        instructions="Read-only access to bounded Pixiu paper skeleton and retrieval tools.",
    )

    @server.list_tools()
    async def handle_list_tools():
        return [types.Tool(**contract) for contract in list_mcp_tools(active_registry)]

    async def handle_call_tool(request: types.CallToolRequest):
        result = call_mcp_tool(
            request.params.name,
            request.params.arguments or {},
            active_registry,
        )
        content = [types.TextContent(**item) for item in result["content"]]
        response_data = {
            "content": content,
            "isError": result["isError"],
        }
        if "structuredContent" in result:
            response_data["structuredContent"] = result["structuredContent"]
        return types.ServerResult(types.CallToolResult(**response_data))

    server.request_handlers[types.CallToolRequest] = handle_call_tool
    return server


async def _serve_stdio() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_stdio_server() -> None:
    asyncio.run(_serve_stdio())
