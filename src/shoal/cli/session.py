"""Session management commands: new, ls, attach, detach, fork, kill, status, popup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import git, tmux
from shoal.core.config import config_dir, ensure_dirs, load_config, load_tool_config
from shoal.core.db import with_db
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
    asyncio.run(with_db(_add_impl(path, tool, worktree, branch, name)))


async def _add_impl(path, tool, worktree, branch, name):
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
    if await find_by_name(session_name):
        console.print(f"[red]Session with name '{session_name}' already exists[/red]")
        raise typer.Exit(1)

    # Create session state
    session = await create_session(session_name, tool, root, work_dir, branch_name)

    # Get tool command
    tool_cfg = load_tool_config(tool)
    tmux_session = session.tmux_session

    # Create tmux session
    try:
        tmux.new_session(tmux_session, cwd=work_dir)
    except Exception:
        console.print("[red]Failed to create tmux session[/red]")
        await delete_session(session.id)
        raise typer.Exit(1) from None

    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

    # Run startup commands
    for cmd in cfg.tmux.startup_commands:
        interpolated = cmd.format(
            tool_command=tool_cfg.command,
            work_dir=work_dir,
            session_name=session_name,
            tmux_session=tmux_session,
        )
        tmux.run_command(interpolated)

    # Update state
    await update_session(session.id, status=SessionStatus.running)

    pane = tmux.pane_pid(tmux_session)
    if pane:
        await update_session(session.id, pid=pane)

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
    asyncio.run(with_db(_ls_impl(format)))


async def _ls_impl(format):
    ensure_dirs()
    sessions = await list_sessions()

    if format == "plain":
        for session in sessions:
            console.print(session.name)
        return

    if not sessions:
        console.print("No sessions")
        return

    # Group sessions by path

    from collections import defaultdict

    groups = defaultdict(list)
    for s in sessions:
        groups[s.path].append(s)

    # Sort paths alphabetically
    sorted_paths = sorted(groups.keys())

    for path in sorted_paths:
        group_sessions = groups[path]
        display_project = path.replace(str(Path.home()), "~")

        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=None,
            padding=(0, 1),
            collapse_padding=True,
        )
        table.add_column("ID", style="dim", width=8)
        table.add_column("NAME", width=25)
        table.add_column("TOOL", width=12)
        table.add_column("STATUS", width=20)
        table.add_column("BRANCH", width=30)
        table.add_column("WORKTREE")

        # Sort sessions within group by name
        for s in sorted(group_sessions, key=lambda x: x.name):
            try:
                icon = load_tool_config(s.tool).icon
            except FileNotFoundError:
                icon = "●"

            # Check if it's a ghost session
            is_ghost = False
            if s.status.value != "stopped" and not tmux.has_session(s.tmux_session):
                is_ghost = True

            status_style = {
                "running": "green",
                "waiting": "bold yellow",
                "error": "bold red",
                "stopped": "dim",
            }.get(s.status.value, "")

            status_text = (
                f"[{status_style}]{s.status.value}[/{status_style}]"
                if status_style
                else s.status.value
            )

            if is_ghost:
                status_text = f"[bold red]󱄽 ghost[/bold red] [dim]({s.status.value})[/dim]"

            wt_display = ""
            if s.worktree:
                wt_display = s.worktree.replace(path, ".").replace(str(Path.home()), "~")
            else:
                wt_display = "[dim](root)[/dim]"

            table.add_row(
                s.id,
                f"{icon} [bold]{s.name}[/bold]",
                s.tool,
                status_text,
                f"[cyan]{s.branch or '-'}[/cyan]",
                wt_display,
            )

        from rich.panel import Panel

        console.print(
            Panel(
                table,
                title=f"[bold blue]󰚝 {Path(path).name}[/bold blue] [dim]({display_project})[/dim]",
                title_align="left",
                border_style="blue",
                padding=(0, 1),
            )
        )


def attach(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    asyncio.run(with_db(_attach_impl(session)))


async def _attach_impl(session_name_or_id):
    ensure_dirs()
    sid = resolve_session_interactive(session_name_or_id)
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
    asyncio.run(with_db(_fork_impl(session, name, no_worktree)))


async def _fork_impl(session, name, no_worktree):
    ensure_dirs()
    cfg = load_config()
    source_id = resolve_session_interactive(session)
    source = await get_session(source_id)
    if not source:
        raise typer.Exit(1)

    new_name = name or f"{source.name}-fork"

    if await find_by_name(new_name):
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
    new_session = await create_session(new_name, source.tool, source.path, wt_path, new_branch)

    tmux_session = new_session.tmux_session

    tmux.new_session(tmux_session, cwd=work_dir)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", new_session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", new_name)

    # Run startup commands
    for cmd in cfg.tmux.startup_commands:
        interpolated = cmd.format(
            tool_command=tool_cfg.command,
            work_dir=work_dir,
            session_name=new_name,
            tmux_session=tmux_session,
        )
        tmux.run_command(interpolated)

    await update_session(new_session.id, status=SessionStatus.running)

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
    asyncio.run(with_db(_kill_impl(session, worktree)))


async def _kill_impl(session, worktree):
    ensure_dirs()
    sid = resolve_session_interactive(session)
    s = await get_session(sid)
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

    await delete_session(sid)
    console.print(f"Session '{s.name}' ({sid}) removed")


def prune(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Do not ask for confirmation")
    ] = False,
) -> None:
    """Remove all sessions marked as stopped."""
    asyncio.run(with_db(_prune_impl(force)))


async def _prune_impl(force):
    ensure_dirs()
    sessions = await list_sessions()
    stopped = [s for s in sessions if s.status.value == "stopped"]

    if not stopped:
        console.print("No stopped sessions to prune")
        return

    if not force:
        console.print(f"Found {len(stopped)} stopped sessions:")
        for s in stopped:
            console.print(f"  - {s.name} ({s.id})")
        if not typer.confirm("Are you sure you want to remove these?"):
            raise typer.Abort()

    for s in stopped:
        await delete_session(s.id)
        console.print(f"Removed session '{s.name}' ({s.id})")


def status() -> None:
    """Quick status summary."""
    asyncio.run(with_db(_status_impl()))


async def _status_impl():
    ensure_dirs()
    sessions = await list_sessions()
    if not sessions:
        console.print("[yellow]No active sessions[/yellow]")
        console.print("Create one with: [bold]shoal new[/bold]")
        return

    counts: dict[str, int] = {"running": 0, "waiting": 0, "error": 0, "idle": 0, "stopped": 0}
    for s in sessions:
        counts[s.status.value] = counts.get(s.status.value, 0) + 1

    total = len(sessions)
    from rich.panel import Panel
    from rich.text import Text

    status_line = Text()
    status_line.append(f"Total Sessions: {total}", style="bold")

    parts = []
    if counts["running"]:
        parts.append(f"[green]● {counts['running']} running[/green]")
    if counts["waiting"]:
        parts.append(f"[yellow]◉ {counts['waiting']} waiting[/yellow]")
    if counts["error"]:
        parts.append(f"[red]✗ {counts['error']} error[/red]")
    if counts["idle"]:
        parts.append(f"○ {counts['idle']} idle")
    if counts["stopped"]:
        parts.append(f"[dim]◌ {counts['stopped']} stopped[/dim]")

    console.print(Panel(Text.from_markup("  |  ".join(parts)), title="Shoal Status", expand=False))

    # Sessions needing attention
    if counts["waiting"]:
        console.print("\n[bold yellow]󰀦 Waiting for input:[/bold yellow]")
        for s in sessions:
            if s.status.value == "waiting":
                try:
                    icon = load_tool_config(s.tool).icon
                except FileNotFoundError:
                    icon = "●"
                console.print(f"  {icon} [bold]{s.name}[/bold] [dim]→ shoal attach {s.name}[/dim]")

    if counts["error"]:
        console.print("\n[bold red]󰅚 Errors detected:[/bold red]")
        for s in sessions:
            if s.status.value == "error":
                try:
                    icon = load_tool_config(s.tool).icon
                except FileNotFoundError:
                    icon = "●"
                console.print(f"  {icon} [bold]{s.name}[/bold] [dim]→ shoal attach {s.name}[/dim]")

    console.print("\n[dim]Use 'shoal ls' for a full list or 'shoal info <name>' for details.[/dim]")


def popup() -> None:
    """Open tmux popup dashboard."""
    ensure_dirs()
    if tmux.is_inside_tmux():
        # Launch the dashboard in a tmux popup
        tmux.popup("shoal _popup-inner")
    else:
        _popup_inner_impl()


def info(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Show detailed information about a session."""
    asyncio.run(with_db(_info_impl(session)))


