"""Claw scheduling daemon — autonomous trigger execution for Shoal.

Checks cron/timer triggers on a poll loop and hooks into lifecycle events
for event/file triggers.  Spawns sessions via ``create_session_lifecycle``.
Follows the same daemon pattern as ``services/robo_supervisor.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from shoal.models.claw import TriggerDef, TriggerExecution, TriggerKind
from shoal.models.config.general import ClawConfig

logger = logging.getLogger("shoal.claw")

_MAX_BACKOFF = 300.0


# ---------------------------------------------------------------------------
# Cron matcher (5-field: minute hour dom month dow)
# ---------------------------------------------------------------------------


def _cron_field_matches(field: str, value: int) -> bool:
    """Check if a single cron field matches a value."""
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            return True
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            start = 0 if base == "*" else int(base)
            if (value - start) % step == 0 and value >= start:
                return True
        elif "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(part) == value:
                return True
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    """Check if a 5-field cron expression matches a datetime."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    return (
        _cron_field_matches(minute, dt.minute)
        and _cron_field_matches(hour, dt.hour)
        and _cron_field_matches(dom, dt.day)
        and _cron_field_matches(month, dt.month)
        and _cron_field_matches(dow, dt.weekday())  # 0=Monday
    )


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


class ClawDaemon:
    """Autonomous trigger daemon that polls cron/timers and hooks lifecycle events."""

    def __init__(self, config: ClawConfig) -> None:
        self.config = config
        self._running = True
        self._consecutive_errors = 0
        self._last_cron_minute: str = ""

    async def run(self) -> None:
        """Start the daemon with signal handling and PID file."""
        from shoal.core.config import ensure_dirs, state_dir

        ensure_dirs()

        log_file = state_dir() / "logs" / self.config.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(log_file))
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        shoal_logger = logging.getLogger("shoal")
        shoal_logger.setLevel(logging.INFO)
        shoal_logger.addHandler(handler)

        pid_file = state_dir() / "claw.pid"
        pid_file.write_text(str(os.getpid()))

        logger.info(
            "Claw daemon started (pid: %d, poll: %ds)",
            os.getpid(),
            self.config.poll_interval,
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop)

        self._register_event_hooks()

        try:
            while self._running:
                try:
                    await self._poll()
                    self._consecutive_errors = 0
                except Exception:
                    self._consecutive_errors += 1
                    logger.exception("Poll cycle failed, continuing")

                delay = float(self.config.poll_interval)
                if self._consecutive_errors > 0:
                    delay = min(
                        delay * (2 ** (self._consecutive_errors - 1)),
                        _MAX_BACKOFF,
                    )
                await asyncio.sleep(delay)
        finally:
            pid_file.unlink(missing_ok=True)
            logger.info("Claw daemon stopped")

    def _stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Poll loop (cron + timer triggers)
    # ------------------------------------------------------------------

    async def _poll(self) -> None:
        """Check cron and timer triggers."""
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        triggers = await db.list_triggers()
        now = datetime.now(UTC)
        now_minute = now.strftime("%Y-%m-%dT%H:%M")

        for trigger in triggers:
            if not trigger.enabled:
                continue

            if trigger.kind == TriggerKind.cron:
                if now_minute == self._last_cron_minute:
                    continue
                if (
                    cron_matches(trigger.cron_expr, now)
                    and await self._should_fire(trigger, now)
                ):
                    await self._fire(trigger)

            elif trigger.kind == TriggerKind.timer:
                if (
                    trigger.fire_at
                    and trigger.fire_at <= now.isoformat()
                    and await self._should_fire(trigger, now)
                ):
                    await self._fire(trigger)

        self._last_cron_minute = now_minute

    async def _should_fire(self, trigger: TriggerDef, now: datetime) -> bool:
        """Check cooldown and max_concurrent constraints."""
        from shoal.core.db import get_db

        # Cooldown check
        if trigger.last_fired_at:
            last = datetime.fromisoformat(trigger.last_fired_at)
            if (now - last).total_seconds() < trigger.cooldown_seconds:
                return False

        # Max concurrent check
        db = await get_db()
        active = await db.count_active_executions(trigger.id)
        return active < trigger.max_concurrent

    # ------------------------------------------------------------------
    # Event/file hooks
    # ------------------------------------------------------------------

    def _register_event_hooks(self) -> None:
        """Register lifecycle hooks for event and file triggers."""
        from shoal.models.state import LifecycleEvent
        from shoal.services.lifecycle import on

        async def _on_lifecycle_event(event: LifecycleEvent, **kwargs: Any) -> None:
            await self._handle_event(event.value, kwargs)

        for evt in LifecycleEvent:
            if evt == LifecycleEvent.trigger_fired:
                continue  # don't recurse
            on(evt, _on_lifecycle_event)

    async def _handle_event(self, event_name: str, kwargs: dict[str, Any]) -> None:
        """Check event/file triggers against a lifecycle event."""
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()
        triggers = await db.list_triggers()

        # Early exit: skip iteration if no event/file triggers exist
        reactive = [
            t
            for t in triggers
            if t.enabled and t.kind in (TriggerKind.event, TriggerKind.file)
        ]
        if not reactive:
            return

        now = datetime.now(UTC)

        for trigger in reactive:
            if (
                trigger.kind == TriggerKind.event
                and trigger.event_name == event_name
                and self._event_filter_matches(trigger.event_filter, kwargs)
                and await self._should_fire(trigger, now)
            ):
                await self._fire(trigger)

            elif trigger.kind == TriggerKind.file and event_name == "file_changed":
                file_paths = kwargs.get("file_paths", [])
                if (
                    isinstance(file_paths, list)
                    and any(fnmatch(str(p), trigger.file_pattern) for p in file_paths)
                    and await self._should_fire(trigger, now)
                ):
                    await self._fire(trigger)

    @staticmethod
    def _event_filter_matches(
        event_filter: dict[str, str], kwargs: dict[str, Any]
    ) -> bool:
        """Exact-match filter on event kwargs."""
        for key, expected in event_filter.items():
            actual = kwargs.get(key)
            if actual is None:
                # Check nested: some events pass SessionState objects
                session = kwargs.get("session")
                if session is not None:
                    actual = getattr(session, key, None)
            if str(actual) != expected:
                return False
        return True

    # ------------------------------------------------------------------
    # Fire a trigger (delegates to module-level fire_trigger)
    # ------------------------------------------------------------------

    async def _fire(self, trigger: TriggerDef) -> None:
        await fire_trigger(trigger, self.config)


