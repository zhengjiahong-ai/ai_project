import sys
from typing import Callable, Optional, TextIO

from mcp_adapter.adapter import is_mcp_enabled


def main(
    run_server: Optional[Callable[[], None]] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    error_stream = stderr or sys.stderr
    if not is_mcp_enabled():
        print(
            "Pixiu MCP adapter is disabled. Set PIXIU_MCP_ENABLED=true to start the local stdio server.",
            file=error_stream,
        )
        return 2

    if run_server is None:
        from mcp_adapter.server import run_stdio_server

        run_server = run_stdio_server
    run_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
