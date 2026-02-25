"""Demo start/stop commands."""

from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path
from typing import Annotated

import typer

from shoal.cli.demo import (
    build_demo_pane_command,
    console,
    create_demo_project,
    demo_dir,
    sanitize_demo_tmux_name,
)
from shoal.core import git, tmux
from shoal.core.config import load_tool_config
from shoal.core.db import with_db
from shoal.core.state import create_session, delete_session, update_session
from shoal.core.theme import Icons, create_panel
from shoal.models.state import SessionStatus


async def _pin_demo_tmux_name(session_name: str, session_id: str, current_tmux_name: str) -> str:
    """Use stable demo tmux names, independent of configured global prefix."""
    target_tmux_name = sanitize_demo_tmux_name(session_name)
    if target_tmux_name == current_tmux_name:
        return current_tmux_name
    if tmux.has_session(target_tmux_name):
        console.print(
            "[red]Error: Demo tmux session name already exists:[/red] "
            f"[bold]{target_tmux_name}[/bold]"
        )
        raise typer.Exit(1)
    await update_session(
        session_id,
        tmux_session=target_tmux_name,
        nvim_socket=f"/tmp/nvim-{target_tmux_name}-0.sock",
    )
    return target_tmux_name


def _start_demo_tmux_session(
    tmux_session_name: str,
    cwd: Path,
    *,
    tool_command: str,
    info_command: str,
) -> None:
    """Start a 2-pane demo layout: tool pane + info pane."""
    tmux.new_session(tmux_session_name, cwd=str(cwd))
    quoted_cwd = shlex.quote(str(cwd))
    quoted_session = shlex.quote(tmux_session_name)

    # Use session-level targets so demo works with any tmux base-index settings.
    tmux.send_keys(tmux_session_name, tool_command)
    tmux.run_command(f"split-window -t {quoted_session} -h -c {quoted_cwd}")
    tmux.send_keys(tmux_session_name, info_command)
    tmux.run_command(f"select-pane -t {quoted_session} -L")


def demo_start(
    dir: Annotated[
        str | None,
        typer.Option("--dir", help="Custom directory for demo (default: /tmp/shoal-demo)"),
    ] = None,
) -> None:
    """Start a demo environment with sample sessions."""
    asyncio.run(with_db(_demo_start_impl(dir)))


