"""Demo environment commands: start, stop."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from shoal.core import git, tmux
from shoal.core.db import get_db, with_db
from shoal.core.state import create_session, delete_session, list_sessions

console = Console()

app = typer.Typer(no_args_is_help=True)


def _demo_dir() -> Path:
    """Get the demo directory path."""
    return Path("/tmp/shoal-demo")


def _create_demo_project(demo_dir: Path) -> None:
    """Create a fake Python project with git branches."""
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
- A robo-fish supervisor to monitor the shoal
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
"""
    )

    tests_dir = demo_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_utils.py").write_text(
        """\"\"\"Tests for utils module.\"\"\"

from utils import greet

def test_greet(capsys):
    greet("World")
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out
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

    # Create feature branch
    subprocess.run(
        ["git", "checkout", "-b", "feat/api-endpoint"],
        cwd=demo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=demo_dir,
        check=True,
        capture_output=True,
    )


def _create_session_echo_script(
    session_name: str,
    session_id: str,
    tool: str,
    branch: str,
    project_path: str,
    tmux_session_name: str,
    is_robo: bool = False,
) -> str:
    """Generate an echo script that describes what the session is."""
    if is_robo:
        return f"""clear
echo "╭──────────────────────────────────────────────╮"
echo "│  󰚩 Shoal Demo — Robo Session                │"
echo "├──────────────────────────────────────────────┤"
echo "│                                              │"
echo "│  This is a ROBO-FISH session — Shoal's       │"
echo "│  supervisory agent.                          │"
echo "│                                              │"
echo "│  In nature, robot fish lead schools of real  │"
echo "│  fish. In Shoal, the robo leads your AI      │"
echo "│  coding agents.                              │"
echo "│                                              │"
echo "│  The robo can see these active sessions:     │"
echo "│    • demo-main     (main branch)             │"
echo "│    • demo-feature  (feat/api-endpoint)       │"
echo "│                                              │"
echo "│  A robo-fish can:                            │"
echo "│    • Monitor agent status (shoal status)     │"
echo "│    • Approve waiting agents                  │"
echo "│    • Send commands to any session            │"
echo "│    • Coordinate work across the shoal        │"
echo "│                                              │"
echo "│  In production, this session runs an AI      │"
echo "│  tool with a specialized AGENTS.md prompt    │"
echo "│  that gives it awareness of all sessions.    │"
echo "│                                              │"
echo "╰──────────────────────────────────────────────╯"
echo ""
bash
"""
    else:
        worktree_note = ""
        if "feature" in session_name:
            worktree_note = """echo "│  This session uses a dedicated worktree,     │"
echo "│  which means it has its own working          │"
echo "│  directory separate from the main branch.    │"
echo "│  Changes here won't affect other sessions.   │"
echo "│                                              │" """

        return f"""clear
