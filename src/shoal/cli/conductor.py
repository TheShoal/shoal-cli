"""Conductor (supervisory agent) commands: setup, start, stop, status, ls."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import tmux
from shoal.core.config import config_dir, ensure_dirs, load_conductor_profile, state_dir
from shoal.models.state import ConductorState

console = Console()

app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def conductor_default(ctx: typer.Context) -> None:
    """Conductor management (default: ls)."""
    if ctx.invoked_subcommand is None:
        conductor_ls()


def _conductor_runtime_dir(name: str) -> Path:
    return state_dir() / "conductor" / name


def _conductor_state_file(name: str) -> Path:
    return _conductor_runtime_dir(name) / "state.json"


@app.command("setup")
def conductor_setup(
    name: Annotated[str | None, typer.Argument(help="Conductor profile name")] = None,
    tool: Annotated[str | None, typer.Option("-t", "--tool", help="AI tool to use")] = None,
) -> None:
    """Create a conductor profile."""
    ensure_dirs()
    name = name or "default"
    tool = tool or "opencode"

    profile_file = config_dir() / "conductor" / f"{name}.toml"
    runtime_dir = _conductor_runtime_dir(name)

    # Create profile if it doesn't exist
    if not profile_file.exists():
        profile_file.parent.mkdir(parents=True, exist_ok=True)
        profile_file.write_text(
            f"""# Shoal conductor profile: {name}

[conductor]
name = "{name}"
tool = "{tool}"
auto_approve = false

[monitoring]
poll_interval = 10
waiting_timeout = 300

[escalation]
notify = true
auto_respond = false

[tasks]
log_file = "task-log.md"
"""
        )
        console.print(f"Created profile: {profile_file}")
    else:
        console.print(f"Profile already exists: {profile_file}")

    # Create runtime directory with AGENTS.md
    runtime_dir.mkdir(parents=True, exist_ok=True)

    agents_file = runtime_dir / "AGENTS.md"
    if not agents_file.exists():
        agents_file.write_text(
            """# Shoal Conductor

You are a conductor — a supervisory AI agent that monitors and coordinates other AI coding agents.

## Your Responsibilities

1. **Monitor agent status** — Run `shoal status` periodically to check on all active sessions
2. **Handle waiting agents** — When a session enters "waiting" state, check what it needs
3. **Route tasks** — If an agent finishes, check if there are pending tasks to assign
4. **Escalate** — If an agent is stuck or erroring, notify the user

## Available Commands

- `shoal status` — See all session statuses
- `shoal ls` — List all sessions with details
- `shoal attach <name>` — View a specific session
- `shoal nvim diagnostics <name>` — Check LSP errors in a session's editor

## Workflow

1. Check `shoal status` every few minutes
2. If any session is "waiting", investigate what it needs
3. If you can resolve the issue (e.g., approve a safe operation), do so
4. If not, log it and notify the user
5. Track all actions in task-log.md

## Rules

- Never approve destructive operations (force push, delete production, etc.)
  without user confirmation