async def _demo_start_impl(custom_dir: str | None) -> None:
    _demo_dir = Path(custom_dir) if custom_dir else demo_dir()

    # Check prerequisites
    if not shutil.which("tmux"):
        console.print("[red]Error: tmux not found. Please install tmux first.[/red]")
        raise typer.Exit(1)
    if not shutil.which("git"):
        console.print("[red]Error: git not found. Please install git first.[/red]")
        raise typer.Exit(1)

    # Check if demo already exists
    marker_file = _demo_dir / ".shoal-demo"
    if marker_file.exists():
        console.print(f"[yellow]Demo already running at {_demo_dir}[/yellow]")
        console.print("Run 'shoal demo stop' first, or use a different --dir")
        raise typer.Exit(1)

    console.print(f"[bold blue]Creating demo environment at {_demo_dir}[/bold blue]")
    console.print()

    # Create demo project
    create_demo_project(_demo_dir)
    console.print("  \u2713 Created demo git repository")

    session_ids = []

    # Use the configured default tool (falls back to opencode)
    from shoal.core.config import load_config

    cfg = load_config()
    default_tool = cfg.general.default_tool or "pi"
    tool_cfg = load_tool_config(default_tool)
    tool_command = tool_cfg.command
    display_path = str(_demo_dir).replace(str(Path.home()), "~")

    # ── Session 1: Main branch (feature: session management) ──
    console.print("  \u2713 Creating session: demo-main (main branch)")
    s1 = await create_session(
        name="demo-main",
        tool=default_tool,
        git_root=str(_demo_dir),
        branch=git.current_branch(str(_demo_dir)),
    )
    s1.tmux_session = await _pin_demo_tmux_name(s1.name, s1.id, s1.tmux_session)
    session_ids.append(s1.id)

    pane_command = build_demo_pane_command(
        session_name="demo-main",
        session_id=s1.id,
        tool=default_tool,
        branch="main",
        project_path=display_path,
        tmux_session_name=s1.tmux_session,
        feature="sessions",
    )
    _start_demo_tmux_session(
        s1.tmux_session,
        _demo_dir,
        tool_command=tool_command,
        info_command=pane_command,
    )

    # ── Session 2: Feature branch with worktree (feature: worktrees) ──
    console.print("  \u2713 Creating session: demo-feature (feat/api-endpoint worktree)")
    worktree_path = _demo_dir / ".worktrees" / "feat-api-endpoint"
    (_demo_dir / ".worktrees").mkdir(parents=True, exist_ok=True)
    git.worktree_add(str(_demo_dir), str(worktree_path), branch="feat/api-endpoint")

    s2 = await create_session(
        name="demo-feature",
        tool=default_tool,
        git_root=str(_demo_dir),
        worktree=str(worktree_path),
        branch="feat/api-endpoint",
    )
    s2.tmux_session = await _pin_demo_tmux_name(s2.name, s2.id, s2.tmux_session)
    session_ids.append(s2.id)

    wt_display = str(worktree_path).replace(str(Path.home()), "~")
    pane_command = build_demo_pane_command(
        session_name="demo-feature",
        session_id=s2.id,
        tool=default_tool,
        branch="feat/api-endpoint",
        project_path=wt_display,
        tmux_session_name=s2.tmux_session,
        worktree_note=True,
        feature="worktrees",
    )
    _start_demo_tmux_session(
        s2.tmux_session,
        worktree_path,
        tool_command=tool_command,
        info_command=pane_command,
    )

    # ── Session 3: Bugfix branch with worktree (feature: detection) ──
    console.print("  \u2713 Creating session: demo-bugfix (fix/login-bug worktree)")
    bugfix_path = _demo_dir / ".worktrees" / "fix-login-bug"
    git.worktree_add(str(_demo_dir), str(bugfix_path), branch="fix/login-bug")

    s3 = await create_session(
        name="demo-bugfix",
        tool=default_tool,
        git_root=str(_demo_dir),
        worktree=str(bugfix_path),
        branch="fix/login-bug",
    )
    s3.tmux_session = await _pin_demo_tmux_name(s3.name, s3.id, s3.tmux_session)
    session_ids.append(s3.id)

    bugfix_display = str(bugfix_path).replace(str(Path.home()), "~")
    pane_command = build_demo_pane_command(
        session_name="demo-bugfix",
        session_id=s3.id,
        tool=default_tool,
        branch="fix/login-bug",
        project_path=bugfix_display,
        tmux_session_name=s3.tmux_session,
        worktree_note=True,
        feature="detection",
    )
    _start_demo_tmux_session(
        s3.tmux_session,
        bugfix_path,
        tool_command=tool_command,
        info_command=pane_command,
    )

    # ── Session 4: Robo supervisor ──
    console.print("  \u2713 Creating session: demo-robo (supervisor)")
    s4 = await create_session(
        name="demo-robo",
        tool=default_tool,
        git_root=str(_demo_dir),
        branch=git.current_branch(str(_demo_dir)),
    )
    s4.tmux_session = await _pin_demo_tmux_name(s4.name, s4.id, s4.tmux_session)
    session_ids.append(s4.id)

    pane_command = build_demo_pane_command(
        session_name="demo-robo",
        session_id=s4.id,
        tool=default_tool,
        branch="main",
        project_path=display_path,
        tmux_session_name=s4.tmux_session,
        is_robo=True,
    )
    _start_demo_tmux_session(
        s4.tmux_session,
        _demo_dir,
        tool_command=tool_command,
        info_command=pane_command,
    )

    # ── Set varied statuses to demonstrate detection ──
    await update_session(s1.id, status=SessionStatus.running)
    await update_session(s2.id, status=SessionStatus.idle)
    await update_session(s3.id, status=SessionStatus.waiting)
    await update_session(s4.id, status=SessionStatus.running)

    # Write marker file
    marker_file.write_text("\n".join(session_ids))

    console.print()
    console.print(
        create_panel(
            f"""[bold green]Demo environment ready![/bold green]

[bold]What was created:[/bold]
  \u2022 Temporary git repository at [cyan]{_demo_dir}[/cyan]
  \u2022 4 demo sessions with different features highlighted:
    [bold]demo-main[/bold]     [green]\u25cf running[/green]   main branch \u2014 session management
    [bold]demo-feature[/bold]  [white]\u25cb idle[/white]      feat/api-endpoint \u2014 isolation
    [bold]demo-bugfix[/bold]   [yellow]\u25c9 waiting[/yellow]  fix/login-bug \u2014 status
    [bold]demo-robo[/bold]     [green]\u25cf running[/green]   supervisor \u2014 agent coordination

[bold]Try these commands:[/bold]
  [dim]Session management[/dim]
    [yellow]shoal ls[/yellow]                \u2014 Sessions grouped by project
    [yellow]shoal status[/yellow]            \u2014 Status summary (see varied statuses!)
    [yellow]shoal info demo-main[/yellow]    \u2014 Detailed session info
    [yellow]shoal attach demo-main[/yellow]  \u2014 Attach to a session
  [dim]Worktree isolation[/dim]
    [yellow]shoal wt ls[/yellow]             \u2014 Active worktrees
  [dim]Templates & inheritance[/dim]
    [yellow]shoal template ls[/yellow]       \u2014 Available templates (with extends chains)
    [yellow]shoal template mixins[/yellow]   \u2014 Additive mixin fragments
  [dim]MCP orchestration[/dim]
    [yellow]shoal mcp ls[/yellow]            \u2014 Running MCP servers
    [yellow]shoal mcp doctor[/yellow]        \u2014 Health check with protocol probing
  [dim]Supervisor[/dim]
    [yellow]shoal robo ls[/yellow]           \u2014 Robo profiles
  [dim]Dashboard[/dim]
    [yellow]shoal popup[/yellow]             \u2014 Interactive fzf dashboard
  [dim]Guided tours[/dim]
    [yellow]shoal demo tour[/yellow]         \u2014 Feature showcase (7 areas)
    [yellow]shoal demo tutorial[/yellow]     \u2014 Interactive hands-on walkthrough

[bold]Cleanup:[/bold]
  [yellow]shoal demo stop[/yellow]           \u2014 Remove all demo sessions and files
""",
            title=f"[bold blue]{Icons.DASHBOARD} Shoal Demo Started[/bold blue]",
            title_align="left",
            primary=True,
        )
    )


