"""MCP stdio-to-Unix-socket bridge — entry point for shoal-mcp-proxy.

Pure Python replacement for the former socat-based proxy.  Uses asyncio
to bridge stdin/stdout to a pooled MCP server's Unix domain socket.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress

from shoal.core.config import state_dir
from shoal.services.mcp_pool import validate_mcp_name

_CHUNK_SIZE = 65536
_CONNECT_TIMEOUT = 30  # seconds — max wait for socket connection
_IDLE_TIMEOUT = 120  # seconds — max silence between reads


async def _bridge(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Copy from *reader* to *writer* until EOF, with idle timeout."""
    try:
        while True:
            data = await asyncio.wait_for(reader.read(_CHUNK_SIZE), timeout=_IDLE_TIMEOUT)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, TimeoutError):
        pass
    finally:
        with suppress(Exception):
            writer.close()


async def _run_bridge(socket_path: str) -> None:
    """Open a connection to *socket_path* and bridge stdio ↔ socket."""
    loop = asyncio.get_running_loop()

    # Connect to the MCP server's Unix socket with timeout
    sock_reader, sock_writer = await asyncio.wait_for(
        asyncio.open_unix_connection(socket_path),
        timeout=_CONNECT_TIMEOUT,
    )

    # Wrap stdin/stdout as asyncio streams
    stdin_reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(stdin_reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    stdout_transport, stdout_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout.buffer
    )
    stdout_writer = asyncio.StreamWriter(
        stdout_transport,
        stdout_protocol,
        stdin_reader,
        loop,
    )

    # Bridge both directions concurrently; when either side closes, cancel the other
    done, pending = await asyncio.wait(
        [
            asyncio.ensure_future(_bridge(stdin_reader, sock_writer)),
            asyncio.ensure_future(_bridge(sock_reader, stdout_writer)),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()


def main() -> None:
    """Bridge stdio to a pooled MCP server's Unix socket."""
    if len(sys.argv) < 2 or not sys.argv[1]:
        print("Usage: shoal-mcp-proxy <mcp-name>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]

    try:
        validate_mcp_name(name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    socket = state_dir() / "mcp-pool" / "sockets" / f"{name}.sock"

    if not socket.exists():
        print(f"MCP socket not found: {socket}", file=sys.stderr)
        print(f"Start the server: shoal mcp start {name}", file=sys.stderr)
        sys.exit(1)

    with suppress(KeyboardInterrupt, BrokenPipeError):
        asyncio.run(_run_bridge(str(socket)))


if __name__ == "__main__":
    main()
