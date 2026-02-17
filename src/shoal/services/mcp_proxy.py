"""MCP stdio-to-Unix-socket bridge — entry point for shoal-mcp-proxy."""

from __future__ import annotations

import os
import re
import sys

from shoal.core.config import state_dir

# MCP server names must be plain identifiers (letters, digits, dash, underscore)
_VALID_MCP_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def main() -> None:
    """Bridge stdio to a pooled MCP server's Unix socket via socat."""
    if len(sys.argv) < 2 or not sys.argv[1]:
        print("Usage: shoal-mcp-proxy <mcp-name>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]

    if not _VALID_MCP_NAME.match(name):
        print(
            f"Error: Invalid MCP server name: {name!r}\n"
            "Names must contain only letters, digits, dashes, and underscores.",
            file=sys.stderr,
        )
        sys.exit(1)
    socket = state_dir() / "mcp-pool" / "sockets" / f"{name}.sock"

    if not socket.exists():
        print(f"MCP socket not found: {socket}", file=sys.stderr)
        print(f"Start the server: shoal mcp start {name}", file=sys.stderr)
        sys.exit(1)

    os.execvp("socat", ["socat", "STDIO", f"UNIX-CONNECT:{socket}"])


if __name__ == "__main__":
    main()
