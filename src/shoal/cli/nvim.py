"""Neovim integration commands: send, diagnostics."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import ensure_dirs
from shoal.core.db import with_db
from shoal.core.state import (
    _resolve_session_interactive_impl,
    get_session,
    resolve_nvim_socket,
)

console = Console()

app = typer.Typer(no_args_is_help=True)


@app.command("send")
def nvim_send(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    command: Annotated[str, typer.Argument(help="Ex command to send")],
) -> None:
    """Send a command to a session's neovim."""
    asyncio.run(with_db(_nvim_send_impl(session, command)))


async def _nvim_send_impl(session: str, command: str) -> None:
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    socket = await resolve_nvim_socket(s)
    if not socket:
        console.print(f"[red]No nvim socket for session '{s.name}'[/red]")
        raise typer.Exit(1)

    if not await asyncio.to_thread(lambda: Path(socket).exists()):
        console.print(f"[red]Nvim socket not found: {socket}[/red]")
        console.print(f"Is nvim running in session '{s.name}'?")
        raise typer.Exit(1)

    if not shutil.which("nvr"):
        console.print("[red]nvr not found — install with: pip install neovim-remote[/red]")
        raise typer.Exit(1)

    await asyncio.to_thread(
        subprocess.run,
        ["nvr", "--servername", socket, "--remote-send", f"<C-\\><C-n>:{command}<CR>"],
        check=False,
    )
    console.print(f"Sent to {s.name} nvim: :{command}")


@app.command("diagnostics")
def nvim_diagnostics(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
) -> None:
    """Get LSP diagnostics from a session's neovim."""
    asyncio.run(with_db(_nvim_diagnostics_impl(session)))


_DIAGNOSTICS_LUA = """\
local diags = vim.diagnostic.get(0)
local out = {}
for _, d in ipairs(diags) do
  local fname = vim.api.nvim_buf_get_name(d.bufnr)
  local sev = vim.diagnostic.severity[d.severity] or "?"
  table.insert(out, string.format("%s:%d: [%s] %s", fname, d.lnum + 1, sev, d.message))
end
return table.concat(out, "\\n")
"""


async def _nvim_diagnostics_impl(session: str) -> None:
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    socket = await resolve_nvim_socket(s)
    if not socket:
        console.print(f"[red]No nvim socket for session '{s.name}'[/red]")
        raise typer.Exit(1)

    if not await asyncio.to_thread(lambda: Path(socket).exists()):
        console.print(f"[red]Nvim socket not found: {socket}[/red]")
        console.print(f"Is nvim running in session '{s.name}'?")
        raise typer.Exit(1)

    if not shutil.which("nvr"):
        console.print("[red]nvr not found — install with: pip install neovim-remote[/red]")
        raise typer.Exit(1)

    # Write Lua to a temp file to avoid shell quoting issues with luaeval()
    with tempfile.NamedTemporaryFile(
        suffix=".lua", prefix="shoal-diag-", mode="w", delete=False
    ) as f:
        f.write(_DIAGNOSTICS_LUA)
        lua_file = Path(f.name)
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "nvr",
                "--servername",
                socket,
                "--remote-expr",
                f"luaeval('dofile([[{lua_file}]])')",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    finally:
        await asyncio.to_thread(lambda: lua_file.unlink(missing_ok=True))

    if not result.stdout.strip():
        console.print(f"No diagnostics for session '{s.name}'")
    else:
        console.print(f"Diagnostics for session '{s.name}':")
        console.print(result.stdout)