echo "╭──────────────────────────────────────────────╮"
echo "│  󰚩 Shoal Demo — Session: {session_name:22s}│"
echo "├──────────────────────────────────────────────┤"
echo "│                                              │"
echo "│  This is a Shoal session running on the      │"
echo "│  {branch:42s}│"
{worktree_note}echo "│  In a real workflow, this session would be    │"
echo "│  running an AI coding tool like:             │"
echo "│    • OpenCode (opencode)                     │"
echo "│    • Claude Code (claude)                    │"
echo "│    • Gemini CLI (gemini)                     │"
echo "│                                              │"
echo "│  The tool would have full access to the      │"
echo "│  project files and could make changes,       │"
echo "│  run tests, and commit code.                 │"
echo "│                                              │"
echo "│  You can also run terminal tools here:       │"
echo "│    • lazygit — TUI git client                │"
echo "│    • btop — system monitor                   │"
echo "│    • nvim — editor with LSP                  │"
echo "│                                              │"
echo "│  Session ID:    {session_id:30s}│"
echo "│  Tool:          {tool:30s}│"
echo "│  Branch:        {branch:30s}│"
echo "│  Project:       {project_path:30s}│"
echo "│  Tmux Session:  {tmux_session_name:30s}│"
echo "│                                              │"
echo "╰──────────────────────────────────────────────╯"
echo ""
echo "Type 'exit' or press Ctrl+D to leave this session."
bash
"""


@app.command("start")
def demo_start(
    dir: Annotated[
        str | None,
        typer.Option("--dir", help="Custom directory for demo (default: /tmp/shoal-demo)"),
    ] = None,
) -> None:
    """Start a demo environment with sample sessions."""
    asyncio.run(with_db(_demo_start_impl(dir)))


async def _demo_start_impl(custom_dir: str | None):
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
    console.print(f"  ✓ Created demo git repository")

    # Create marker file to track demo sessions
    session_ids = []

    # Session 1: Main branch
    console.print("  ✓ Creating session: demo-main (main branch)")
    s1 = await create_session(
        name="demo-main",
        tool="claude",
        git_root=str(demo_dir),
    )
    session_ids.append(s1.id)

    # Create tmux session with echo script
    tmux.new_session(s1.tmux_session, cwd=str(demo_dir))
    echo_script = _create_session_echo_script(
        session_name="demo-main",
        session_id=s1.id,
        tool="claude",
        branch="main",
        project_path=str(demo_dir).replace(str(Path.home()), "~"),
        tmux_session_name=s1.tmux_session,
    )
    script_path = demo_dir / ".demo-main.sh"
    script_path.write_text(echo_script)
    tmux.send_keys(s1.tmux_session, f"bash {script_path}")

    # Session 2: Feature branch with worktree
    console.print("  ✓ Creating session: demo-feature (feat/api-endpoint worktree)")
    worktree_path = demo_dir / ".worktrees" / "feat-api-endpoint"
    git.worktree_add(str(demo_dir), str(worktree_path), branch="feat/api-endpoint")

    s2 = await create_session(
        name="demo-feature",
        tool="opencode",
        git_root=str(demo_dir),
        worktree=str(worktree_path),
        branch="feat/api-endpoint",
    )
    session_ids.append(s2.id)

    # Create tmux session with echo script
    tmux.new_session(s2.tmux_session, cwd=str(worktree_path))
    echo_script = _create_session_echo_script(
        session_name="demo-feature",
        session_id=s2.id,
        tool="opencode",
        branch="feat/api-endpoint",
        project_path=str(worktree_path).replace(str(Path.home()), "~"),
        tmux_session_name=s2.tmux_session,
    )
    script_path = worktree_path / ".demo-feature.sh"
    script_path.write_text(echo_script)
    tmux.send_keys(s2.tmux_session, f"bash {script_path}")

    # Session 3: Robo session
    console.print("  ✓ Creating session: demo-robo (supervisor)")
    s3 = await create_session(
        name="demo-robo",
        tool="opencode",
        git_root=str(demo_dir),
    )
    session_ids.append(s3.id)

    # Create tmux session with robo echo script
    tmux.new_session(s3.tmux_session, cwd=str(demo_dir))
    echo_script = _create_session_echo_script(
        session_name="demo-robo",
        session_id=s3.id,
        tool="opencode",
        branch="main",
        project_path=str(demo_dir).replace(str(Path.home()), "~"),
        tmux_session_name=s3.tmux_session,
        is_robo=True,
    )
    script_path = demo_dir / ".demo-robo.sh"
    script_path.write_text(echo_script)
    tmux.send_keys(s3.tmux_session, f"bash {script_path}")

    # Write marker file
    marker_file.write_text("\n".join(session_ids))

    console.print()
    console.print(
        Panel(
            f"""[bold green]Demo environment ready![/bold green]

[bold]What was created:[/bold]
  • Temporary git repository: [cyan]{demo_dir}[/cyan]
  • 3 demo sessions:
    - [bold]demo-main[/bold] (main branch)
    - [bold]demo-feature[/bold] (feat/api-endpoint worktree)
    - [bold]demo-robo[/bold] (supervisor)

[bold]Try these commands:[/bold]
  [yellow]shoal ls[/yellow]              — See all sessions grouped by project
  [yellow]shoal status[/yellow]          — Check agent statuses
  [yellow]shoal attach demo-main[/yellow] — Attach to the main session
  [yellow]shoal wt ls[/yellow]           — See managed worktrees
  [yellow]shoal robo ls[/yellow]         — View robo profiles
  [yellow]shoal popup[/yellow]           — Open interactive dashboard

[bold]Cleanup:[/bold]
  [yellow]shoal demo stop[/yellow]       — Remove all demo sessions and files
""",
            title="[bold blue]󰚩 Shoal Demo Started[/bold blue]",
            title_align="left",
            border_style="blue",
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


async def _demo_stop_impl(custom_dir: str | None):
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
                console.print(f"  ✓ Killed tmux session: {s.name}")
            await delete_session(sid)
            console.print(f"  ✓ Deleted session: {s.name}")

    # Remove demo directory
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
        console.print(f"  ✓ Removed demo directory")

    console.print()
    console.print("[bold green]Demo environment cleaned up![/bold green]")