def rename(
    old_name: Annotated[str, typer.Argument(help="Current session name or ID")],
    new_name: Annotated[str, typer.Argument(help="New name for the session")],
) -> None:
    """Rename a session."""
    asyncio.run(with_db(_rename_impl(old_name, new_name)))


def logs(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 20,
    tail: Annotated[bool, typer.Option("--tail", "-f", help="Follow the logs")] = False,
) -> None:
    """Show recent output from a session."""
    asyncio.run(with_db(_logs_impl(session, lines, tail)))


async def _logs_impl(session_name_or_id, lines, tail):
    ensure_dirs()
    from shoal.core.state import resolve_session

    sid = await resolve_session(session_name_or_id) if session_name_or_id else None
    if not sid:
        from shoal.core.state import _resolve_session_interactive_impl

        sid = await _resolve_session_interactive_impl(session_name_or_id)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not tmux.has_session(s.tmux_session):
        console.print(f"[red]Tmux session '{s.tmux_session}' not found[/red]")
        raise typer.Exit(1)

    if not tail:
        content = tmux.capture_pane(s.tmux_session, lines=lines)
        console.print(content)
    else:
        # Tailing tmux pane output is tricky without a dedicated tool,
        # but we can do a simple loop or use 'tmux pipe-pane'.
        # For simplicity, let's just use a loop for now.
        import time

        last_content = ""
        try:
            while True:
                content = tmux.capture_pane(s.tmux_session, lines=lines)
                if content != last_content:
                    # Clear screen and show new content, or just show diff
                    # Simplest: just print it if it changed
                    if last_content:
                        new_lines = content.splitlines()
                        old_lines = last_content.splitlines()
                        # This is a very naive tail
                        for line in new_lines[len(old_lines) - 1 :]:
                            if line not in old_lines:
                                console.print(line)
                    else:
                        console.print(content)
                    last_content = content
                time.sleep(1)
        except KeyboardInterrupt:
            pass


