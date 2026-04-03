"""Session management commands: attach, detach, rename, prune, popup."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated

import typer

from shoal.cli._console import get_console
from shoal.core import tmux
from shoal.core.config import ensure_dirs
from shoal.core.db import with_db
from shoal.core.journal import archive_journal
from shoal.core.session_names import (
    is_shoal_tmux_session_name,
    validate_session_name,
)
from shoal.core.state import (
    _resolve_session_interactive_impl,
    delete_session,
    find_by_name,
    get_session,
    list_sessions,
    touch_session,
    update_session,
)
from shoal.models.state import SessionStatus
from shoal.services.runtime_provider import provider_for_session


def attach(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    asyncio.run(with_db(_attach_impl(session)))


async def _attach_impl(session_name_or_id: str | None) -> None:
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session_name_or_id)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)
    provider = provider_for_session(s)
    if not provider.exists(s):
        get_console().print(
            "[red]Runtime session "
            f"'{s.tmux_runtime.session_name}' not found (session may have died)[/red]"
        )
        await update_session(sid, status=SessionStatus.stopped)
        raise typer.Exit(1)

    await touch_session(sid)
    provider.attach(s)


def detach() -> None:
    """Detach from current session."""
    if not tmux.is_inside_tmux():
        get_console().print("[red]Not inside a tmux session[/red]")
        raise typer.Exit(1)

    current = tmux.current_session_name()
    if not is_shoal_tmux_session_name(current):
        get_console().print(f"[red]Not inside a shoal session (current: {current})[/red]")
        raise typer.Exit(1)

    tmux.detach_client()


def rename(
    old_name: Annotated[str, typer.Argument(help="Current session name or ID")],
    new_name: Annotated[str, typer.Argument(help="New name for the session")],
) -> None:
    """Rename a session."""
    asyncio.run(with_db(_rename_impl(old_name, new_name)))


async def _rename_impl(old_name: str, new_name: str) -> None:
    ensure_dirs()
    from shoal.core.state import resolve_session

    # Validate new name
    try:
        validate_session_name(new_name)
    except ValueError as e:
        get_console().print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from e

    sid = await resolve_session(old_name)
    if not sid:
        get_console().print(f"[red]Session not found: {old_name}[/red]")
        raise typer.Exit(1)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if await find_by_name(new_name):
        get_console().print(f"[red]Session with name '{new_name}' already exists[/red]")
        raise typer.Exit(1)

    updated_runtime = await provider_for_session(s).async_rename(s, new_name)
    await update_session(sid, name=new_name, runtime=updated_runtime)
    get_console().print(f"Renamed session: {s.name} → {new_name}")


def prune(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Do not ask for confirmation")
    ] = False,
) -> None:
    """Remove all sessions marked as stopped."""
    asyncio.run(with_db(_prune_impl(force)))


async def _prune_impl(force: bool) -> None:
    ensure_dirs()
    sessions = await list_sessions()
    stopped = [s for s in sessions if s.status.value == "stopped"]

    if not stopped:
        get_console().print("No stopped sessions to prune")
        return

    if not force:
        get_console().print()
        get_console().print(f"Found {len(stopped)} stopped sessions:")
        for s in stopped:
            get_console().print(f"  - {s.name} ({s.id})")
        if not typer.confirm("Are you sure you want to remove these?"):
            raise typer.Abort

    for s in stopped:
        with contextlib.suppress(OSError):
            await asyncio.to_thread(archive_journal, s.id)
        await delete_session(s.id)
        get_console().print(f"Removed session '{s.name}' ({s.id})")


def send(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    keys: Annotated[str, typer.Argument(help="Keys to send (empty string sends Enter)")],
) -> None:
    """Send keys to a session's tmux pane."""
    asyncio.run(with_db(_send_impl(session, keys)))


async def _send_impl(session_name_or_id: str, keys: str) -> None:
    ensure_dirs()
    from shoal.core.state import resolve_session

    sid = await resolve_session(session_name_or_id)
    if not sid:
        get_console().print(f"[red]Session not found: {session_name_or_id}[/red]")
        raise typer.Exit(1)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)
    pane_target = tmux.preferred_pane(s.tmux_runtime.session_name, title=f"shoal:{s.id}")
    tmux.send_keys(pane_target, keys)


def popup() -> None:
    """Open tmux popup dashboard."""
    ensure_dirs()
    if tmux.is_inside_tmux():
        # Launch the dashboard in a tmux popup
        tmux.popup("shoal _popup-inner")
    else:
        _popup_inner_impl()


def _popup_inner_impl() -> None:
    """Inner popup implementation — called by the popup command."""
    from shoal.dashboard.popup import run_popup

    run_popup()


def session_done(
    name: str = typer.Argument(..., help="Session name."),
    summary: str = typer.Option(
        "", "--summary", "-s", help="Completion summary written to journal."
    ),
) -> None:
    """Mark a session as complete."""
    from shoal.services.lifecycle import SessionNotFoundError, complete_session

    try:
        asyncio.run(with_db(complete_session(name, summary)))
    except SessionNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"Session '{name}' marked complete.")
