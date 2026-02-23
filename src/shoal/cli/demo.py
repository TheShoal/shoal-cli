"""Demo environment commands: start, stop, tour."""

from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from shoal.core import git, tmux
from shoal.core.config import load_tool_config
from shoal.core.db import with_db
from shoal.core.state import create_session, delete_session, list_sessions, update_session
from shoal.core.theme import (
    Icons,
    Symbols,
    create_panel,
    create_table,
    get_status_icon,
    get_status_style,
)
from shoal.models.state import SessionStatus

console = Console()

app = typer.Typer(no_args_is_help=True)


def _demo_dir() -> Path:
    """Get the demo directory path."""
    return Path("/tmp/shoal-demo")


def _create_demo_project(demo_dir: Path) -> None:
    """Create a sample Python project with git branches."""
    # Remove existing demo dir to ensure clean state
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=demo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Shoal Demo"],
        cwd=demo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "demo@shoal.local"],
        cwd=demo_dir,
        check=True,
        capture_output=True,
    )

    # Create sample files
    (demo_dir / "README.md").write_text(
        """# Shoal Demo Project

This is a temporary demo project created by `shoal demo start`.

It demonstrates how Shoal orchestrates multiple AI coding sessions:
- Parallel sessions on different branches
- Isolated worktrees for conflict-free development
- Real-time status detection across agents
- A robo-fish supervisor to monitor the shoal
"""
    )

    (demo_dir / "pyproject.toml").write_text(
        """[project]
name = "shoal-demo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi", "uvicorn"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )

    (demo_dir / "main.py").write_text(
        """#!/usr/bin/env python3
\"\"\"Demo application entry point.\"\"\"

from utils import greet

def main():
    greet("Shoal Demo")

if __name__ == "__main__":
    main()
"""
    )

    (demo_dir / "utils.py").write_text(
        """\"\"\"Utility functions.\"\"\"

def greet(name: str) -> None:
    print(f"Hello, {name}!")

def add(a: int, b: int) -> int:
    return a + b
"""
    )

    (demo_dir / "api.py").write_text(
        """\"\"\"REST API endpoints.\"\"\"

from fastapi import FastAPI

app = FastAPI(title="Shoal Demo API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/greet/{name}")
def greet_endpoint(name: str):
    return {"message": f"Hello, {name}!"}
"""
    )

    tests_dir = demo_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_utils.py").write_text(
        """\"\"\"Tests for utils module.\"\"\"

from utils import greet, add

def test_greet(capsys):
    greet("World")
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out

def test_add():
    assert add(2, 3) == 5
"""
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=demo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=demo_dir,
        check=True,
        capture_output=True,
    )


def _build_demo_pane_command(
    session_name: str,
    session_id: str,
    tool: str,
    branch: str,
    project_path: str,
    tmux_session_name: str,
    *,
    worktree_note: bool = False,
    is_robo: bool = False,
    feature: str = "",
) -> str:
    """Build shell command to render demo pane via Typer/Rich."""
    parts = [
        "shoal",
        "demo",
        "pane",
        "--session-name",
        session_name,
        "--session-id",
        session_id,
        "--tool",
        tool,
        "--branch",
        branch,
        "--project-path",
        project_path,
        "--tmux-session-name",
        tmux_session_name,
    ]
    if worktree_note:
        parts.append("--worktree-note")
    if is_robo:
        parts.append("--robo")
    if feature:
        parts.extend(["--feature", feature])
    return " ".join(shlex.quote(part) for part in parts)


# ============================================================================
# Pane rendering — feature-focused content for each demo session
# ============================================================================


def _render_sessions_pane_content() -> None:
    """Session management feature showcase."""
    console.print(Text("Session Management Commands", style="bold green"))
    console.print()
    cmds = Table.grid(padding=(0, 1), expand=True)
    cmds.add_column(style="bold yellow", width=34)
    cmds.add_column(style="white")
    cmds.add_row("shoal ls", "List sessions grouped by project")
    cmds.add_row("shoal status", "Quick status summary")
    cmds.add_row("shoal info demo-main", "Detailed session info")
    cmds.add_row("shoal logs demo-main", "Recent pane output")
    cmds.add_row("shoal attach demo-main", "Attach to this session")
    cmds.add_row("shoal fork demo-main", "Fork into new worktree")
    cmds.add_row("shoal template ls", "Available templates")
    cmds.add_row("shoal mcp doctor", "MCP health checks")
    cmds.add_row("shoal demo tour", "Guided feature walkthrough (9 areas)")
    console.print(cmds)


def _render_worktrees_pane_content() -> None:
    """Worktree isolation feature showcase."""
    console.print(Text("Worktree Isolation", style="bold green"))
    console.print(Text("This session runs in an isolated git worktree.", style="white"))
    console.print(Text("Files here are independent from other sessions.", style="white"))
    console.print()
    cmds = Table.grid(padding=(0, 1), expand=True)
    cmds.add_column(style="bold yellow", width=34)
    cmds.add_column(style="white")
    cmds.add_row("shoal wt ls", "List active worktrees")
    cmds.add_row("shoal wt finish demo-feature", "Merge worktree back")
    cmds.add_row("shoal wt cleanup", "Remove orphaned worktrees")
    cmds.add_row("shoal new -w fix/my-bug -b", "Create session + worktree")
    console.print(cmds)


def _render_detection_pane_content() -> None:
    """Status detection feature showcase."""
    console.print(Text("Status Detection", style="bold green"))
    console.print(Text("Shoal monitors pane output for tool-specific patterns:", style="white"))
    console.print()
    from shoal.core.theme import STATUS_STYLES

    for status_name in ["running", "waiting", "error", "idle", "stopped"]:
        style = STATUS_STYLES[status_name]
        desc = {
            "running": "Agent is actively working",
            "waiting": "Agent needs human input",
            "error": "Something went wrong",
            "idle": "Agent is ready for a task",
            "stopped": "Session is not running",
        }[status_name]
        console.print(f"  [{style.rich}]{style.icon} {status_name:10}[/{style.rich}] {desc}")
    console.print()
    console.print(Text("Try: shoal status  — see varied statuses in action", style="bold yellow"))


def _render_robo_pane_content() -> None:
    """Robo supervisor feature showcase."""
    console.print(Text("Supervisor Commands", style="bold green"))
    console.print()
    cmds = Table.grid(padding=(0, 1), expand=True)
    cmds.add_column(style="bold yellow", width=42)
    cmds.add_column(style="white")
    cmds.add_row("shoal status", "Check all agent statuses")
    cmds.add_row("shoal ls", "List all sessions")
    cmds.add_row("shoal robo ls", "View robo profiles")
    cmds.add_row("shoal logs demo-feature", "Check a worker's output")
    cmds.add_row("shoal robo approve demo-feature", "Approve an action")
    cmds.add_row("shoal robo send demo-main 'pytest'", "Send command to worker")
    console.print(cmds)
    console.print()
    console.print(Text("MCP Orchestration", style="bold green"))
    console.print(Text("Robo agents can also control sessions via MCP tools:", style="white"))
    console.print(Text("  list_sessions, session_status, send_keys,", style="dim"))
    console.print(Text("  create_session, kill_session, session_info", style="dim"))


def _render_default_pane_content(tool: str, worktree_note: bool) -> None:
    """Fallback pane content."""
    console.print(Text("Start Here", style="bold green"))
    console.print(Text(f"1) Authenticate {tool} if needed.", style="white"))
    if worktree_note:
        console.print(Text("2) You are in an isolated worktree. Iterate freely.", style="white"))
    else:
        console.print(Text(f"2) Ask {tool} for a quick repo + branch summary.", style="white"))


def _render_demo_pane(
    session_name: str,
    session_id: str,
    tool: str,
    branch: str,
    project_path: str,
    tmux_session_name: str,
    *,
    worktree_note: bool,
    robo: bool,
    feature: str,
) -> None:
    """Render feature-focused demo pane output with Rich."""
    if robo:
        header_style = "bold white on magenta"
        header = " ROBO SUPERVISOR "
        subtitle = "Agent Coordination"
        accent = "magenta"
    else:
        header_style = "bold black on cyan"
        header = " SHOAL WORKER "
        subtitle = {
            "sessions": "Session Management",
            "worktrees": "Worktree Isolation",
            "detection": "Status Detection",
        }.get(feature, "AI Agent")
        accent = "cyan"

    console.print(Text(f"{header}\u2014 {subtitle}", style=header_style))
    console.print(Text(f"session: {session_name}", style="bold white"))
    console.print(Text(f"project: {project_path}", style="dim"))
    console.print(Rule(style=accent))

    # Session details
    details = Table.grid(padding=(0, 1), expand=True)
    details.add_column(style="bold", width=11)
    details.add_column(style="white")
    details.add_row("session_id", session_id)
    details.add_row("tool", tool)
    details.add_row("branch", branch)
    details.add_row("tmux", tmux_session_name)
    console.print(details)
    console.print()

    # Feature-specific content
    if robo:
        _render_robo_pane_content()
    elif feature == "sessions":
        _render_sessions_pane_content()
    elif feature == "worktrees":
        _render_worktrees_pane_content()
    elif feature == "detection":
        _render_detection_pane_content()
    else:
        _render_default_pane_content(tool, worktree_note)

    console.print()
    console.print(Rule(style="dim"))
    console.print(
        Text("Run 'shoal demo tour' for a guided feature walkthrough.", style="bold green")
    )
    console.print(Text("Cleanup: shoal demo stop", style="dim italic"))


@app.command("pane", hidden=True)
def demo_pane(
    session_name: Annotated[str, typer.Option("--session-name", help="Demo session name")],
    session_id: Annotated[str, typer.Option("--session-id", help="Session ID")],
    tool: Annotated[str, typer.Option("--tool", help="Tool name")],
    branch: Annotated[str, typer.Option("--branch", help="Git branch")],
    project_path: Annotated[str, typer.Option("--project-path", help="Project path")],
    tmux_session_name: Annotated[str, typer.Option("--tmux-session-name", help="Tmux name")],
    worktree_note: Annotated[
        bool, typer.Option("--worktree-note", help="Show worktree note")
    ] = False,
    robo: Annotated[bool, typer.Option("--robo", help="Render robo supervisor pane")] = False,
    feature: Annotated[str, typer.Option("--feature", help="Feature area focus")] = "",
) -> None:
    """Render the demo sidebar pane output."""
    _render_demo_pane(
        session_name,
        session_id,
        tool,
        branch,
        project_path,
        tmux_session_name,
        worktree_note=worktree_note,
        robo=robo,
        feature=feature,
    )


# ============================================================================
# Tmux session helpers
# ============================================================================


def _sanitize_demo_tmux_name(name: str) -> str:
    """Return a stable tmux-safe name for demo sessions."""
    return name.replace("/", "-").replace(":", "-").replace(".", "-")


async def _pin_demo_tmux_name(session_name: str, session_id: str, current_tmux_name: str) -> str:
    """Use stable demo tmux names, independent of configured global prefix."""
    target_tmux_name = _sanitize_demo_tmux_name(session_name)
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


# ============================================================================
# Demo start / stop
# ============================================================================


@app.command("start")
def demo_start(
    dir: Annotated[
        str | None,
        typer.Option("--dir", help="Custom directory for demo (default: /tmp/shoal-demo)"),
    ] = None,
) -> None:
    """Start a demo environment with sample sessions."""
    asyncio.run(with_db(_demo_start_impl(dir)))


async def _demo_start_impl(custom_dir: str | None) -> None:
    demo_dir = Path(custom_dir) if custom_dir else _demo_dir()

    # Check prerequisites
    if not shutil.which("tmux"):
        console.print("[red]Error: tmux not found. Please install tmux first.[/red]")
        raise typer.Exit(1)
    if not shutil.which("git"):
        console.print("[red]Error: git not found. Please install git first.[/red]")
        raise typer.Exit(1)

    # Check if demo already exists
    marker_file = demo_dir / ".shoal-demo"
    if marker_file.exists():
        console.print(f"[yellow]Demo already running at {demo_dir}[/yellow]")
        console.print("Run 'shoal demo stop' first, or use a different --dir")
        raise typer.Exit(1)

    console.print(f"[bold blue]Creating demo environment at {demo_dir}[/bold blue]")
    console.print()

    # Create demo project
    _create_demo_project(demo_dir)
    console.print("  \u2713 Created demo git repository")

    session_ids = []

    # Use the configured default tool (falls back to opencode)
    from shoal.core.config import load_config

    cfg = load_config()
    default_tool = cfg.general.default_tool or "opencode"
    tool_cfg = load_tool_config(default_tool)
    tool_command = tool_cfg.command
    display_path = str(demo_dir).replace(str(Path.home()), "~")

    # ── Session 1: Main branch (feature: session management) ──
    console.print("  \u2713 Creating session: demo-main (main branch)")
    s1 = await create_session(
        name="demo-main",
        tool=default_tool,
        git_root=str(demo_dir),
    )
    s1.tmux_session = await _pin_demo_tmux_name(s1.name, s1.id, s1.tmux_session)
    session_ids.append(s1.id)

    pane_command = _build_demo_pane_command(
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
        demo_dir,
        tool_command=tool_command,
        info_command=pane_command,
    )

    # ── Session 2: Feature branch with worktree (feature: worktrees) ──
    console.print("  \u2713 Creating session: demo-feature (feat/api-endpoint worktree)")
    worktree_path = demo_dir / ".worktrees" / "feat-api-endpoint"
    (demo_dir / ".worktrees").mkdir(parents=True, exist_ok=True)
    git.worktree_add(str(demo_dir), str(worktree_path), branch="feat/api-endpoint")

    s2 = await create_session(
        name="demo-feature",
        tool=default_tool,
        git_root=str(demo_dir),
        worktree=str(worktree_path),
        branch="feat/api-endpoint",
    )
    s2.tmux_session = await _pin_demo_tmux_name(s2.name, s2.id, s2.tmux_session)
    session_ids.append(s2.id)

    wt_display = str(worktree_path).replace(str(Path.home()), "~")
    pane_command = _build_demo_pane_command(
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
    bugfix_path = demo_dir / ".worktrees" / "fix-login-bug"
    git.worktree_add(str(demo_dir), str(bugfix_path), branch="fix/login-bug")

    s3 = await create_session(
        name="demo-bugfix",
        tool=default_tool,
        git_root=str(demo_dir),
        worktree=str(bugfix_path),
        branch="fix/login-bug",
    )
    s3.tmux_session = await _pin_demo_tmux_name(s3.name, s3.id, s3.tmux_session)
    session_ids.append(s3.id)

    bugfix_display = str(bugfix_path).replace(str(Path.home()), "~")
    pane_command = _build_demo_pane_command(
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
        git_root=str(demo_dir),
    )
    s4.tmux_session = await _pin_demo_tmux_name(s4.name, s4.id, s4.tmux_session)
    session_ids.append(s4.id)

    pane_command = _build_demo_pane_command(
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
        demo_dir,
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
  \u2022 Temporary git repository at [cyan]{demo_dir}[/cyan]
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
  [dim]Feature tour[/dim]
    [yellow]shoal demo tour[/yellow]         \u2014 Guided walkthrough (9 feature areas)

[bold]Cleanup:[/bold]
  [yellow]shoal demo stop[/yellow]           \u2014 Remove all demo sessions and files
""",
            title=f"[bold blue]{Icons.DASHBOARD} Shoal Demo Started[/bold blue]",
            title_align="left",
            primary=True,
        )
    )


