"""Demo environment commands: start, stop."""

from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from shoal.core import git, tmux
from shoal.core.config import load_tool_config
from shoal.core.db import get_db, with_db
from shoal.core.state import create_session, delete_session, list_sessions, update_session
from shoal.core.theme import Icons, create_panel

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


def _create_session_echo_script(
    session_name: str,
    session_id: str,
    tool: str,
    branch: str,
    project_path: str,
    tmux_session_name: str,
    is_robo: bool = False,
) -> str:
    """Generate a simple info script for the demo sidebar pane."""
    if is_robo:
        return f"""clear
echo "Shoal Demo: robo supervisor"
echo
echo "Session details"
echo "- session_id: {session_id}"
echo "- tool: {tool}"
echo "- branch: {branch}"
echo "- project: {project_path}"
echo "- tmux: {tmux_session_name}"
echo
echo "Suggested commands for pane 0 (opencode)"
echo "1) shoal status"
echo "2) shoal ls"
echo "3) shoal logs demo-feature"
echo "4) shoal robo approve demo-feature"
echo "5) shoal robo send demo-main \"run pytest -q\""
echo
echo "Tip: if opencode requires authentication, sign in there first."
echo ""
"""
    else:
        worktree_note = ""
        if "feature" in session_name:
            worktree_note = """echo "Worktree note"
echo "- This session uses an isolated worktree."
echo "- Changes here stay isolated from main."
echo
"""

        return f"""clear
echo "Shoal Demo: {session_name}"
echo
echo "Session details"
echo "- session_id: {session_id}"
echo "- tool: {tool}"
echo "- branch: {branch}"
echo "- project: {project_path}"
echo "- tmux: {tmux_session_name}"
echo ""
{worktree_note}echo "Suggested prompts for pane 0 (opencode)"
echo "1) summarize the repository and current branch"
echo "2) run tests with: uv run pytest -q"
echo "3) implement a tiny change and show git diff"
echo "4) explain next commit message before committing"
echo
echo "Tip: if opencode requires authentication, sign in there first."
"""


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
    info_script_path: Path,
) -> None:
    """Start a 2-pane demo layout: tool pane + info pane."""
    tmux.new_session(tmux_session_name, cwd=str(cwd))
    quoted_session = shlex.quote(tmux_session_name)
    quoted_cwd = shlex.quote(str(cwd))
    tmux.run_command(f"split-window -t {quoted_session}:0 -h -p 35 -c {quoted_cwd}")
    tmux.send_keys(f"{tmux_session_name}:0.0", tool_command)
    tmux.send_keys(f"{tmux_session_name}:0.1", f"fish {shlex.quote(str(info_script_path))}")
    tmux.run_command(f"select-pane -t {quoted_session}:0.0")


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
    tool_cfg = load_tool_config("opencode")
    tool_command = tool_cfg.command

    # Session 1: Main branch
    console.print("  ✓ Creating session: demo-main (main branch)")
    s1 = await create_session(
        name="demo-main",
        tool="opencode",
        git_root=str(demo_dir),
    )
    s1.tmux_session = await _pin_demo_tmux_name(s1.name, s1.id, s1.tmux_session)
    session_ids.append(s1.id)

    # Create tmux session with tool + info panes
    echo_script = _create_session_echo_script(
        session_name="demo-main",
        session_id=s1.id,
        tool="opencode",
        branch="main",
        project_path=str(demo_dir).replace(str(Path.home()), "~"),
        tmux_session_name=s1.tmux_session,
    )
    script_path = demo_dir / ".demo-main.sh"
    script_path.write_text(echo_script)
    _start_demo_tmux_session(
        s1.tmux_session,
        demo_dir,
        tool_command=tool_command,
        info_script_path=script_path,
    )

    # Session 2: Feature branch with worktree
    console.print("  ✓ Creating session: demo-feature (feat/api-endpoint worktree)")
    worktree_path = demo_dir / ".worktrees" / "feat-api-endpoint"
    (demo_dir / ".worktrees").mkdir(parents=True, exist_ok=True)
    git.worktree_add(str(demo_dir), str(worktree_path), branch="feat/api-endpoint")

    s2 = await create_session(
        name="demo-feature",
        tool="opencode",
        git_root=str(demo_dir),
        worktree=str(worktree_path),
        branch="feat/api-endpoint",
    )
    s2.tmux_session = await _pin_demo_tmux_name(s2.name, s2.id, s2.tmux_session)
    session_ids.append(s2.id)

    # Create tmux session with tool + info panes
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
    _start_demo_tmux_session(
        s2.tmux_session,
        worktree_path,
        tool_command=tool_command,
        info_script_path=script_path,
    )

    # Session 3: Robo session
    console.print("  ✓ Creating session: demo-robo (supervisor)")
    s3 = await create_session(
        name="demo-robo",
        tool="opencode",
        git_root=str(demo_dir),
    )
    s3.tmux_session = await _pin_demo_tmux_name(s3.name, s3.id, s3.tmux_session)
    session_ids.append(s3.id)

    # Create tmux session with tool + info panes
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
    _start_demo_tmux_session(
        s3.tmux_session,
        demo_dir,
        tool_command=tool_command,
        info_script_path=script_path,
    )

    # Write marker file
    marker_file.write_text("\n".join(session_ids))

    console.print()
    console.print(
        create_panel(
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