- Log every action you take
- Prefer asking the user over making assumptions about intent
"""
        )
        console.print(f"Created AGENTS.md: {agents_file}")

    task_log = runtime_dir / "task-log.md"
    if not task_log.exists():
        task_log.write_text(f"# Conductor Task Log: {name}\n\n---\n\n")
        console.print(f"Created task log: {task_log}")

    console.print()
    console.print(f"Conductor '{name}' ready")
    console.print(f"  Profile: {profile_file}")
    console.print(f"  Runtime: {runtime_dir}")
    console.print()
    console.print(f"Start with: shoal conductor start {name}")


@app.command("start")
def conductor_start(
    name: Annotated[str | None, typer.Argument(help="Conductor profile")] = None,
) -> None:
    """Start a conductor session."""
    ensure_dirs()
    name = name or "default"

    profile_file = config_dir() / "conductor" / f"{name}.toml"
    runtime_dir = _conductor_runtime_dir(name)

    if not profile_file.exists():
        console.print(f"[red]Conductor profile '{name}' not found[/red]")
        console.print(f"Create it with: shoal conductor setup {name}")
        raise typer.Exit(1)

    # Read tool from profile
    try:
        profile = load_conductor_profile(name)
        tool = profile.tool
    except FileNotFoundError:
        tool = "opencode"

    tmux_session = f"shoal_conductor_{name}"

    if tmux.has_session(tmux_session):
        console.print(f"[red]Conductor '{name}' is already running[/red]")
        console.print(f"Attach with: tmux attach -t {tmux_session}")
        raise typer.Exit(1)

    # Ensure runtime dir exists
    if not runtime_dir.exists():
        conductor_setup(name, tool)

    # Create tmux session
    tmux.new_session(tmux_session, cwd=str(runtime_dir))
    tmux.set_environment(tmux_session, "SHOAL_CONDUCTOR", name)

    # Get tool command and launch
    from shoal.core.config import load_tool_config

    try:
        tool_cfg = load_tool_config(tool)
        tool_cmd = tool_cfg.command
    except FileNotFoundError:
        tool_cmd = tool

    tmux.send_keys(tmux_session, tool_cmd)

    # Write state
    state = ConductorState(
        name=name,
        tool=tool,
        tmux_session=tmux_session,
        status="running",
        started_at=datetime.now(UTC),
    )
    state_file = _conductor_state_file(name)
    state_file.write_text(state.model_dump_json(indent=2))

    console.print(f"Conductor '{name}' started")
    console.print(f"  Tool: {tool}")
    console.print(f"  Tmux: {tmux_session}")
    console.print(f"  Runtime: {runtime_dir}")
    console.print()
    console.print(f"Attach with: tmux attach -t {tmux_session}")


@app.command("stop")
def conductor_stop(
    name: Annotated[str | None, typer.Argument(help="Conductor to stop")] = None,
) -> None:
    """Stop a conductor."""
    ensure_dirs()
    name = name or "default"

    tmux_session = f"shoal_conductor_{name}"
    state_file = _conductor_state_file(name)

    if not tmux.has_session(tmux_session):
        console.print(f"[red]Conductor '{name}' is not running[/red]")
        # Update state if stale
        if state_file.exists():
            state = ConductorState.model_validate_json(state_file.read_text())
            state = state.model_copy(update={"status": "stopped"})
            state_file.write_text(state.model_dump_json(indent=2))
        raise typer.Exit(1)

    tmux.kill_session(tmux_session)

    if state_file.exists():
        state = ConductorState.model_validate_json(state_file.read_text())
        state = state.model_copy(update={"status": "stopped"})
        state_file.write_text(state.model_dump_json(indent=2))

    console.print(f"Conductor '{name}' stopped")


@app.command("status")
def conductor_status() -> None:
    """Conductor health check."""
    ensure_dirs()
    conductor_dir = state_dir() / "conductor"
    if not conductor_dir.exists():
        console.print("No conductors configured")
        console.print("Create one with: shoal conductor setup <name>")
        return

    found = 0
    for state_file in sorted(conductor_dir.glob("*/state.json")):
        state = ConductorState.model_validate_json(state_file.read_text())
        found += 1

        if tmux.has_session(state.tmux_session):
            cond_status = "[green]running[/green]"
        else:
            cond_status = "[bright_black]stopped[/bright_black]"
            updated = state.model_copy(update={"status": "stopped"})
            state_file.write_text(updated.model_dump_json(indent=2))

        started = state.started_at.strftime("%Y-%m-%dT%H:%M:%SZ") if state.started_at else "-"
        console.print(f"Conductor: {state.name}")
        console.print(f"  Tool: {state.tool}")
        console.print(f"  Status: {cond_status}")
        console.print(f"  Tmux: {state.tmux_session}")
        console.print(f"  Started: {started}")
        console.print()

    if found == 0:
        console.print("No conductors found")
        console.print("Set up with: shoal conductor setup <name>")


@app.command("ls")
def conductor_ls() -> None:
    """List conductor profiles."""
    ensure_dirs()

    profiles_dir = config_dir() / "conductor"
    if not profiles_dir.exists():
        console.print("No conductor profiles")
        console.print("Create one with: shoal conductor setup <name>")
        return

    profiles = sorted(profiles_dir.glob("*.toml"))
    if not profiles:
        console.print("No conductor profiles")
        console.print("Create one with: shoal conductor setup <name>")
        return

    table = Table(show_edge=False, pad_edge=False)
    table.add_column("NAME", width=20)
    table.add_column("TOOL", width=10)
    table.add_column("STATUS", width=10)
    table.add_column("STARTED")

    for profile_path in profiles:
        name = profile_path.stem
        try:
            profile = load_conductor_profile(name)
            tool = profile.tool
        except Exception:
            tool = "opencode"

        tmux_session = f"shoal_conductor_{name}"
        started = "-"

        state_file = _conductor_state_file(name)
        if state_file.exists():
            state = ConductorState.model_validate_json(state_file.read_text())
            started = state.started_at.strftime("%Y-%m-%dT%H:%M:%SZ") if state.started_at else "-"

        if tmux.has_session(tmux_session):
            cond_status = "[green]running[/green]"
        else:
            cond_status = "[bright_black]stopped[/bright_black]"

        table.add_row(name, tool, cond_status, started)

    console.print(table)
