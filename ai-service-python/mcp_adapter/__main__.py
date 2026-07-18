import os
import sys
from typing import Callable, Optional, TextIO

from mcp_adapter.adapter import is_mcp_enabled

_VALID_TRANSPORTS = ("stdio", "sse")


def _resolve_transport() -> str:
    raw = os.environ.get("PIXIU_MCP_TRANSPORT", "stdio").strip().lower()
    if raw not in _VALID_TRANSPORTS:
        print(
            f"Unknown PIXIU_MCP_TRANSPORT={raw!r}. Supported: {', '.join(_VALID_TRANSPORTS)}.",
            file=sys.stderr,
        )
        return "stdio"
    return raw


def main(
    run_server: Optional[Callable[[], None]] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    error_stream = stderr or sys.stderr
    if not is_mcp_enabled():
        print(
            "Pixiu MCP adapter is disabled. Set PIXIU_MCP_ENABLED=true to start the local server.",
            file=error_stream,
        )
        return 2

    if run_server is None:
        transport = _resolve_transport()
        if transport == "sse":
            from mcp_adapter.server import run_sse_server

            host = os.environ.get("PIXIU_MCP_SSE_HOST", "127.0.0.1")
            port = int(os.environ.get("PIXIU_MCP_SSE_PORT", "8001"))
            run_server = lambda: run_sse_server(host=host, port=port)
        else:
            from mcp_adapter.server import run_stdio_server

            run_server = run_stdio_server
    run_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
