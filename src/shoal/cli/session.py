"""Session management commands: add, ls, attach, detach, fork, kill, status, popup."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import git, tmux
from shoal.core.config import config_dir, ensure_dirs, load_config, load_tool_config
from shoal.core.state import (
    create_session,
    delete_session,
    find_by_name,
    get_session,
    list_sessions,
    resolve_session_interactive,
    touch_session,
    update_session,
)
from shoal.models.state import SessionStatus

console = Console()


def add(
    path: Annotated[str | None, typer.Argument(help="Project directory")] = None,
    tool: Annotated[str | None, typer.Option("-t", "--tool", help="AI tool to use")] = None,
    worktree: Annotated[
        str | None, typer.Option("-w", "--worktree", help="Create a git worktree")
    ] = None,
    branch: Annotated[bool, typer.Option("-b", "--branch", help="Create a new branch")] = False,
    name: Annotated[str | None, typer.Option("-n", "--name", help="Session name")] = None,
) -> None:
    """Create a new session."""
    ensure_dirs()
    cfg = load_config()

    resolved_path = Path(path).resolve() if path else Path.cwd().resolve()

    if not tool:
        tool = cfg.general.default_tool

    # Validate tool config
    tool_config_path = config_dir() / "tools" / f"{tool}.toml"
    if not tool_config_path.exists():
        console.print(f"[red]Unknown tool: {tool} (no config at {tool_config_path})[/red]")
        raise typer.Exit(1)

    # Validate git repo
    if not git.is_git_repo(str(resolved_path)):
        console.print(f"[red]Not a git repository: {resolved_path}[/red]")
        raise typer.Exit(1)

    root = git.git_root(str(resolved_path))
    work_dir = str(resolved_path)
    branch_name = ""

    # Worktree setup
    if worktree:
        wt_dir_name = worktree.replace("/", "-")
        wt_path = str(Path(root) / ".worktrees" / wt_dir_name)

        if Path(wt_path).exists():
            console.print(f"[red]Worktree already exists: {wt_path}[/red]")
            raise typer.Exit(1)

        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)

        if branch:
            branch_name = f"feat/{worktree}"
            git.worktree_add(root, wt_path, branch=branch_name)
        else:
            git.worktree_add(root, wt_path)
            branch_name = git.current_branch(wt_path)

        work_dir = wt_path
    else:
        branch_name = git.current_branch(str(resolved_path))

    # Session name
    session_name = name
    if not session_name:
        project_name = Path(root).name
        if worktree:
            wt_label = worktree.replace("/", "-")
            session_name = f"{project_name}/{wt_label}"
        else:
            session_name = project_name

    # Check name collision
    if find_by_name(session_name):
        console.print(f"[red]Session with name '{session_name}' already exists[/red]")
        raise typer.Exit(1)

    # Create session state
    session = create_session(session_name, tool, root, work_dir, branch_name)

    # Get tool command
    tool_cfg = load_tool_config(tool)
    tmux_session = session.tmux_session

    # Create tmux session
    try:
        tmux.new_session(tmux_session, cwd=work_dir)
    except Exception:
        console.print("[red]Failed to create tmux session[/red]")
        delete_session(session.id)
        raise typer.Exit(1) from None

    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

    # Launch the AI tool
    tmux.send_keys(tmux_session, tool_cfg.command)

    # Update state
    update_session(session.id, status=SessionStatus.running)

    pane = tmux.pane_pid(tmux_session)
    if pane:
        update_session(session.id, pid=pane)

    console.print(
        f"{tool_cfg.icon} Session '{session_name}' created (id: {session.id}, tool: {tool})"
    )
    if worktree:
        console.print(f"  Worktree: {work_dir}")
        console.print(f"  Branch: {branch_name}")
    console.print(f"  Tmux: {tmux_session}")
    console.print()
    console.print(f"Attach with: shoal attach {session_name}")


def ls(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (names only for completions)",
        ),
    ] = None,
) -> None:
    """List all sessions."""
    ensure_dirs()
    sessions = list_sessions()

    if format == "plain":
        for sid in sessions:
            session = get_session(sid)
            if session:
                console.print(session.name)
        return

    if not sessions:
        console.print("No sessions")
        return

    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", width=8)
    table.add_column("NAME", width=20)
    table.add_column("TOOL", width=12)
    table.add_column("STATUS", width=10)
    table.add_column("BRANCH", width=30)
    table.add_column("PATH")

    for sid in sessions:
        session = get_session(sid)
        if not session:
            continue

        try:
            icon = load_tool_config(session.tool).icon
        except FileNotFoundError:
            icon = "●"

        status_style = {
            "running": "green",
            "waiting": "yellow",
            "error": "red",
            "stopped": "bright_black",
        }.get(session.status.value, "")

        status_text = (
            f"[{status_style}]{session.status.value}[/{status_style}]"
            if status_style
            else session.status.value
        )

        display_path = session.worktree or session.path
        display_path = display_path.replace(str(Path.home()), "~")

        table.add_row(
            session.id,
            f"{icon} {session.name}",
            session.tool,
            status_text,
            session.branch or "-",
            display_path,
        )

    console.print(table)


def attach(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    ensure_dirs()
    sid = resolve_session_interactive(session)
    s = get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not tmux.has_session(s.tmux_session):
        console.print(
            f"[red]Tmux session '{s.tmux_session}' not found (session may have died)[/red]"
        )
        update_session(sid, status=SessionStatus.stopped)
        raise typer.Exit(1)

    touch_session(sid)

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
    if not current or not current.startswith("shoal_"):
        console.print(f"[red]Not inside a shoal session (current: {current})[/red]")
        raise typer.Exit(1)

    tmux.detach_client()


def fork(
    session: Annotated[str | None, typer.Argument(help="Session to fork")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="New session name")] = None,
    no_worktree: Annotated[
        bool, typer.Option("--no-worktree", help="Fork without creating a worktree")
    ] = False,
) -> None:
    """Fork a session into a new worktree (or standalone session with --no-worktree)."""
    ensure_dirs()
    source_id = resolve_session_interactive(session)
    source = get_session(source_id)
    if not source:
        raise typer.Exit(1)

    new_name = name or f"{source.name}-fork"

    if find_by_name(new_name):
        console.print(f"[red]Session with name '{new_name}' already exists[/red]")
        raise typer.Exit(1)

    tool_cfg = load_tool_config(source.tool)
    work_dir = source.worktree or source.path
    wt_path = ""
    new_branch = source.branch

    if no_worktree:
        # Fork as a standalone session in the same directory
        pass
    else:
        # Create new worktree
        wt_dir_name = new_name.replace("/", "-")
        wt_path = str(Path(source.path) / ".worktrees" / wt_dir_name)
        new_branch = f"feat/{new_name.replace('/', '-')}"

        Path(source.path, ".worktrees").mkdir(parents=True, exist_ok=True)
        try:
            git.worktree_add(source.path, wt_path, branch=new_branch, start_point=source.branch)
        except Exception:
            console.print("[red]Failed to create worktree for fork[/red]")
            raise typer.Exit(1) from None
        work_dir = wt_path

    # Create new session
    new_session = create_session(new_name, source.tool, source.path, wt_path, new_branch)

    tmux_session = new_session.tmux_session

    tmux.new_session(tmux_session, cwd=work_dir)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", new_session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", new_name)
    tmux.send_keys(tmux_session, tool_cfg.command)

    update_session(new_session.id, status=SessionStatus.running)

    console.print(f"{tool_cfg.icon} Forked '{source.name}' → '{new_name}' (id: {new_session.id})")
    if wt_path:
        console.print(f"  Worktree: {wt_path}")
        console.print(f"  Branch: {new_branch} (from {source.branch})")
    else:
        console.print(f"  Directory: {work_dir}")
    console.print()
    console.print(f"Attach with: shoal attach {new_name}")


def kill(
    session: Annotated[str | None, typer.Argument(help="Session to kill")] = None,
    worktree: Annotated[
        bool, typer.Option("--worktree", help="Also remove the git worktree")
    ] = False,
) -> None:
    """Kill a session."""
    ensure_dirs()
    sid = resolve_session_interactive(session)
    s = get_session(sid)
    if not s:
        raise typer.Exit(1)

    try:
        icon = load_tool_config(s.tool).icon
    except FileNotFoundError:
        icon = "●"

    # Kill tmux session
    if tmux.has_session(s.tmux_session):
        tmux.kill_session(s.tmux_session)
        console.print(f"{icon} Killed tmux session: {s.tmux_session}")

    # Optionally remove worktree
    if worktree and s.worktree and Path(s.worktree).is_dir():
        if git.worktree_remove(s.path, s.worktree, force=True):
            console.print(f"  Removed worktree: {s.worktree}")
        else:
            console.print(f"  [yellow]Warning: Failed to remove worktree: {s.worktree}[/yellow]")

        if s.branch and s.branch not in ("main", "master") and git.branch_delete(s.path, s.branch):
            console.print(f"  Deleted branch: {s.branch}")

    delete_session(sid)
    console.print(f"Session '{s.name}' ({sid}) removed")


def status() -> None:
    """Quick status summary."""
    ensure_dirs()
    sessions = list_sessions()
    if not sessions:
        console.print("No active sessions")
        return

    counts: dict[str, int] = {"running": 0, "waiting": 0, "error": 0, "idle": 0, "stopped": 0}
    for sid in sessions:
        s = get_session(sid)
        if s:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1

    total = len(sessions)
    console.print(f"Shoal Sessions: {total} total")
    console.print()

    if counts["running"]:
        console.print(f"  [green]● Running:  {counts['running']}[/green]")
    if counts["waiting"]:
        console.print(f"  [yellow]◉ Waiting:  {counts['waiting']}[/yellow]")
    if counts["error"]:
        console.print(f"  [red]✗ Error:    {counts['error']}[/red]")
    if counts["idle"]:
        console.print(f"  ○ Idle:     {counts['idle']}")
    if counts["stopped"]:
        console.print(f"  [bright_black]◌ Stopped:  {counts['stopped']}[/bright_black]")

    console.print()

    # Sessions needing attention
    if counts["waiting"]:
        console.print("[yellow]Sessions waiting for input:[/yellow]")
        for sid in sessions:
            s = get_session(sid)
            if s and s.status.value == "waiting":
                try:
                    icon = load_tool_config(s.tool).icon
                except FileNotFoundError:
                    icon = "●"
                console.print(f"  {icon} {s.name} → shoal attach {s.name}")
        console.print()

    if counts["error"]:
        console.print("[red]Sessions with errors:[/red]")
        for sid in sessions:
            s = get_session(sid)
            if s and s.status.value == "error":
                try:
                    icon = load_tool_config(s.tool).icon
                except FileNotFoundError:
                    icon = "●"
                console.print(f"  {icon} {s.name} → shoal attach {s.name}")


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
