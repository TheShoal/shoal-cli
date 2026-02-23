"""Demo environment commands: start, stop, tour, tutorial."""

from __future__ import annotations

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

console = Console()

app = typer.Typer(no_args_is_help=True)


def demo_dir() -> Path:
    """Get the demo directory path."""
    return Path("/tmp/shoal-demo")


def tutorial_dir() -> Path:
    """Get the tutorial directory path."""
    return Path("/tmp/shoal-tutorial")


def create_demo_project(demo_dir: Path) -> None:
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


def sanitize_demo_tmux_name(name: str) -> str:
    """Return a stable tmux-safe name for demo sessions."""
    return name.replace("/", "-").replace(":", "-").replace(".", "-")


def build_demo_pane_command(
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
    cmds.add_row("shoal demo tour", "Guided feature walkthrough")
    cmds.add_row("shoal demo tutorial", "Interactive hands-on tutorial")
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


# Register subcommands
from shoal.cli.demo.start_stop import demo_start, demo_stop  # noqa: E402
from shoal.cli.demo.tour import demo_tour  # noqa: E402

app.command("start")(demo_start)
app.command("stop")(demo_stop)
app.command("tour")(demo_tour)
