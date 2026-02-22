"""Robo (supervisory agent) commands: setup, start, stop, send, approve, status, ls."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shoal.core import tmux
from shoal.core.config import config_dir, ensure_dirs, load_config, load_robo_profile, state_dir
from shoal.core.db import get_db, with_db
from shoal.core.theme import Icons, create_panel, create_table
from shoal.models.state import RoboState, SessionStatus

console = Console()

app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def robo_default(ctx: typer.Context) -> None:
    """Robo management (default: ls)."""
    if ctx.invoked_subcommand is None:
        robo_ls()


def _robo_runtime_dir(name: str) -> Path:
    return state_dir() / "robo" / name


def _robo_session_prefix() -> str:
    cfg = load_config()
    return (cfg.robo.session_prefix or "").strip()


def _build_robo_tmux_session(name: str) -> str:
    prefix = _robo_session_prefix()
    if not prefix:
        return name
    if prefix.endswith("_"):
        return f"{prefix}{name}"
    return f"{prefix}_{name}"


@app.command("setup")
def robo_setup(
    name: Annotated[str | None, typer.Argument(help="Robo profile name")] = None,
    tool: Annotated[str | None, typer.Option("-t", "--tool", help="AI tool to use")] = None,
) -> None:
    """Create a robo profile."""
    ensure_dirs()
    name = name or "default"
    tool = tool or "opencode"

    # Try new path first, support old path for backward compat
    profile_file = config_dir() / "robo" / f"{name}.toml"
    runtime_dir = _robo_runtime_dir(name)

    # Create profile if it doesn't exist
    if not profile_file.exists():
        profile_file.parent.mkdir(parents=True, exist_ok=True)
        profile_file.write_text(
            f"""# Shoal robo profile: {name}

[robo]
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
            """# Shoal Robo-Fish

You are a robo-fish — a supervisory AI agent that leads and coordinates a shoal of AI coding agents.

## The Analogy

In nature, researchers have shown that biomimetic robot fish can integrate
into and lead schools of real fish (see Marras & Porfiri 2012,
Papaspyros et al. 2019). The robot alternates between following and
leading to gain social acceptance, then guides the group.

In Shoal, you are that robo-fish. You monitor the shoal of AI coding
agents, approve their actions, and ensure the group stays on track.

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
- `shoal robo approve <name>` — Approve a waiting session (sends Enter)
- `shoal robo send <name> <keys>` — Send specific keys to a session

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
        task_log.write_text(f"# Robo Task Log: {name}\n\n---\n\n")
        console.print(f"Created task log: {task_log}")

    console.print()
    console.print(f"Robo '{name}' ready")
    console.print(f"  Profile: {profile_file}")
    console.print(f"  Runtime: {runtime_dir}")
    console.print()
    console.print(f"Start with: shoal robo start {name}")


@app.command("start")
def robo_start(
    name: Annotated[str | None, typer.Argument(help="Robo profile")] = None,
) -> None:
    """Start a robo session."""
    asyncio.run(with_db(_robo_start_impl(name)))


async def _robo_start_impl(name: str | None) -> None:
    ensure_dirs()
    name = name or "default"

    runtime_dir = _robo_runtime_dir(name)

    # Check if profile exists (backward compat with old conductor path)
    try:
        profile = load_robo_profile(name)
        tool = profile.tool
    except FileNotFoundError:
        console.print(f"[red]Error: Robo profile '{name}' not found[/red]")
        console.print()
        console.print("[yellow]Available profiles:[/yellow]")
        robo_dir = config_dir() / "robo"
        if robo_dir.exists() and list(robo_dir.glob("*.toml")):
            for f in sorted(robo_dir.glob("*.toml")):
                console.print(f"  • {f.stem}")
        else:
            console.print("  [dim](none configured)[/dim]")
        console.print()
        console.print(f"[yellow]Create a profile:[/yellow] shoal robo setup {name}")
        raise typer.Exit(1) from None

    tmux_session = _build_robo_tmux_session(name)

    if tmux.has_session(tmux_session):
        console.print(f"[red]Error: Robo '{name}' is already running[/red]")
        console.print(f"[dim]Tmux session: {tmux_session}[/dim]")
        console.print()
        console.print("[yellow]Options:[/yellow]")
        console.print(f"  • Attach to existing robo: tmux attach -t {tmux_session}")
        console.print(f"  • Stop and restart: shoal robo stop {name} && shoal robo start {name}")
        raise typer.Exit(1)

    # Ensure runtime dir exists
    if not runtime_dir.exists():
        robo_setup(name, tool)

    # Create tmux session
    tmux.new_session(tmux_session, cwd=str(runtime_dir))
    tmux.set_environment(tmux_session, "SHOAL_ROBO", name)

    # Get tool command and launch
    from shoal.core.config import load_tool_config

    try:
        tool_cfg = load_tool_config(tool)
        tool_cmd = tool_cfg.command
    except FileNotFoundError:
        tool_cmd = tool

    tmux.send_keys(tmux_session, tool_cmd)

    # Write state to DB
    state = RoboState(
        name=name,
        tool=tool,
        tmux_session=tmux_session,
        status=SessionStatus.running,
        started_at=datetime.now(UTC),
    )
    db = await get_db()
    await db.save_robo(state)

    console.print(f"Robo '{name}' started")
    console.print(f"  Tool: {tool}")
    console.print(f"  Tmux: {tmux_session}")
    console.print(f"  Runtime: {runtime_dir}")
    console.print()
    console.print(f"Attach with: tmux attach -t {tmux_session}")


@app.command("stop")
def robo_stop(
    name: Annotated[str | None, typer.Argument(help="Robo to stop")] = None,
) -> None:
    """Stop a robo."""
    asyncio.run(with_db(_robo_stop_impl(name)))


async def _robo_stop_impl(name: str | None) -> None:
    ensure_dirs()
    name = name or "default"

    db = await get_db()
    state = await db.get_robo(name)
    tmux_session = state.tmux_session if state else _build_robo_tmux_session(name)

    if not tmux.has_session(tmux_session):
        console.print(f"[red]Robo '{name}' is not running[/red]")
        if state:
            updated = state.model_copy(update={"status": "stopped"})
            await db.save_robo(updated)
        raise typer.Exit(1)

    tmux.kill_session(tmux_session)

    if state:
        updated = state.model_copy(update={"status": "stopped"})
        await db.save_robo(updated)

    console.print(f"Robo '{name}' stopped")


@app.command("send")
def robo_send(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    keys: Annotated[str, typer.Argument(help="Keys to send")],
) -> None:
    """Send keys to a session's tmux pane."""
    asyncio.run(with_db(_robo_send_impl(session, keys)))


