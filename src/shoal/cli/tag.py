"""CLI commands for session tagging."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.db import with_db
from shoal.core.state import add_tag, get_session, remove_tag, resolve_session

console = Console()

app = typer.Typer(no_args_is_help=True)


@app.command("add")
def tag_add(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    tag: Annotated[str, typer.Argument(help="Tag to add")],
) -> None:
    """Add a tag to a session."""
    asyncio.run(with_db(_tag_add_impl(session, tag)))


async def _tag_add_impl(session: str, tag: str) -> None:
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    await add_tag(sid, tag)
    console.print(f"Tag '{tag}' added to session '{session}'")


@app.command("remove")
def tag_remove(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    tag: Annotated[str, typer.Argument(help="Tag to remove")],
) -> None:
    """Remove a tag from a session."""
    asyncio.run(with_db(_tag_remove_impl(session, tag)))


async def _tag_remove_impl(session: str, tag: str) -> None:
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    await remove_tag(sid, tag)
    console.print(f"Tag '{tag}' removed from session '{session}'")


@app.command("ls")
def tag_ls(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
) -> None:
    """List tags for a session."""
    asyncio.run(with_db(_tag_ls_impl(session)))


async def _tag_ls_impl(session: str) -> None:
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    s = await get_session(sid)
    if not s:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    if s.tags:
        for tag in s.tags:
            console.print(tag)
    else:
        console.print("[dim]No tags[/dim]")