async def _rename_impl(old_name, new_name):
    ensure_dirs()
    from shoal.core.state import resolve_session, _sanitize_tmux_name

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
    new_tmux = f"shoal_{_sanitize_tmux_name(new_name)}"

    # Rename tmux session if it exists
    if tmux.has_session(old_tmux):
        tmux.rename_session(old_tmux, new_tmux)
        console.print(f"Renamed tmux session: {old_tmux} → {new_tmux}")

    # Update DB
    await update_session(sid, name=new_name, tmux_session=new_tmux)
    console.print(f"Renamed session: {s.name} → {new_name}")


async def _info_impl(session_name_or_id):
    ensure_dirs()
    from shoal.core.state import resolve_session

    sid = await resolve_session(session_name_or_id) if session_name_or_id else None

    if not sid:
        # Fallback to interactive if no arg or not found
        from shoal.core.state import _resolve_session_interactive_impl

        sid = await _resolve_session_interactive_impl(session_name_or_id)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    try:
        tool_cfg = load_tool_config(s.tool)
        icon = tool_cfg.icon
    except FileNotFoundError:
        icon = "●"
        tool_cfg = None

    from rich.panel import Panel
    from rich.columns import Columns

    status_style = {
        "running": "green",
        "waiting": "yellow",
        "error": "red",
        "stopped": "bright_black",
    }.get(s.status.value, "")

    status_text = (
        f"[{status_style}]{s.status.value}[/{status_style}]" if status_style else s.status.value
    )

    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold cyan")
    details.add_column()

    details.add_row("󰚝 ID", s.id)
    details.add_row(f"{icon} Name", f"[bold]{s.name}[/bold]")
    details.add_row("󰏗 Tool", s.tool)
    details.add_row("󰀦 Status", status_text)
    details.add_row("󰃭 Created", s.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    details.add_row("󰥔 Activity", s.last_activity.strftime("%Y-%m-%d %H:%M:%S"))

    paths = Table.grid(padding=(0, 2))
    paths.add_column(style="bold green")
    paths.add_column()
    paths.add_row("󱂵 Git Root", s.path)
    paths.add_row("󱉭 Worktree", s.worktree or "[dim](none)[/dim]")
    paths.add_row("󰘬 Branch", f"[magenta]{s.branch or '-'}[/magenta]")

    runtime = Table.grid(padding=(0, 2))
    runtime.add_column(style="bold yellow")
    runtime.add_column()
    runtime.add_row("󰒋 Tmux", f"[dim]session:[/dim] {s.tmux_session}")
    runtime.add_row(" ", f"[dim]window:[/dim] {s.tmux_window}")
    runtime.add_row("󰆍 PID", str(s.pid) if s.pid else "[dim]N/A[/dim]")
    runtime.add_row("󰒔 MCP", ", ".join(s.mcp_servers) if s.mcp_servers else "[dim](none)[/dim]")

    console.print(
        Panel(
            Columns([details, paths, runtime], expand=True),
            title=f"[bold blue]󰚝 Session: {s.name}[/bold blue]",
            title_align="left",
            border_style="dim",
            padding=(1, 2),
        )
    )

    if tmux.has_session(s.tmux_session):
        console.print("\n[bold]󰆍 Recent Output:[/bold]")
        content = tmux.capture_pane(s.tmux_session)
        if content:
            from rich.syntax import Syntax

            # Show last 10 lines
            lines = content.splitlines()[-10:]
            preview = "\n".join(lines)
            console.print(Panel(preview, border_style="dim", padding=(0, 1)))
        else:
            console.print("  [dim](no output captured)[/dim]")


def _popup_inner_impl() -> None:
    """Inner popup implementation — called by the popup command."""
    from shoal.dashboard.popup import run_popup

    run_popup()
