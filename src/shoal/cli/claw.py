"""CLI commands for the Shoal claw scheduling and trigger system."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from shoal.models.claw import TriggerDef, TriggerExecution

import typer

from shoal.cli._console import get_console

app = typer.Typer(no_args_is_help=True)


# ---------------------------------------------------------------------------
# PID helpers
# ---------------------------------------------------------------------------


def _pid_file() -> Path:

    from shoal.core.config import state_dir

    return state_dir() / "claw.pid"


def _read_pid() -> int | None:
    pf = _pid_file()
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pf.unlink(missing_ok=True)
        return None


# ---------------------------------------------------------------------------
# Trigger CRUD
# ---------------------------------------------------------------------------


@app.command("add")
def claw_add(
    name: Annotated[str, typer.Argument(help="Trigger name (unique)")],
    template: Annotated[str, typer.Option("--template", "-t", help="Template to spawn")] = "",
    prompt: Annotated[str, typer.Option("--prompt", "-p", help="Initial prompt")] = "",
    prefix: Annotated[str, typer.Option("--prefix", help="Session name prefix")] = "",
    cron: Annotated[str, typer.Option("--cron", help="Cron expression (5-field)")] = "",
    event: Annotated[str, typer.Option("--event", help="Lifecycle event name")] = "",
    event_filter: Annotated[str, typer.Option("--event-filter", help="JSON event filter")] = "",
    file: Annotated[str, typer.Option("--file", help="File change glob")] = "",
    timer: Annotated[str, typer.Option("--timer", help="ISO timestamp for one-shot")] = "",
    webhook: Annotated[bool, typer.Option("--webhook", help="Webhook-triggered")] = False,
    max_concurrent: Annotated[
        int, typer.Option("--max-concurrent", help="Max concurrent sessions")
    ] = 1,
    cooldown: Annotated[int, typer.Option("--cooldown", help="Cooldown seconds")] = 60,
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tags")] = None,
) -> None:
    """Create a trigger."""
    from shoal.core.db import with_db
    from shoal.models.claw import TriggerDef, TriggerKind

    # Determine kind
    kinds_set: list[tuple[str, TriggerKind]] = []
    if cron:
        kinds_set.append((cron, TriggerKind.cron))
    if event:
        kinds_set.append((event, TriggerKind.event))
    if file:
        kinds_set.append((file, TriggerKind.file))
    if timer:
        kinds_set.append((timer, TriggerKind.timer))
    if webhook:
        kinds_set.append(("webhook", TriggerKind.webhook))

    if len(kinds_set) != 1:
        get_console().print(
            "[red]Specify exactly one trigger kind:"
            " --cron, --event, --file, --timer, or --webhook[/red]"
        )
        raise typer.Exit(1)

    _, kind = kinds_set[0]

    if not template:
        get_console().print("[red]--template is required[/red]")
        raise typer.Exit(1)

    # Parse event_filter
    ef: dict[str, str] = {}
    if event_filter:
        try:
            ef = json.loads(event_filter)
        except json.JSONDecodeError:
            get_console().print("[red]--event-filter must be valid JSON[/red]")
            raise typer.Exit(1) from None

    trigger = TriggerDef(
        id=uuid.uuid4().hex[:8],
        name=name,
        kind=kind,
        template=template,
        prompt=prompt,
        session_name_prefix=prefix or name,
        cron_expr=cron,
        event_name=event,
        event_filter=ef,
        file_pattern=file,
        fire_at=timer,
        max_concurrent=max_concurrent,
        cooldown_seconds=cooldown,
        tags=tag or [],
        created_at=datetime.now(UTC).isoformat(),
    )

    async def _save() -> None:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        existing = await db.get_trigger(name)
        if existing:
            get_console().print(f"[red]Trigger '{name}' already exists[/red]")
            raise typer.Exit(1)
        await db.save_trigger(trigger)

    asyncio.run(with_db(_save()))
    get_console().print(f"[green]Trigger '{name}' created ({kind.value})[/green]")


@app.command("rm")
def claw_rm(
    name: Annotated[str, typer.Argument(help="Trigger name")],
) -> None:
    """Remove a trigger."""
    from shoal.core.db import with_db

    async def _delete() -> None:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        existing = await db.get_trigger(name)
        if not existing:
            get_console().print(f"[red]Trigger '{name}' not found[/red]")
            raise typer.Exit(1)
        await db.delete_trigger(name)

    asyncio.run(with_db(_delete()))
    get_console().print(f"Trigger '{name}' removed")


@app.command("ls")
def claw_ls() -> None:
    """List all triggers."""
    from rich.table import Table

    from shoal.core.db import with_db

    async def _list() -> list[TriggerDef]:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        return await db.list_triggers()

    triggers = asyncio.run(with_db(_list()))

    table = Table()
    table.add_column("NAME", style="bold")
    table.add_column("KIND")
    table.add_column("ENABLED")
    table.add_column("TEMPLATE")
    table.add_column("SCHEDULE/PATTERN")
    table.add_column("FIRES", justify="right")
    table.add_column("LAST FIRED")

    for t in triggers:
        schedule = t.cron_expr or t.event_name or t.file_pattern or t.fire_at or "webhook"
        enabled = "[green]yes[/green]" if t.enabled else "[dim]no[/dim]"
        last = t.last_fired_at[:19] if t.last_fired_at else "-"
        table.add_row(t.name, t.kind.value, enabled, t.template, schedule, str(t.fire_count), last)

    get_console().print(table)


@app.command("info")
def claw_info(
    name: Annotated[str, typer.Argument(help="Trigger name")],
) -> None:
    """Show trigger details and recent executions."""
    from shoal.core.db import with_db

    async def _info() -> tuple[TriggerDef | None, list[TriggerExecution]]:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        trigger = await db.get_trigger(name)
        execs: list[TriggerExecution] = []
        if trigger:
            execs = await db.list_executions(trigger.id, limit=10)
        return trigger, execs

    trigger, execs = asyncio.run(with_db(_info()))
    if not trigger:
        get_console().print(f"[red]Trigger '{name}' not found[/red]")
        raise typer.Exit(1)

    get_console().print(f"[bold]{trigger.name}[/bold] ({trigger.kind.value})")
    get_console().print(f"  template:       {trigger.template}")
    get_console().print(f"  enabled:        {trigger.enabled}")
    get_console().print(f"  max_concurrent: {trigger.max_concurrent}")
    get_console().print(f"  cooldown:       {trigger.cooldown_seconds}s")
    get_console().print(f"  fire_count:     {trigger.fire_count}")
    if trigger.prompt:
        get_console().print(f"  prompt:         {trigger.prompt[:60]}")
    if trigger.cron_expr:
        get_console().print(f"  cron:           {trigger.cron_expr}")
    if trigger.event_name:
        get_console().print(f"  event:          {trigger.event_name}")
        if trigger.event_filter:
            get_console().print(f"  filter:         {trigger.event_filter}")
    if trigger.file_pattern:
        get_console().print(f"  file_pattern:   {trigger.file_pattern}")

    if execs:
        get_console().print("\n[bold]Recent executions:[/bold]")
        for ex in execs:
            status_color = {"running": "blue", "completed": "green", "error": "red"}.get(
                ex.status, "yellow"
            )
            get_console().print(
                f"  [{status_color}]{ex.status:10s}[/{status_color}] "
                f"{ex.session_name:30s} {ex.started_at[:19]}"
            )


@app.command("enable")
def claw_enable(
    name: Annotated[str, typer.Argument(help="Trigger name")],
) -> None:
    """Enable a trigger."""
    _set_enabled(name, enabled=True)


@app.command("disable")
def claw_disable(
    name: Annotated[str, typer.Argument(help="Trigger name")],
) -> None:
    """Disable a trigger."""
    _set_enabled(name, enabled=False)


def _set_enabled(name: str, *, enabled: bool) -> None:
    from shoal.core.db import with_db

    async def _toggle() -> None:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        trigger = await db.get_trigger(name)
        if not trigger:
            get_console().print(f"[red]Trigger '{name}' not found[/red]")
            raise typer.Exit(1)
        trigger.enabled = enabled
        await db.save_trigger(trigger)

    asyncio.run(with_db(_toggle()))
    state = "enabled" if enabled else "disabled"
    get_console().print(f"Trigger '{name}' {state}")


@app.command("fire")
def claw_fire(
    name: Annotated[str, typer.Argument(help="Trigger name")],
) -> None:
    """Manually fire a trigger (for testing)."""
    from shoal.core.db import with_db

    async def _fire() -> None:
        from shoal.core.config import load_config
        from shoal.core.db import get_db
        from shoal.services.claw_daemon import fire_trigger

        db = await get_db()
        await db.connect()
        trigger = await db.get_trigger(name)
        if not trigger:
            get_console().print(f"[red]Trigger '{name}' not found[/red]")
            raise typer.Exit(1)

        await fire_trigger(trigger, load_config().claw)

    asyncio.run(with_db(_fire()))
    get_console().print(f"Trigger '{name}' fired")


@app.command("history")
def claw_history(
    name: Annotated[str | None, typer.Argument(help="Trigger name (all if omitted)")] = None,
) -> None:
    """Show trigger execution history."""
    from rich.table import Table

    from shoal.core.db import with_db

    async def _history() -> list[TriggerExecution]:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        trigger_id = None
        if name:
            trigger = await db.get_trigger(name)
            if not trigger:
                get_console().print(f"[red]Trigger '{name}' not found[/red]")
                raise typer.Exit(1)
            trigger_id = trigger.id
        return await db.list_executions(trigger_id, limit=50)

    execs = asyncio.run(with_db(_history()))

    table = Table()
    table.add_column("TRIGGER")
    table.add_column("SESSION")
    table.add_column("STATUS")
    table.add_column("STARTED")
    table.add_column("COMPLETED")

    for ex in execs:
        status_color = {"running": "blue", "completed": "green", "error": "red"}.get(
            ex.status, "yellow"
        )
        table.add_row(
            ex.trigger_name,
            ex.session_name,
            f"[{status_color}]{ex.status}[/{status_color}]",
            ex.started_at[:19],
            ex.completed_at[:19] if ex.completed_at else "-",
        )

    get_console().print(table)


# ---------------------------------------------------------------------------
# Daemon control
# ---------------------------------------------------------------------------


@app.command("start")
def claw_start(
    daemon: Annotated[
        bool, typer.Option("--daemon", "-d", help="Run as background daemon")
    ] = False,
) -> None:
    """Start the claw scheduling daemon."""
    from shoal.core.config import load_config

    cfg = load_config().claw

    get_console().print("[bold]Claw daemon[/bold]")
    get_console().print(f"  poll_interval: {cfg.poll_interval}s")
    get_console().print()

    if daemon:
        existing = _read_pid()
        if existing:
            get_console().print(f"[red]Claw daemon already running (pid: {existing})[/red]")
            raise typer.Exit(1)

        proc = subprocess.Popen(
            [sys.executable, "-m", "shoal.services.claw_daemon"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        get_console().print(f"Claw daemon started (pid: {proc.pid})")
        return

    from shoal.services.claw_daemon import main

    asyncio.run(main(cfg))


@app.command("stop")
def claw_stop() -> None:
    """Stop the claw daemon."""
    pid = _read_pid()
    if not pid:
        get_console().print("[red]Claw daemon is not running[/red]")
        raise typer.Exit(1)

    os.kill(pid, signal.SIGTERM)
    _pid_file().unlink(missing_ok=True)
    get_console().print(f"Claw daemon stopped (pid: {pid})")


@app.command("status")
def claw_status() -> None:
    """Show claw daemon status and trigger counts."""
    from shoal.core.db import with_db

    pid = _read_pid()
    if pid:
        get_console().print(f"[green]Claw daemon running (pid: {pid})[/green]")
    else:
        get_console().print("Claw daemon not running")

    async def _counts() -> tuple[int, int, int]:
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        triggers = await db.list_triggers()
        total = len(triggers)
        enabled = sum(1 for t in triggers if t.enabled)
        return total, enabled, total - enabled

    total, enabled, disabled = asyncio.run(with_db(_counts()))
    get_console().print(f"  triggers: {total} ({enabled} enabled, {disabled} disabled)")
