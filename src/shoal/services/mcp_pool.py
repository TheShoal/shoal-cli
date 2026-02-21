"""MCP server lifecycle management (socat start/stop/health)."""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path

from shoal.core.config import state_dir

# MCP server name validation
_MCP_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def validate_mcp_name(name: str) -> None:
    """Validate MCP server name for safety.

    Names are used in file paths (socket/pid files) and tmux env vars.

    Raises:
        ValueError: If name is invalid.
    """
    if not name:
        raise ValueError("MCP server name cannot be empty")
    if not _MCP_NAME_RE.match(name):
        raise ValueError(
            f"Invalid MCP name '{name}': must be 1-64 alphanumeric characters, "
            "dashes, or underscores, starting with a letter or digit"
        )


# Well-known MCP server commands
KNOWN_SERVERS: dict[str, str] = {
    "memory": "npx -y @modelcontextprotocol/server-memory",
    "filesystem": "npx -y @modelcontextprotocol/server-filesystem",
    "github": "npx -y @modelcontextprotocol/server-github",
    "fetch": "npx -y @modelcontextprotocol/server-fetch",
}


def mcp_socket(name: str) -> Path:
    return state_dir() / "mcp-pool" / "sockets" / f"{name}.sock"


def mcp_pid_file(name: str) -> Path:
    return state_dir() / "mcp-pool" / "pids" / f"{name}.pid"


def read_pid(name: str) -> int | None:
    pf = mcp_pid_file(name)
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except ValueError:
        return None


def is_mcp_running(name: str) -> bool:
    pid = read_pid(name)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def start_mcp_server(name: str, command: str | None = None) -> tuple[int, Path, str]:
    """Start an MCP server. Returns (pid, socket_path, command_used).

    Raises ValueError if name is invalid or command can't be determined.
    Raises RuntimeError if server fails to start.
    """
    validate_mcp_name(name)
    socket = mcp_socket(name)
    pid_file = mcp_pid_file(name)

    # Check if already running
    if socket.exists() and is_mcp_running(name):
        pid = read_pid(name)
        raise RuntimeError(f"MCP server '{name}' is already running (pid: {pid})")

    # Clean up stale socket
    socket.unlink(missing_ok=True)

    # Resolve command
    if not command:
        command = KNOWN_SERVERS.get(name)
        if not command:
            raise ValueError(
                f"Unknown MCP server: {name}\n"
                "Provide --command or use a known server: " + ", ".join(KNOWN_SERVERS)
            )

    socket.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Start socat proxy — quote command to prevent shell injection via config values
    safe_command = " ".join(shlex.quote(tok) for tok in shlex.split(command))
    proc = subprocess.Popen(
        [
            "socat",
            f"UNIX-LISTEN:{socket},fork,reuseaddr",
            f"EXEC:{safe_command},pipes",
        ],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait briefly to see if it starts
    time.sleep(1)
    if proc.poll() is not None:
        socket.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to start MCP server '{name}'")

    pid_file.write_text(str(proc.pid))
    return proc.pid, socket, command


def stop_mcp_server(name: str) -> None:
    """Stop an MCP server. Raises FileNotFoundError if not running."""
    validate_mcp_name(name)
    pid_file = mcp_pid_file(name)
    socket = mcp_socket(name)

    if not pid_file.exists():
        raise FileNotFoundError(f"MCP server '{name}' is not running")

    pid = read_pid(name)
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass

    pid_file.unlink(missing_ok=True)
    socket.unlink(missing_ok=True)
