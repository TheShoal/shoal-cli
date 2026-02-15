"""MCP stdio-to-Unix-socket bridge — entry point for shoal-mcp-proxy."""

from __future__ import annotations

import os
import sys

from shoal.core.config import state_dir


def main() -> None:
    """Bridge stdio to a pooled MCP server's Unix socket via socat."""
    if len(sys.argv) < 2:
        print("Usage: shoal-mcp-proxy <mcp-name>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]
    socket = state_dir() / "mcp-pool" / "sockets" / f"{name}.sock"

    if not socket.exists():
        print(f"MCP socket not found: {socket}", file=sys.stderr)
        print(f"Start the server: shoal mcp start {name}", file=sys.stderr)
        sys.exit(1)

    os.execvp("socat", ["socat", "STDIO", f"UNIX-CONNECT:{socket}"])


if __name__ == "__main__":
    main()
