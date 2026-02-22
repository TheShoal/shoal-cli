"""MCP server lifecycle management (pure Python, no socat dependency).

Each MCP server is a long-lived process that listens on a Unix domain
socket.  When a client connects, the pool spawns a fresh instance of the
MCP command and bridges the client's connection to the command's
stdin/stdout.  This replaces the former socat-based approach.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from contextlib import suppress
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


# Well-known MCP server commands (kept as private fallback; prefer registry)
_DEFAULT_SERVERS: dict[str, str] = {
    "memory": "npx -y @modelcontextprotocol/server-memory",
    "filesystem": "npx -y @modelcontextprotocol/server-filesystem",
    "github": "npx -y @modelcontextprotocol/server-github",
    "fetch": "npx -y @modelcontextprotocol/server-fetch",
}

# Public alias kept for backward compatibility in tests / direct imports.
KNOWN_SERVERS = _DEFAULT_SERVERS


def mcp_log_dir() -> Path:
    """Return the MCP pool log directory."""
    return state_dir() / "mcp-pool" / "logs"


def mcp_log_file(name: str) -> Path:
    """Return the log file path for a named MCP server."""
    return mcp_log_dir() / f"{name}.log"


def _truncate_log(path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
    """If *path* exceeds *max_bytes*, truncate to the last half."""
    if not path.exists():
        return
    size = path.stat().st_size
    if size <= max_bytes:
        return
    keep = max_bytes // 2
    with open(path, "r+b") as f:
        f.seek(size - keep)
        tail = f.read()
        f.seek(0)
        f.write(tail)
        f.truncate()


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

    The server is a Python subprocess that runs an asyncio Unix socket
    listener.  Each client connection spawns the MCP command and bridges
    the socket I/O to the command's stdin/stdout.

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

    # Resolve command via configurable registry
    if not command:
        from shoal.core.config import load_mcp_registry

        registry = load_mcp_registry()
        command = registry.get(name)
        if not command:
            raise ValueError(
                f"Unknown MCP server: {name}\n"
                "Provide --command or add it to ~/.config/shoal/mcp-servers.toml\n"
                "Known servers: " + ", ".join(registry)
            )

    socket.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Set up log file for stderr
    log_dir = mcp_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = mcp_log_file(name)
    _truncate_log(log_path)

    log_fh = open(log_path, "a")  # noqa: SIM115

    # Launch the pool server as a detached subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "shoal.services.mcp_pool", name, command],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=log_fh,
    )

    # Wait briefly to see if it starts
    time.sleep(1)
    if proc.poll() is not None:
        log_fh.close()
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


# ---------------------------------------------------------------------------
# Async server entry point (invoked as ``python -m shoal.services.mcp_pool``)
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 65536
_CONNECT_TIMEOUT = 30  # seconds — max wait for first data after accept
_IDLE_TIMEOUT = 120  # seconds — max silence between reads


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    command: str,
    log_path: Path | None = None,
) -> None:
    """Handle a single client connection by spawning the MCP command."""
    tokens = shlex.split(command)
    log_fh = None
    stderr_dest: int | None = asyncio.subprocess.DEVNULL
    if log_path is not None:
        with suppress(OSError):
            log_fh = await asyncio.to_thread(open, log_path, "a")
    try:
        proc = await asyncio.create_subprocess_exec(
            *tokens,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=log_fh if log_fh is not None else stderr_dest,
        )
    except Exception:
        if log_fh is not None:
            log_fh.close()
        client_writer.close()
        return

    assert proc.stdin is not None
    assert proc.stdout is not None

    async def _copy(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter | asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                data = await asyncio.wait_for(reader.read(_CHUNK_SIZE), timeout=_IDLE_TIMEOUT)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            pass

    try:
        _done, pending = await asyncio.wait(
            [
                asyncio.ensure_future(_copy(client_reader, proc.stdin)),
                asyncio.ensure_future(_copy(proc.stdout, client_writer)),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        with suppress(Exception):
            proc.kill()
        with suppress(Exception):
            client_writer.close()
        if log_fh is not None:
            with suppress(Exception):
                log_fh.close()


async def _serve(socket_path: str, command: str, log_path: Path | None = None) -> None:
    """Run the Unix socket server loop."""

    async def _on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_client(reader, writer, command, log_path=log_path)

    server = await asyncio.start_unix_server(_on_connect, path=socket_path)
    async with server:
        await server.serve_forever()


def _pool_main() -> None:
    """Entry point when invoked as ``python -m shoal.services.mcp_pool <name> <command>``."""
    if len(sys.argv) < 3:
        print("Usage: python -m shoal.services.mcp_pool <name> <command>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]
    command = sys.argv[2]
    socket_path = str(mcp_socket(name))

    # Set up log file
    log_dir = mcp_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = mcp_log_file(name)
    _truncate_log(log_path)

    # Clean stale socket
    Path(socket_path).unlink(missing_ok=True)
    Path(socket_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(_serve(socket_path, command, log_path=log_path))
    except KeyboardInterrupt:
        pass
    finally:
        Path(socket_path).unlink(missing_ok=True)


if __name__ == "__main__":
    _pool_main()