async def _robo_send_impl(session_name_or_id: str, keys: str) -> None:
    ensure_dirs()
    from shoal.core.state import get_session, resolve_session

    sid = await resolve_session(session_name_or_id)
    if not sid:
        console.print(f"[red]Session not found: {session_name_or_id}[/red]")
        raise typer.Exit(1)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not tmux.has_session(s.tmux_session):
        console.print(f"[red]Tmux session '{s.tmux_session}' not found[/red]")
        raise typer.Exit(1)

    tmux.send_keys(s.tmux_session, keys)
    console.print(f"Sent keys to '{s.name}'")


@app.command("approve")
def robo_approve(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
) -> None:
    """Approve a waiting session (sends Enter)."""
    asyncio.run(with_db(_robo_send_impl(session, "")))


@app.command("status")
def robo_status() -> None:
    """Robo health check."""
    asyncio.run(with_db(_robo_status_impl()))


async def _robo_status_impl() -> None:
    ensure_dirs()
    db = await get_db()
    robos = await db.list_robos()

    if not robos:
        console.print("No robos configured")
        console.print("Create one with: shoal robo setup <name>")
        return

    for state in robos:
        if tmux.has_session(state.tmux_session):
            robo_status_text = "[green]running[/green]"
        else:
            robo_status_text = "[bright_black]stopped[/bright_black]"
            if state.status != "stopped":
                state = state.model_copy(update={"status": "stopped"})
                await db.save_robo(state)

        started = state.started_at.strftime("%Y-%m-%dT%H:%M:%SZ") if state.started_at else "-"
        console.print(f"Robo: {state.name}")
        console.print(f"  Tool: {state.tool}")
        console.print(f"  Status: {robo_status_text}")
        console.print(f"  Tmux: {state.tmux_session}")
        console.print(f"  Started: {started}")
        console.print()


@app.command("ls")
def robo_ls() -> None:
    """List robo profiles."""
    asyncio.run(with_db(_robo_ls_impl()))


async def _robo_ls_impl() -> None:
    ensure_dirs()
    db = await get_db()

    # Check both new and old paths for backward compat
    profiles_dir = config_dir() / "robo"
    old_profiles_dir = config_dir() / "conductor"

    profiles = []
    if profiles_dir.exists():
        profiles.extend(sorted(profiles_dir.glob("*.toml")))
    if old_profiles_dir.exists():
        profiles.extend(sorted(old_profiles_dir.glob("*.toml")))

    # Deduplicate by name
    seen_names = set()
    unique_profiles = []
    for p in profiles:
        if p.stem not in seen_names:
            seen_names.add(p.stem)
            unique_profiles.append(p)

    if not unique_profiles:
        console.print("No robo profiles")
        console.print("Create one with: shoal robo setup <name>")
        return

    # Use consistent table style with Panel (fixing Task 1)
    table = create_table(padding=(0, 1))
    table.add_column("NAME", width=20)
    table.add_column("TOOL", width=10)
    table.add_column("STATUS", width=10)
    table.add_column("STARTED")

    for profile_path in unique_profiles:
        name = profile_path.stem
        try:
            profile = load_robo_profile(name)
            tool = profile.tool
        except Exception:
            tool = "opencode"

        tmux_session = _build_robo_tmux_session(name)
        started = "-"

        state = await db.get_robo(name)
        if state:
            started = state.started_at.strftime("%Y-%m-%dT%H:%M:%SZ") if state.started_at else "-"

        if tmux.has_session(tmux_session):
            robo_status_display = "[green]running[/green]"
        else:
            robo_status_display = "[bright_black]stopped[/bright_black]"

        table.add_row(name, tool, robo_status_display, started)

    console.print()
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.DASHBOARD} Robo[/bold blue]",
            title_align="left",
        )
    )
