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


def edit_session(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    name: str | None = typer.Option(None, "--name", help="Rename the session"),
    add_tag: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--add-tag",
        help="Add a tag to the session",
    ),
    remove_tag: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--remove-tag",
        help="Remove a tag from the session",
    ),
    linear: str | None = typer.Option(None, "--linear", help="Attach a Linear issue"),
    clear_linear: bool = typer.Option(False, "--clear-linear", help="Detach Linear issue binding"),
    github: str | None = typer.Option(
        None,
        "--github",
        help="Attach a GitHub PR owner/repo#number",
    ),
    clear_github: bool = typer.Option(False, "--clear-github", help="Detach GitHub PR binding"),
) -> None:
    """Edit mutable session metadata."""
    asyncio.run(
        with_db(
            _edit_session_impl(
                session,
                name=name,
                add_tags=add_tag or [],
                remove_tags=remove_tag or [],
                linear=linear,
                clear_linear=clear_linear,
                github=github,
                clear_github=clear_github,
            )
        )
    )


async def _edit_session_impl(
    session: str,
    *,
    name: str | None,
    add_tags: list[str],
    remove_tags: list[str],
    linear: str | None,
    clear_linear: bool,
    github: str | None,
    clear_github: bool,
) -> None:
    from shoal.cli.github import _pr_attach_impl, _pr_detach_impl
    from shoal.cli.ticket import _ticket_attach_impl, _ticket_detach_impl
    from shoal.core.state import add_tag as add_session_tag
    from shoal.core.state import remove_tag as remove_session_tag
    from shoal.core.state import resolve_session

    console = get_console()
    if linear and clear_linear:
        console.print("[red]Choose either --linear or --clear-linear[/red]")
        raise typer.Exit(1)
    if github and clear_github:
        console.print("[red]Choose either --github or --clear-github[/red]")
        raise typer.Exit(1)

    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    current = await get_session(sid)
    if current is None:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    target_ref = current.name
    if name:
        await _rename_impl(session, name)
        target_ref = name

    for tag in add_tags:
        await add_session_tag(sid, tag)
    for tag in remove_tags:
        await remove_session_tag(sid, tag)

    if linear:
        await _ticket_attach_impl(target_ref, linear)
    elif clear_linear:
        await _ticket_detach_impl(target_ref)

    if github:
        if "#" not in github:
            console.print("[red]GitHub binding must be in owner/repo#number format[/red]")
            raise typer.Exit(1)
        repo, number_text = github.rsplit("#", 1)
        try:
            number = int(number_text)
        except ValueError as exc:
            console.print("[red]GitHub binding must use a numeric PR number[/red]")
            raise typer.Exit(1) from exc
        await _pr_attach_impl(target_ref, repo, number)
    elif clear_github:
        await _pr_detach_impl(target_ref)

    if add_tags or remove_tags or name or linear or clear_linear or github or clear_github:
        console.print(f"Updated session: {target_ref}")
    else:
        console.print("[yellow]No changes requested[/yellow]")


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
