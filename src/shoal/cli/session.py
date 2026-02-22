"""Session management commands: attach, detach, rename, prune, popup."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from shoal.core import tmux
from shoal.core.config import ensure_dirs
from shoal.core.db import with_db
from shoal.core.state import (
    _resolve_session_interactive_impl,
    build_tmux_session_name,
    delete_session,
    find_by_name,
    get_session,
    is_shoal_tmux_session_name,
    list_sessions,
    touch_session,
    update_session,
)
from shoal.models.state import SessionStatus

console = Console()


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

    if not tmux.has_session(s.tmux_session):
        console.print(
            f"[red]Tmux session '{s.tmux_session}' not found (session may have died)[/red]"
        )
        await update_session(sid, status=SessionStatus.stopped)
        raise typer.Exit(1)

    await touch_session(sid)

    if tmux.is_inside_tmux():
        tmux.switch_client(s.tmux_session)
    else:
        tmux.attach_session(s.tmux_session)


def detach() -> None:
    """Detach from current session."""
    if not tmux.is_inside_tmux():
        console.print("[red]Not inside a tmux session[/red]")
        raise typer.Exit(1)

    current = tmux.current_session_name()
    if not is_shoal_tmux_session_name(current):
        console.print(f"[red]Not inside a shoal session (current: {current})[/red]")
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
    from shoal.core.state import resolve_session, validate_session_name

    # Validate new name
    try:
        validate_session_name(new_name)
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from e

    sid = await resolve_session(old_name)
    if not sid:
        console.print(f"[red]Session not found: {old_name}[/red]")
        raise typer.Exit(1)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    # Check if new name already exists
    if await find_by_name(new_name):
        console.print(f"[red]Session with name '{new_name}' already exists[/red]")
        raise typer.Exit(1)

    old_tmux = s.tmux_session
    new_tmux = build_tmux_session_name(new_name)

    # Rename tmux session if it exists
    if tmux.has_session(old_tmux):
        tmux.rename_session(old_tmux, new_tmux)
        console.print(f"Renamed tmux session: {old_tmux} → {new_tmux}")

    # Update DB
    await update_session(sid, name=new_name, tmux_session=new_tmux)
    console.print(f"Renamed session: {s.name} → {new_name}")


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
        console.print("No stopped sessions to prune")
        return

    if not force:
        console.print()
        console.print(f"Found {len(stopped)} stopped sessions:")
        for s in stopped:
            console.print(f"  - {s.name} ({s.id})")
        if not typer.confirm("Are you sure you want to remove these?"):
            raise typer.Abort()

    for s in stopped:
        await delete_session(s.id)
        console.print(f"Removed session '{s.name}' ({s.id})")


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
