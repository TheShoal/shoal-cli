"""Delegation wrapper — UNIX socket proxy for secure API key injection.

This module implements a UNIX socket proxy that allows API keys to be injected
securely without exposing them to the agent sandbox. The proxy intercepts API
requests and adds the necessary authentication headers.

The delegation proxy runs as a separate process and communicates with agents
via a UNIX socket. Agents send requests through the socket, and the proxy
adds secure environment variables (like API keys) before forwarding them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from shoal.core.config import data_dir

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger("shoal.delegation")

_CHUNK_SIZE = 65536


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    secure_env: dict[str, str],
) -> None:
    """Handle a client connection to the delegation proxy.

    Reads JSON-RPC style requests from the client, injects secure environment
    variables, executes the command, and streams the response back.

    Args:
        reader: Async stream reader for client input.
        writer: Async stream writer for client output.
        secure_env: Secure environment variables to inject (e.g., API keys).
    """
    addr = writer.get_extra_info("peername")
    logger.debug("New delegation connection from %s", addr)

    try:
        while True:
            # Read request
            data = await reader.read(_CHUNK_SIZE)
            if not data:
                break

            try:
                request = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                response = {"error": f"Invalid JSON: {e}"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                continue

            # Execute command with secure env injection
            command = request.get("command")
            args = request.get("args", [])
            env = request.get("env", {})

            if not command:
                response = {"error": "Missing 'command' field"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                continue

            # Merge environments: secure_env takes precedence
            full_env = os.environ.copy()
            full_env.update(env)
            full_env.update(secure_env)

            try:
                # Delegation proxy executes commands synchronously (acceptable for subprocess proxy)
                result = subprocess.run(
                    [command, *args],
                    env=full_env,
                    capture_output=True,
                    text=True,
                    timeout=request.get("timeout", 30),
                )
                response = {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,  # type: ignore[dict-item]
                }
            except subprocess.TimeoutExpired:
                response = {"error": "Command timed out"}
            except FileNotFoundError:
                response = {"error": f"Command not found: {command}"}
            except Exception as e:
                response = {"error": str(e)}

            writer.write(json.dumps(response).encode("utf-8"))
            await writer.drain()

    except ConnectionResetError:
        logger.debug("Client connection reset")
    except Exception as e:
        logger.exception("Error handling client: %s", e)
    finally:
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()


async def _serve(socket_path: str, secure_env: dict[str, str]) -> None:
    """Run the UNIX socket delegation server.

    Args:
        socket_path: Path to the UNIX socket file.
        secure_env: Secure environment variables to inject into proxied commands.
    """
    logger.info("Starting delegation proxy on %s", socket_path)

    # Ensure socket directory exists
    socket_file = Path(socket_path)
    socket_file.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale socket
    socket_file.unlink(missing_ok=True)

    server = await asyncio.start_unix_server(
        lambda r, w: _handle_client(r, w, secure_env),
        path=str(socket_file),
    )

    async with server:
        logger.info("Delegation proxy listening on %s", socket_path)
        await server.serve_forever()


def delegation_socket_path(session_id: str) -> Path:
    """Get the socket path for a session's delegation proxy.

    Args:
        session_id: The session UUID.

    Returns:
        Path to the UNIX socket file.
    """
    socket_dir = data_dir() / "delegation" / "sockets"
    socket_dir.mkdir(parents=True, exist_ok=True)
    return socket_dir / f"{session_id}.sock"


def start_delegation_proxy(
    session_id: str,
    secure_env: dict[str, str],
) -> subprocess.Popen[Any]:
    """Start a delegation proxy process for a session.

    Spawns a background process that runs the UNIX socket server. The proxy
    injects secure environment variables (like API keys) into all commands
    executed through it, keeping them hidden from the agent sandbox.

    Args:
        session_id: The session UUID (used for socket path).
        secure_env: Secure environment variables to inject.

    Returns:
        The subprocess.Popen handle for the proxy process.
    """
    socket_path = str(delegation_socket_path(session_id))

    # Create a minimal script to run the proxy
    proxy_script = f"""
import asyncio
import sys
sys.path.insert(0, '{Path(__file__).parent.parent.parent}')
from shoal.integrations.lobster.delegation_wrapper import _serve
asyncio.run(_serve('{socket_path}', {secure_env!r}))
"""

    env = os.environ.copy()
    env["SHOAL_DELEGATION_SOCKET"] = socket_path

    # Start the proxy as a background process
    proc = subprocess.Popen(
        [sys.executable, "-c", proxy_script],
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    logger.info("Started delegation proxy for session %s (PID %d)", session_id, proc.pid)
    return proc


def stop_delegation_proxy(session_id: str) -> None:
    """Stop a delegation proxy for a session.

    Removes the socket file. The proxy process should be killed separately
    if needed.

    Args:
        session_id: The session UUID.
    """
    socket_path = delegation_socket_path(session_id)
    socket_path.unlink(missing_ok=True)
    logger.debug("Stopped delegation proxy for session %s", session_id)


async def send_to_delegation_proxy(
    session_id: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Send a command to the delegation proxy for execution.

    Connects to the session's delegation proxy socket and requests command
    execution with secure environment injection.

    Args:
        session_id: The session UUID.
        command: Command to execute.
        args: Command arguments.
        env: Additional environment variables (secure ones will be merged).
        timeout: Request timeout in seconds.

    Returns:
        Dict with stdout, stderr, returncode, or error.

    Raises:
        FileNotFoundError: If socket doesn't exist.
        asyncio.TimeoutError: If request times out.
    """
    socket_path = delegation_socket_path(session_id)

    if not socket_path.exists():
        raise FileNotFoundError(f"Delegation proxy socket not found: {socket_path}")

    request = {
        "command": command,
        "args": args,
        "env": env or {},
        "timeout": timeout,
    }

    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write(json.dumps(request).encode("utf-8"))
        await writer.drain()

        response_data = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(_CHUNK_SIZE), timeout=5)
            if not chunk:
                break
            response_data += chunk
            # Try to parse as JSON - if successful, we have the full response
            try:
                return json.loads(response_data.decode("utf-8"))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                continue
        raise ConnectionError("Proxy connection closed without response")
    finally:
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()
