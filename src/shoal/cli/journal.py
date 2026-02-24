"""CLI command for viewing and appending to session journals."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from shoal.core.db import with_db
from shoal.core.journal import (
    JournalEntry,
    append_entry,
    archived_journal_path,
    journal_exists,
    read_archived_journal,
    read_journal,
)
from shoal.core.state import resolve_session

console = Console()


def journal_view(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    append: Annotated[str | None, typer.Option("--append", "-a", help="Append entry text")] = None,
    source: Annotated[str, typer.Option("--source", "-s", help="Entry source tag")] = "cli",
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Show last N entries")] = None,
    archived: Annotated[
        bool, typer.Option("--archived", help="Read from archived journal")
    ] = False,
) -> None:
    """View or append to a session journal."""
    import asyncio

    from shoal.core.journal import build_journal_metadata
    from shoal.core.state import get_session
    from shoal.models.state import SessionState

    if archived:
        _view_archived(session, limit=limit)
        return

    async def _impl() -> tuple[str | None, SessionState | None]:
        sid = await resolve_session(session)
        if not sid:
            return None, None
        state = await get_session(sid)
        return sid, state

    session_id, session_state = asyncio.run(with_db(_impl()))
    if not session_id:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    if append:
        metadata = None
        if not journal_exists(session_id) and session_state:
            metadata = build_journal_metadata(session_state)
        path = append_entry(session_id, append, source=source, metadata=metadata)
        console.print(f"[green]Entry appended to {path.name}[/green]")
        return

    if not journal_exists(session_id):
        console.print(f"[yellow]No journal for session '{session}'[/yellow]")
        return

    entries = read_journal(session_id, limit=limit)
    if not entries:
        console.print("[yellow]Journal is empty[/yellow]")
        return

    _render_entries(entries)


def _view_archived(session: str, *, limit: int | None = None) -> None:
    """Display an archived journal by session name or ID."""
    # Archived journals are keyed by session ID.  The user may pass either
    # a session name or an ID, so we try direct ID lookup first, then fall
    # back to DB resolution (the session row may still exist in stopped state).
    import asyncio

    path = archived_journal_path(session)
    if path.exists():
        session_id = session
    else:
        # Try resolving via DB in case user passed a name
        async def _resolve() -> str | None:
            return await resolve_session(session)

        session_id = asyncio.run(with_db(_resolve()))
        if not session_id:
            console.print(f"[red]No archived journal found for '{session}'[/red]")
            raise typer.Exit(1)

    entries = read_archived_journal(session_id, limit=limit)
    if not entries:
        console.print(f"[yellow]No archived journal found for '{session}'[/yellow]")
        return

    console.print(f"[dim]Archived journal for {session}[/dim]\n")
    _render_entries(entries)


def _render_entries(entries: list[JournalEntry]) -> None:
    """Render journal entries to the console."""

    for entry in entries:
        ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        src_tag = f" [{entry.source}]" if entry.source else ""
        header = f"### {ts}{src_tag}"
        console.print(Markdown(header))
        console.print(Markdown(entry.content))
        console.print("[dim]---[/dim]")
