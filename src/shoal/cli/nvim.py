"""Neovim integration commands: send, diagnostics."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import ensure_dirs
from shoal.core.db import with_db
from shoal.core.state import (
    get_session,
    resolve_session_interactive,
    _resolve_session_interactive_impl,
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


async def _nvim_send_impl(session, command):
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not s.nvim_socket:
        console.print(f"[red]No nvim socket for session '{s.name}'[/red]")
        raise typer.Exit(1)

    if not Path(s.nvim_socket).exists():
        console.print(f"[red]Nvim socket not found: {s.nvim_socket}[/red]")
        console.print(f"Is nvim running in session '{s.name}'?")
        raise typer.Exit(1)

    if not shutil.which("nvr"):
        console.print("[red]nvr not found — install with: pip install neovim-remote[/red]")
        raise typer.Exit(1)

    subprocess.run(
        ["nvr", "--servername", s.nvim_socket, "--remote-send", f"<C-\\><C-n>:{command}<CR>"],
        check=False,
    )
    console.print(f"Sent to {s.name} nvim: :{command}")


@app.command("diagnostics")
def nvim_diagnostics(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
) -> None:
    """Get LSP diagnostics from a session's neovim."""
    asyncio.run(with_db(_nvim_diagnostics_impl(session)))


async def _nvim_diagnostics_impl(session):
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not s.nvim_socket:
        console.print(f"[red]No nvim socket for session '{s.name}'[/red]")
        raise typer.Exit(1)

    if not Path(s.nvim_socket).exists():
        console.print(f"[red]Nvim socket not found: {s.nvim_socket}[/red]")
        console.print(f"Is nvim running in session '{s.name}'?")
        raise typer.Exit(1)

    if not shutil.which("nvr"):
        console.print("[red]nvr not found — install with: pip install neovim-remote[/red]")
        raise typer.Exit(1)

    lua_cmd = (
        "local diags = vim.diagnostic.get(0); "
        "local out = {}; "
        "for _, d in ipairs(diags) do "
        'table.insert(out, string.format("%s:%d: [%s] %s", '
        "vim.api.nvim_buf_get_name(d.bufnr), d.lnum + 1, "
        'vim.diagnostic.severity[d.severity] or "?", d.message)) end; '
        'return table.concat(out, "\\n")'
    )

    result = subprocess.run(
        ["nvr", "--servername", s.nvim_socket, "--remote-expr", f"luaeval('{lua_cmd}')"],
        capture_output=True,
        text=True,
        check=False,
    )

    if not result.stdout.strip():
        console.print(f"No diagnostics for session '{s.name}'")
    else:
        console.print(f"Diagnostics for session '{s.name}':")
        console.print(result.stdout)
