"""CLI command for viewing and appending to session journals."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from shoal.core.db import with_db
from shoal.core.journal import append_entry, journal_exists, read_journal
from shoal.core.state import resolve_session

console = Console()


def journal_view(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    append: Annotated[str | None, typer.Option("--append", "-a", help="Append entry text")] = None,
    source: Annotated[str, typer.Option("--source", "-s", help="Entry source tag")] = "cli",
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Show last N entries")] = None,
) -> None:
    """View or append to a session journal."""
    import asyncio

    async def _impl() -> str | None:
        return await resolve_session(session)

    session_id = asyncio.run(with_db(_impl()))
    if not session_id:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    if append:
        path = append_entry(session_id, append, source=source)
        console.print(f"[green]Entry appended to {path.name}[/green]")
        return

    if not journal_exists(session_id):
        console.print(f"[yellow]No journal for session '{session}'[/yellow]")
        return

    entries = read_journal(session_id, limit=limit)
    if not entries:
        console.print("[yellow]Journal is empty[/yellow]")
        return

    for entry in entries:
        ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        src_tag = f" [{entry.source}]" if entry.source else ""
        header = f"### {ts}{src_tag}"
        console.print(Markdown(header))
        console.print(Markdown(entry.content))
        console.print("[dim]---[/dim]")