# ---------------------------------------------------------------------------
# Public fire function — used by daemon, CLI, MCP tools, webhook
# ---------------------------------------------------------------------------


async def fire_trigger(trigger: TriggerDef, config: ClawConfig) -> None:
    """Spawn a session for a trigger.

    This is the canonical fire path shared by the daemon poll loop,
    lifecycle event hooks, ``shoal claw fire``, MCP tools, and the
    webhook API endpoint.
    """
    from shoal.core import git
    from shoal.core.config import (
        ensure_dirs,
        load_config,
        load_template,
        load_tool_config,
    )
    from shoal.core.db import get_db
    from shoal.models.state import LifecycleEvent
    from shoal.services.lifecycle import create_session_lifecycle, emit

    ensure_dirs()
    now = datetime.now(UTC)
    timestamp = now.strftime("%H%M%S")
    session_name = (
        f"{trigger.session_name_prefix or trigger.name}-{timestamp}"
    )
    execution_id = uuid.uuid4().hex[:8]

    logger.info(
        "Firing trigger '%s' → session '%s'", trigger.name, session_name
    )

    try:
        cfg = load_config()
        template_name = trigger.template or config.default_template
        if not template_name:
            logger.error(
                "Trigger '%s': no template or default_template",
                trigger.name,
            )
            return

        template_cfg = load_template(template_name)
        resolved_tool = template_cfg.tool or cfg.general.default_tool
        tool_cfg = load_tool_config(resolved_tool)

        # Merge MCP servers from template
        mcp_servers = (
            sorted(set(template_cfg.mcp)) if template_cfg.mcp else None
        )

        # Determine working directory
        root = await asyncio.to_thread(git.git_root, ".")
        wt_dir = session_name.replace("/", "-")
        wt_path = f"{root}/.worktrees/{wt_dir}"
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)

        branch_prefix = (
            template_cfg.git.branch_prefix if template_cfg.git else ""
        )
        branch_name = git.infer_branch_name(session_name, branch_prefix)
        await asyncio.to_thread(
            git.worktree_add, root, wt_path, branch=branch_name
        )

        # Build tool command — respects input_mode == "keys" guard
        if not trigger.prompt or tool_cfg.input_mode == "keys":
            tool_command = tool_cfg.command
        else:
            from shoal.core.prompt_delivery import (
                build_tool_command_with_prompt,
            )

            tool_command = build_tool_command_with_prompt(
                tool_cfg, trigger.prompt, session_name
            )

        extra_env = {**trigger.env} if trigger.env else None

        session = await create_session_lifecycle(
            session_name=session_name,
            tool=resolved_tool,
            git_root=root,
            wt_path=wt_path,
            work_dir=wt_path,
            branch_name=branch_name,
            tool_command=tool_command,
            startup_commands=cfg.tmux.startup_commands,
            template_cfg=template_cfg,
            worktree_name=wt_dir,
            mcp_servers=mcp_servers,
            extra_env=extra_env,
            tags=[*trigger.tags, "claw", f"trigger:{trigger.name}"],
        )

        # Send prompt via keys if tool uses keys input mode
        if trigger.prompt and tool_cfg.input_mode == "keys":
            from shoal.services.runtime_provider import provider_for_session

            provider = provider_for_session(session)
            await provider.async_send_input(session, trigger.prompt)

        # Record execution
        db = await get_db()
        execution = TriggerExecution(
            id=execution_id,
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            session_id=session.id,
            session_name=session.name,
            started_at=now.isoformat(),
        )
        await db.save_execution(execution)

        # Update trigger bookkeeping
        trigger.last_fired_at = now.isoformat()
        trigger.fire_count += 1
        if trigger.kind == TriggerKind.timer:
            trigger.enabled = False  # one-shot
        await db.save_trigger(trigger)

        await emit(
            LifecycleEvent.trigger_fired,
            trigger_name=trigger.name,
            session_name=session.name,
            session_id=session.id,
        )

        logger.info(
            "Trigger '%s' fired → session '%s' (id: %s)",
            trigger.name,
            session.name,
            session.id,
        )

    except Exception:
        logger.exception("Failed to fire trigger '%s'", trigger.name)


async def main(config: ClawConfig | None = None) -> None:
    """Entry point for the claw daemon."""
    if config is None:
        from shoal.core.config import load_config

        config = load_config().claw

    daemon = ClawDaemon(config)
    await daemon.run()


def _cli_main() -> None:
    """Console script entry point for ``python -m shoal.services.claw_daemon``."""
    import contextlib

    from shoal.core.db import with_db

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(with_db(main()))


if __name__ == "__main__":
    _cli_main()