def demo_stop(
    dir: Annotated[
        str | None,
        typer.Option("--dir", help="Custom directory (must match start --dir)"),
    ] = None,
) -> None:
    """Stop and clean up the demo environment."""
    asyncio.run(with_db(_demo_stop_impl(dir)))


async def _demo_stop_impl(custom_dir: str | Path | None) -> None:
    _demo_dir = Path(custom_dir) if custom_dir else demo_dir()
    marker_file = _demo_dir / ".shoal-demo"

    if not marker_file.exists():
        console.print(f"[yellow]No demo found at {_demo_dir}[/yellow]")
        console.print("Nothing to clean up.")
        raise typer.Exit(0)

    console.print(f"[bold blue]Stopping demo environment at {_demo_dir}[/bold blue]")
    console.print()

    # Read session IDs
    session_ids = marker_file.read_text().strip().split("\n")

    # Kill sessions
    for sid in session_ids:
        from shoal.core.state import get_session

        s = await get_session(sid)
        if s:
            if tmux.has_session(s.tmux_session):
                tmux.kill_session(s.tmux_session)
                console.print(f"  \u2713 Killed tmux session: {s.name}")
            await delete_session(sid)
            console.print(f"  \u2713 Deleted session: {s.name}")

    # Remove demo directory
    if _demo_dir.exists():
        shutil.rmtree(_demo_dir)
        console.print("  \u2713 Removed demo directory")

    console.print()
    console.print("[bold green]Demo environment cleaned up![/bold green]")
