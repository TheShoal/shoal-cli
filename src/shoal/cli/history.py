"""CLI command for viewing session status transition history."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core.db import get_db, with_db
from shoal.core.state import resolve_session
from shoal.core.theme import STATUS_STYLES, Symbols, create_panel

console = Console()


def history(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max transitions to show")] = 50,
) -> None:
    """Show status transition history for a session."""
    asyncio.run(with_db(_history_impl(session, limit)))


async def _history_impl(session: str, limit: int) -> None:
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    db = await get_db()
    transitions = await db.get_status_transitions(sid, limit=limit)

    if not transitions:
        console.print(f"[yellow]No status transitions recorded for '{session}'[/yellow]")
        return

    # Transitions are ordered desc — reverse for chronological display
    transitions.reverse()

    table = Table(show_header=True, header_style="bold cyan", padding=(0, 1))
    table.add_column("Timestamp", style="dim")
    table.add_column("From")
    table.add_column("")
    table.add_column("To")
    table.add_column("Duration", justify="right")

    for i, t in enumerate(transitions):
        ts = _format_timestamp(t["timestamp"])
        from_styled = _style_status(t["from_status"])
        to_styled = _style_status(t["to_status"])

        # Duration = time until next transition (or "current" for last)
        if i + 1 < len(transitions):
            duration = _duration_between(t["timestamp"], transitions[i + 1]["timestamp"])
        else:
            duration = "[dim]current[/dim]"

        table.add_row(ts, from_styled, Symbols.ARROW, to_styled, duration)

    console.print(
        create_panel(table, title=f"[bold]Status History: {session}[/bold]", title_align="left")
    )
    console.print(f"[dim]{len(transitions)} transition(s)[/dim]")


def _format_timestamp(iso: str) -> str:
    """Format an ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso


def _style_status(status: str) -> str:
    """Apply Rich style to a status string."""
    style = STATUS_STYLES.get(status)
    if style:
        return f"[{style.rich}]{status}[/{style.rich}]"
    return status


def _duration_between(start_iso: str, end_iso: str) -> str:
    """Compute human-friendly duration between two ISO timestamps."""
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        delta = end - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes, seconds = divmod(total_seconds, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    except (ValueError, TypeError):
        return "?"
