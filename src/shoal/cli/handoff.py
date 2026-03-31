"""Handoff artifact commands."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from shoal.core.journal import (
    generate_handoff,
    read_journal,
    write_handoff_artifact,
)

console = Console()
app = typer.Typer(no_args_is_help=True)


def handoff_show(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    save: Annotated[bool, typer.Option("--save", help="Save artifact to disk")] = False,
) -> None:
    """Generate and display a handoff summary for a session."""
    import asyncio

    from shoal.core.db import get_db, with_db
    from shoal.core.state import _resolve_session_interactive_impl

    async def _impl() -> None:
        session_id = await _resolve_session_interactive_impl(session)
        if not session_id:
            console.print(f"[red]Session '{session}' not found[/red]")
            raise typer.Exit(1)

        from shoal.core.state import get_session

        session_state = await get_session(session_id)
        if not session_state:
            console.print(f"[red]Session '{session}' not found in DB[/red]")
            raise typer.Exit(1)

        entries = read_journal(session_id)
        db = await get_db()
        transitions = await db.get_status_transitions(session_id, limit=5)
        artifact = generate_handoff(session_state, entries, transitions)

        if save:
            path = write_handoff_artifact(session_id, artifact)
            console.print(f"[green]Saved:[/green] {path}")

        if as_json:
            console.print_json(json.dumps(artifact.to_dict()))
        else:
            console.print(Markdown(artifact.to_markdown()))

    asyncio.run(with_db(_impl()))


def handoff_ls() -> None:
    """List saved handoff artifacts."""
    from shoal.core.journal import _journals_dir

    handoffs_dir = _journals_dir() / "handoffs"
    if not handoffs_dir.exists():
        console.print("[dim]No handoff artifacts found.[/dim]")
        return

    artifacts = sorted(handoffs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not artifacts:
        console.print("[dim]No handoff artifacts found.[/dim]")
        return

    from rich.table import Table

    table = Table(show_header=True)
    table.add_column("Session ID", style="cyan")
    table.add_column("Modified", style="dim")
    table.add_column("Size")

    from datetime import datetime

    for path in artifacts:
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC)
        size = f"{st.st_size:,} B"
        table.add_row(path.stem, mtime.strftime("%Y-%m-%d %H:%M"), size)

    console.print(table)