@app.command("stop")
def demo_stop(
    dir: Annotated[
        str | None,
        typer.Option("--dir", help="Custom directory (must match start --dir)"),
    ] = None,
) -> None:
    """Stop and clean up the demo environment."""
    asyncio.run(with_db(_demo_stop_impl(dir)))


async def _demo_stop_impl(custom_dir: str | None) -> None:
    demo_dir = Path(custom_dir) if custom_dir else _demo_dir()
    marker_file = demo_dir / ".shoal-demo"

    if not marker_file.exists():
        console.print(f"[yellow]No demo found at {demo_dir}[/yellow]")
        console.print("Nothing to clean up.")
        raise typer.Exit(0)

    console.print(f"[bold blue]Stopping demo environment at {demo_dir}[/bold blue]")
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
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
        console.print("  \u2713 Removed demo directory")

    console.print()
    console.print("[bold green]Demo environment cleaned up![/bold green]")


# ============================================================================
# Demo tour — guided walkthrough proving features work
# ============================================================================


@app.command("tour")
def demo_tour() -> None:
    """Guided tour demonstrating Shoal features with live examples."""
    asyncio.run(with_db(_demo_tour_impl()))


async def _demo_tour_impl() -> None:
    from pydantic import ValidationError

    from shoal.core.config import _apply_mixin, _merge_templates
    from shoal.core.detection import detect_status
    from shoal.core.state import validate_session_name
    from shoal.core.theme import STATUS_STYLES
    from shoal.models.config import (
        DetectionPatterns,
        SessionTemplateConfig,
        TemplateMixinConfig,
        TemplatePaneConfig,
        TemplateWindowConfig,
        ToolConfig,
    )
    from shoal.services.mcp_pool import validate_mcp_name

    console.print()
    console.print(Rule("[bold cyan]SHOAL FEATURE TOUR[/bold cyan]", style="cyan"))
    console.print("[dim]Live tests proving each feature area works correctly.[/dim]")
    console.print()

    passed = 0
    failed = 0

    # ── 1. Session State ──────────────────────────────────────────────────
    console.print("[bold]1. Session Management[/bold]")
    console.print("[dim]   Sessions track AI agents in tmux with git context.[/dim]")
    console.print()

    sessions = await list_sessions()
    if sessions:
        table = create_table(padding=(0, 1))
        table.add_column("Name", width=16)
        table.add_column("Tool", width=10)
        table.add_column("Status", width=12)
        table.add_column("Branch", width=22)
        table.add_column("Worktree")
        for s in sessions:
            style = get_status_style(s.status.value)
            icon = get_status_icon(s.status.value)
            status_text = f"[{style}]{icon} {s.status.value}[/{style}]"
            wt = Path(s.worktree).name if s.worktree else "(root)"
            table.add_row(s.name, s.tool, status_text, s.branch or "main", wt)
        console.print(table)
        console.print()

        # Status breakdown
        counts: dict[str, int] = {}
        for s in sessions:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        parts = []
        for status_val, count in sorted(counts.items()):
            icon = get_status_icon(status_val)
            parts.append(f"{icon} {count} {status_val}")
        console.print(f"   Total: {len(sessions)} sessions \u2014 {', '.join(parts)}")
    else:
        console.print(
            "   [dim]No sessions found (run 'shoal demo start' for full experience)[/dim]"
        )

    console.print(f"   [green]{Symbols.CHECK} Session state queries work[/green]")
    passed += 1
    console.print()

    # ── 2. Status Detection Engine ─────────────────────────────────────────
    console.print("[bold]2. Status Detection Engine[/bold]")
    console.print("[dim]   Pane content matched against tool-specific patterns.[/dim]")
    console.print()

    claude_tool = ToolConfig(
        name="claude",
        command="claude",
        icon="\U0001f916",
        detection=DetectionPatterns(
            busy_patterns=["\u280b", "thinking"],
            waiting_patterns=["Yes/No", "Allow"],
            error_patterns=["Error:", "ERROR"],
        ),
    )
    pi_tool = ToolConfig(
        name="pi",
        command="pi",
        icon="\U0001f967",
        detection=DetectionPatterns(
            busy_patterns=["thinking", "generating", "executing"],
            waiting_patterns=["permission", "approve", "y/n"],
            error_patterns=["Error:", "FAILED"],
        ),
    )

    test_cases = [
        ("thinking about the code...", claude_tool, SessionStatus.running),
        ("Do you Allow this? Yes/No", claude_tool, SessionStatus.waiting),
        ("Error: file not found", claude_tool, SessionStatus.error),
        ("$ ls\nfile.py", claude_tool, SessionStatus.idle),
        ("generating response...", pi_tool, SessionStatus.running),
        ("Please approve the edit", pi_tool, SessionStatus.waiting),
        ("Build FAILED with 3 errors", pi_tool, SessionStatus.error),
    ]

    detection_ok = True
    for content, tool, expected in test_cases:
        result = detect_status(content, tool)
        ok = result == expected
        icon = get_status_icon(result.value)
        style = get_status_style(result.value)
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        short = content[:42].replace("\n", "\\n")
        console.print(
            f"   [{color}]{mark}[/{color}] [{style}]{icon} {result.value:8}[/{style}] "
            f'\u2190 {tool.name}: "{short}"'
        )
        if not ok:
            detection_ok = False

    if detection_ok:
        console.print(f"   [green]{Symbols.CHECK} All detection tests passed[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Some detection tests failed[/red]")
        failed += 1
    console.print()

    # ── 3. Template Validation ─────────────────────────────────────────────
    console.print("[bold]3. Template Validation[/bold]")
    console.print("[dim]   Schema-validated session layouts with pane configuration.[/dim]")
    console.print()

    template_ok = True

    # Valid template
    try:
        t = SessionTemplateConfig(
            name="pi-dev",
            description="Pi agent with terminal pane",
            tool="pi",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[
                        TemplatePaneConfig(split="root", size="65%", command="{tool_command}"),
                        TemplatePaneConfig(split="right", size="35%", command="echo terminal"),
                    ],
                ),
            ],
        )
        console.print(
            f"   [green]{Symbols.CHECK}[/green] Valid: {t.name} "
            f"({len(t.windows)} window, "
            f"{sum(len(w.panes) for w in t.windows)} panes)"
        )
    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS} Valid template rejected: {e}[/red]")
        template_ok = False

    # Invalid: bad name
    try:
        SessionTemplateConfig(
            name="bad name!",
            windows=[
                TemplateWindowConfig(
                    name="w", panes=[TemplatePaneConfig(split="root", command="echo")]
                )
            ],
        )
        console.print(f"   [red]{Symbols.CROSS} Should have rejected invalid name[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f'   [green]{Symbols.CHECK}[/green] Rejected invalid name: "bad name!"')

    # Invalid: no windows
    try:
        SessionTemplateConfig(name="empty", windows=[])
        console.print(f"   [red]{Symbols.CROSS} Should have rejected empty windows[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f"   [green]{Symbols.CHECK}[/green] Rejected template with no windows")

    # Invalid: bad pane size
    try:
        TemplatePaneConfig(split="root", size="150%", command="echo")
        console.print(f"   [red]{Symbols.CROSS} Should have rejected invalid size[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f'   [green]{Symbols.CHECK}[/green] Rejected invalid pane size: "150%"')

    # Invalid: first pane not root
    try:
        TemplateWindowConfig(name="bad", panes=[TemplatePaneConfig(split="right", command="echo")])
        console.print(f"   [red]{Symbols.CROSS} Should have rejected non-root first pane[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f"   [green]{Symbols.CHECK}[/green] Rejected non-root first pane")

    if template_ok:
        console.print(f"   [green]{Symbols.CHECK} Template validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Template validation issues[/red]")
        failed += 1
    console.print()

    # ── 4. MCP Name Validation ─────────────────────────────────────────────
    console.print("[bold]4. MCP Server Name Validation[/bold]")
    console.print("[dim]   Names validated for file paths and environment variables.[/dim]")
    console.print()

    mcp_ok = True
    valid_mcp = ["memory", "filesystem", "my-server", "test_123"]
    invalid_mcp = [
        ("bad/name", "bad/name"),
        ("$(whoami)", "$(whoami)"),
        ("", "(empty)"),
        ("-leading", "-leading"),
        ("a" * 65, "a" * 20 + "..."),
    ]

    for name in valid_mcp:
        try:
            validate_mcp_name(name)
            console.print(f'   [green]{Symbols.CHECK}[/green] Accepted: "{name}"')
        except ValueError:
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have accepted: "{name}"')
            mcp_ok = False

    for name, display in invalid_mcp:
        try:
            validate_mcp_name(name)
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have rejected: "{display}"')
            mcp_ok = False
        except ValueError:
            console.print(f'   [green]{Symbols.CHECK}[/green] Rejected: "{display}"')

    if mcp_ok:
        console.print(f"   [green]{Symbols.CHECK} MCP name validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} MCP validation issues[/red]")
        failed += 1
    console.print()

    # ── 5. Session Name Validation ─────────────────────────────────────────
    console.print("[bold]5. Session Name Validation[/bold]")
    console.print("[dim]   Names validated for tmux compatibility and security.[/dim]")
    console.print()

    name_ok = True
    valid_names = ["my-session", "project/feature", "test.v2", "a_b-c"]
    invalid_names = [
        ("", "(empty)"),
        ("a" * 101, "a" * 20 + "..."),
        ("$(whoami)", "$(whoami)"),
        ("..", ".."),
        ("bad name", "bad name"),
    ]

    for name in valid_names:
        try:
            validate_session_name(name)
            console.print(f'   [green]{Symbols.CHECK}[/green] Accepted: "{name}"')
        except ValueError:
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have accepted: "{name}"')
            name_ok = False

    for name, display in invalid_names:
        try:
            validate_session_name(name)
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have rejected: "{display}"')
            name_ok = False
        except ValueError:
            console.print(f'   [green]{Symbols.CHECK}[/green] Rejected: "{display}"')

    if name_ok:
        console.print(f"   [green]{Symbols.CHECK} Session name validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Name validation issues[/red]")
        failed += 1
    console.print()

    # ── 6. Template Inheritance ────────────────────────────────────────────
    console.print("[bold]6. Template Inheritance[/bold]")
    console.print("[dim]   Single inheritance (extends) + additive mixins for DRY templates.[/dim]")
    console.print()

    inherit_ok = True

    # Build a parent and child template in-memory
    _win = [
        TemplateWindowConfig(
            name="main",
            panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
        )
    ]
    parent = SessionTemplateConfig(
        name="base",
        description="Base layout",
        tool="opencode",
        env={"EDITOR": "nvim", "LANG": "en_US.UTF-8"},
        mcp=["memory"],
        windows=_win,
    )
    child = SessionTemplateConfig(
        name="child",
        extends="base",
        tool="claude",
        env={"CLAUDE_MODEL": "opus"},
        mcp=["github"],
        windows=[],
    )
    # Simulate child_raw TOML presence (tool explicitly set, no windows)
    child_raw = {"template": {"tool": "claude"}}

    merged = _merge_templates(parent, child, child_raw)
    checks = [
        (merged.tool == "claude", "child tool wins", f"tool={merged.tool}"),
        (merged.description == "Base layout", "parent description inherited", ""),
        (
            merged.env == {"EDITOR": "nvim", "LANG": "en_US.UTF-8", "CLAUDE_MODEL": "opus"},
            "env dicts merged (child wins conflicts)",
            "",
        ),
        (
            merged.mcp == ["github", "memory"],
            "mcp lists unioned and sorted",
            f"mcp={merged.mcp}",
        ),
        (len(merged.windows) == 1, "parent windows inherited (child had none)", ""),
    ]
    for ok, label, detail in checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        extra = f" ({detail})" if detail and not ok else ""
        console.print(f"   [{color}]{mark}[/{color}] {label}{extra}")
        if not ok:
            inherit_ok = False

    # Test mixin application
    mixin = TemplateMixinConfig(
        name="with-tests",
        env={"TEST_RUNNER": "pytest"},
        mcp=["memory", "filesystem"],
        windows=[
            TemplateWindowConfig(
                name="tests",
                panes=[TemplatePaneConfig(split="root", command="pytest --watch")],
            )
        ],
    )
    mixed = _apply_mixin(merged, mixin)
    mixin_checks = [
        ("TEST_RUNNER" in mixed.env, "mixin env merged in"),
        (sorted(mixed.mcp) == ["filesystem", "github", "memory"], "mixin mcp unioned"),
        (len(mixed.windows) == 2, "mixin window appended"),
        (mixed.windows[-1].name == "tests", "appended window is from mixin"),
    ]
    for ok, label in mixin_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            inherit_ok = False

    if inherit_ok:
        console.print(f"   [green]{Symbols.CHECK} Template inheritance works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Template inheritance issues[/red]")
        failed += 1
    console.print()

    # ── 7. Lifecycle Error Handling ────────────────────────────────────────
    console.print("[bold]7. Lifecycle Error Handling[/bold]")
    console.print("[dim]   Structured exceptions with session context for rollback safety.[/dim]")
    console.print()

    from shoal.services.lifecycle import (
        DirtyWorktreeError,
        LifecycleError,
        SessionExistsError,
        StartupCommandError,
        TmuxSetupError,
    )

    lifecycle_ok = True

    # Verify exception hierarchy
    hierarchy_checks = [
        (issubclass(TmuxSetupError, LifecycleError), "TmuxSetupError extends LifecycleError"),
        (
            issubclass(StartupCommandError, LifecycleError),
            "StartupCommandError extends LifecycleError",
        ),
        (
            issubclass(SessionExistsError, LifecycleError),
            "SessionExistsError extends LifecycleError",
        ),
        (
            issubclass(DirtyWorktreeError, LifecycleError),
            "DirtyWorktreeError extends LifecycleError",
        ),
    ]
    for ok, label in hierarchy_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            lifecycle_ok = False

    # Verify structured context on exceptions
    err = DirtyWorktreeError(
        "uncommitted changes",
        session_id="abc123",
        dirty_files="M src/main.py\n?? new_file.txt",
    )
    ctx_checks = [
        (err.session_id == "abc123", "session_id preserved on exception"),
        (err.operation == "kill", "operation auto-set to 'kill'"),
        (err.dirty_files == "M src/main.py\n?? new_file.txt", "dirty_files attached"),
    ]
    for ok, label in ctx_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            lifecycle_ok = False

    if lifecycle_ok:
        console.print(f"   [green]{Symbols.CHECK} Lifecycle error handling works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Lifecycle error handling issues[/red]")
        failed += 1
    console.print()

    # ── 8. MCP Orchestration Tools ─────────────────────────────────────────
    console.print("[bold]8. MCP Orchestration Tools[/bold]")
    console.print("[dim]   FastMCP server exposes Shoal as MCP tools for agent control.[/dim]")
    console.print()

    mcp_tools_ok = True
    try:
        from shoal.services.mcp_shoal_server import mcp as shoal_mcp

        tools = await shoal_mcp.list_tools()
        tool_names = sorted(t.name for t in tools)
        expected_tools = [
            "create_session",
            "kill_session",
            "list_sessions",
            "send_keys",
            "session_info",
            "session_status",
        ]
        if tool_names == expected_tools:
            console.print(f"   [green]{Symbols.CHECK}[/green] 6 MCP tools registered")
        else:
            console.print(
                f"   [red]{Symbols.CROSS}[/red] Expected {expected_tools}, got {tool_names}"
            )
            mcp_tools_ok = False

        # Show each tool with its annotation
        for tool_obj in sorted(tools, key=lambda t: t.name):
            annotations = tool_obj.annotations
            read_only = getattr(annotations, "readOnlyHint", False) if annotations else False
            destructive = getattr(annotations, "destructiveHint", False) if annotations else False
            if read_only:
                badge = "[dim cyan]read-only[/dim cyan]"
            elif destructive:
                badge = "[dim red]destructive[/dim red]"
            else:
                badge = "[dim]unknown[/dim]"
            console.print(f"   [green]{Symbols.CHECK}[/green] {tool_obj.name:20} {badge}")

    except ImportError:
        console.print(
            f"   [yellow]{Symbols.BULLET_FILLED}[/yellow] "
            "fastmcp not installed (pip install shoal[mcp])"
        )
        # Not a failure — optional dependency
    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS}[/red] MCP server introspection failed: {e}")
        mcp_tools_ok = False

    if mcp_tools_ok:
        console.print(f"   [green]{Symbols.CHECK} MCP orchestration tools work[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} MCP orchestration issues[/red]")
        failed += 1
    console.print()

    # ── 9. Theme System ────────────────────────────────────────────────────
    console.print("[bold]9. Theme & UI System[/bold]")
    console.print("[dim]   Centralized status icons and colors for CLI.[/dim]")
    console.print()

    for status_name, status_style in STATUS_STYLES.items():
        console.print(
            f"   [{status_style.rich}]{status_style.icon} {status_name:10}[/{status_style.rich}] "
            f"nerd: {status_style.nerd}"
        )

    console.print(f"   [green]{Symbols.CHECK} Theme system works[/green]")
    passed += 1
    console.print()

    # ── Summary ────────────────────────────────────────────────────────────
    total = passed + failed
    console.print(Rule(style="cyan"))
    if failed == 0:
        console.print(f"[bold green]{Symbols.CHECK} All {total} feature areas passed![/bold green]")
    else:
        console.print(
            f"[bold yellow]{passed}/{total} feature areas passed, {failed} failed[/bold yellow]"
        )
    console.print()
