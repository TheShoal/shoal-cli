"""Session subcommand group — aliases for shoal session <cmd>."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(
    name="session",
    help="Session management commands.",
    no_args_is_help=True,
)


@app.command("ls", hidden=True)
def ls(
    format: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Output format: default (rich table) or plain"),
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter sessions by tag")] = None,
    tree: Annotated[
        bool, typer.Option("--tree", help="Display fork relationships as a tree")
    ] = False,
) -> None:
    """List all sessions (alias: shoal ls)."""
    from shoal.cli.session_view import ls as _ls

    _ls(format=format, tag=tag, tree=tree)


@app.command("list")
def list_(
    format: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Output format: default (rich table) or plain"),
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter sessions by tag")] = None,
    tree: Annotated[
        bool, typer.Option("--tree", help="Display fork relationships as a tree")
    ] = False,
) -> None:
    """List all sessions."""
    from shoal.cli.session_view import ls as _ls

    _ls(format=format, tag=tag, tree=tree)


@app.command("info")
def info(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """Show detailed information about a session."""
    from shoal.cli.session_view import info as _info

    _info(session=session, color=color)


@app.command("logs")
def logs(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 20,
    tail: Annotated[bool, typer.Option("--tail", "-f", help="Follow the logs")] = False,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """Show recent output from a session."""
    from shoal.cli.session_view import logs as _logs

    _logs(session=session, lines=lines, tail=tail, color=color)


@app.command("status")
def status(
    format: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Output format: default (rich panel) or plain"),
    ] = None,
) -> None:
    """Quick status summary."""
    from shoal.cli.session_view import status as _status

    _status(format=format)


@app.command("attach")
def attach(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    from shoal.cli.session import attach as _attach

    _attach(session)


@app.command("detach")
def detach() -> None:
    """Detach from current session."""
    from shoal.cli.session import detach as _detach

    _detach()


@app.command("kill")
def kill(
    session: Annotated[str | None, typer.Argument(help="Session to kill")] = None,
    worktree: Annotated[
        bool, typer.Option("--worktree", help="Also remove the git worktree")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force kill even with dirty worktree")
    ] = False,
) -> None:
    """Kill a session."""
    from shoal.cli.session_create import kill as _kill

    _kill(session, worktree, force)


@app.command("prune")
def prune(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Do not ask for confirmation")
    ] = False,
) -> None:
    """Remove all sessions marked as stopped."""
    from shoal.cli.session import prune as _prune

    _prune(force)
