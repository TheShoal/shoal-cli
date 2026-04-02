"""Proactive CLI commands — filesystem watching and event inspection."""

from __future__ import annotations

import asyncio

import typer

from shoal.cli._console import get_console
from shoal.core.db import with_db

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# fs-watch sub-group
# ---------------------------------------------------------------------------

fs_watch_app = typer.Typer(no_args_is_help=True)
app.add_typer(fs_watch_app, name="fs-watch", help="Filesystem watcher control.")


@fs_watch_app.command("start")
def fs_watch_start(
    daemon: bool = typer.Option(
        False,
        "--daemon",
        "-d",
        help="Run in background (foreground by default for visibility).",
    ),
) -> None:
    """Start the filesystem watcher for all active session worktrees.

    Watches each session's worktree for file-save events and emits
    ``file_changed`` lifecycle events that proactive hooks can react to.
    """
    asyncio.run(with_db(_fs_watch_start_impl(daemon=daemon)))


async def _fs_watch_start_impl(*, daemon: bool) -> None:
    from shoal.core.state import list_sessions
    from shoal.services.fs_watcher import init_fs_watcher

    console = get_console()
    sessions = await list_sessions()
    active = [s for s in sessions if s.status.value not in ("stopped", "unknown")]

    watcher = init_fs_watcher()
    await watcher.start()

    registered = 0
    for session in active:
        if session.worktree:
            await watcher.add_path(session.worktree, session.id, session.name)
            registered += 1
        elif session.path:
            await watcher.add_path(session.path, session.id, session.name)
            registered += 1

    console.print(f"[green]FsWatcher started[/green] — watching {registered} path(s).")
    for wp in watcher.watched_paths():
        console.print(f"  [dim]{wp.session_name}[/dim] → {wp.path}")

    if not daemon:
        console.print("[dim]Press Ctrl-C to stop.[/dim]")
        try:
            await asyncio.get_event_loop().create_future()  # run until interrupted
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await watcher.stop()
            console.print("[dim]FsWatcher stopped.[/dim]")


@fs_watch_app.command("status")
def fs_watch_status() -> None:
    """Show currently watched paths."""
    from shoal.services.fs_watcher import get_fs_watcher

    console = get_console()
    fw = get_fs_watcher()
    if fw is None:
        console.print("[yellow]FsWatcher not running in this process.[/yellow]")
        console.print("[dim]Run 'shoal proactive fs-watch start' to start.[/dim]")
        raise typer.Exit(1)

    watched = fw.watched_paths()
    if not watched:
        console.print("[dim]FsWatcher running but no paths registered.[/dim]")
        return

    console.print(f"[green]FsWatcher active[/green] — {len(watched)} path(s):")
    for wp in watched:
        console.print(f"  [cyan]{wp.session_name}[/cyan] ({wp.session_id[:8]}) → {wp.path}")


# ---------------------------------------------------------------------------
# message sub-group
# ---------------------------------------------------------------------------

message_app = typer.Typer(no_args_is_help=True)
app.add_typer(message_app, name="message", help="Agent Bus message commands.")


@message_app.command("send")
def message_send(
    to_session: str = typer.Argument(help="Recipient session name or ID."),
    topic: str = typer.Argument(help="Message topic."),
    payload: str = typer.Argument(help="Message payload (typically JSON)."),
    from_session: str = typer.Option("", "--from", "-f", help="Sender name (default: cli)."),
) -> None:
    """Post a message to another session via the Agent Bus."""

    async def _send() -> None:
        from shoal.core.message_bus import send_message

        msg_id = await send_message(
            from_session=from_session or "cli",
            to_session=to_session,
            topic=topic,
            payload=payload,
        )
        get_console().print(f"[green]Sent[/green] message {msg_id} → {to_session} [{topic}]")

    asyncio.run(with_db(_send()))


@message_app.command("list")
def message_list(
    session: str = typer.Option("", "--session", "-s", help="Recipient session name."),
    topic: str = typer.Option("", "--topic", "-t", help="Filter by topic."),
    all_messages: bool = typer.Option(False, "--all", "-a", help="Include consumed messages."),
) -> None:
    """List messages from the Agent Bus."""

    async def _list() -> None:
        from shoal.core.message_bus import receive_messages
        from shoal.core.state import list_sessions

        console = get_console()

        target = session
        if not target:
            sessions = await list_sessions()
            if len(sessions) == 1:
                target = sessions[0].name
            else:
                console.print("[yellow]Specify --session to filter messages.[/yellow]")
                for s in sessions:
                    target = s.name
                    msgs = await receive_messages(
                        target,
                        topic=topic or None,
                        unconsumed_only=not all_messages,
                    )
                    if msgs:
                        _print_messages(console, target, msgs)
                return

        msgs = await receive_messages(
            target,
            topic=topic or None,
            unconsumed_only=not all_messages,
        )
        _print_messages(console, target, msgs)

    asyncio.run(with_db(_list()))


def _print_messages(
    console: object,
    session: str,
    msgs: list[dict[str, object]],
) -> None:
    from rich.console import Console

    c = console if isinstance(console, Console) else get_console()
    if not msgs:
        c.print(f"[dim]No messages for {session}.[/dim]")
        return
    c.print(f"[bold]Messages for {session}[/bold] ({len(msgs)})")
    for msg in msgs:
        consumed = "[green]✓[/green]" if msg.get("consumed_at") else "[yellow]○[/yellow]"
        c.print(
            f"  {consumed} [dim]#{msg['id']}[/dim]"
            f" [cyan]{msg['from_session']}[/cyan]→{msg['to_session']}"
            f" [{msg['topic']}] {str(msg['payload'])[:60]}"
        )
