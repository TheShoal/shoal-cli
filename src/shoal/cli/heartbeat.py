"""CLI command for pushing agent heartbeat to Shoal."""

from __future__ import annotations

import asyncio

import click

from shoal.models.state import SessionStatus


@click.command("heartbeat")
@click.argument("session")
@click.argument("status", type=click.Choice([s.value for s in SessionStatus]))
@click.option("--summary", default="", help="One-line description of current state")
@click.option("--turn-number", type=int, default=None, help="Turn counter (Pisces)")
@click.option("--tool-name", default=None, help="Last tool called (PostToolUse)")
def heartbeat_cli(
    session: str,
    status: str,
    summary: str,
    turn_number: int | None,
    tool_name: str | None,
) -> None:
    """Push a status heartbeat for a session."""
    from datetime import UTC, datetime

    from shoal.core.state import find_by_name, get_session, update_session
    from shoal.models.state import StatusSource

    async def _run() -> None:
        session_id = await find_by_name(session)
        if not session_id:
            s = await get_session(session)
            if not s:
                click.echo(f"Session not found: {session}", err=True)
                raise SystemExit(1)
            session_id = s.id

        parsed = SessionStatus(status)
        now = datetime.now(UTC)

        await update_session(
            session_id,
            status=parsed,
            status_source=StatusSource.hook,
            last_heartbeat=now,
        )

        if summary:
            from shoal.core.journal import append_entry

            await asyncio.to_thread(
                append_entry,
                session_id,
                f"[heartbeat] {summary}",
                "agent-hook",
            )

        click.echo(f"\u2713 {session}: {parsed.value} (source: hook)")

    asyncio.run(_run())
