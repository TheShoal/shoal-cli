"""Asyncio background daemon that polls tmux panes for status detection."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from datetime import UTC, datetime

from shoal.core.config import ensure_dirs, load_tool_config, state_dir
from shoal.core.detection import detect_status
from shoal.core.notify import notify
from shoal.core.state import list_sessions, update_session
from shoal.models.state import SessionStatus, StatusSource
from shoal.services.runtime_provider import provider_for_session

logger = logging.getLogger("shoal.watcher")

_MAX_BACKOFF = 300.0  # seconds — cap for exponential backoff on consecutive errors
HEARTBEAT_STALE_SECONDS = 60.0  # Consider hook-instrumented sessions stale after 60s


class Watcher:
    def __init__(self, poll_interval: float = 5.0) -> None:
        self.poll_interval = poll_interval
        self._running = True
        self._consecutive_errors = 0

    async def run(self) -> None:
        """Main loop with signal handling + PID file."""
        ensure_dirs()

        log_file = state_dir() / "logs" / "watcher.log"
        handler = logging.FileHandler(str(log_file))
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(name)s [sid=%(session_id)s rid=%(request_id)s]: %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )

        from shoal.core.context import ContextFilter

        handler.addFilter(ContextFilter())
        shoal_logger = logging.getLogger("shoal")
        shoal_logger.setLevel(logging.INFO)
        shoal_logger.addHandler(handler)

        pid_file = state_dir() / "watcher.pid"
        pid_file.write_text(str(os.getpid()))

        logger.info("Watcher started (pid: %d)", os.getpid())

        # Boot-time reconciliation: mark stale DB rows as stopped
        from shoal.services.lifecycle import reconcile_sessions

        try:
            reconciled = await reconcile_sessions()
            if reconciled:
                logger.info("Reconciled %d stale session(s) at startup", len(reconciled))
                for sid, name, action in reconciled:
                    logger.info("  [%s] %s: %s", sid, name, action)
        except Exception:
            logger.exception("Boot-time reconciliation failed, continuing")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop)

        try:
            while self._running:
                try:
                    await self._poll_cycle()
                    self._consecutive_errors = 0
                except (subprocess.CalledProcessError, TimeoutError) as exc:
                    self._consecutive_errors += 1
                    logger.warning("Poll cycle subprocess error: %s", exc)
                except Exception:
                    self._consecutive_errors += 1
                    logger.exception("Poll cycle failed, continuing")

                if self._consecutive_errors > 0:
                    delay = min(
                        self.poll_interval * (2 ** (self._consecutive_errors - 1)),
                        _MAX_BACKOFF,
                    )
                    logger.debug(
                        "Backoff: sleeping %.1fs (consecutive_errors=%d)",
                        delay,
                        self._consecutive_errors,
                    )
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(self.poll_interval)
        finally:
            pid_file.unlink(missing_ok=True)
            logger.info("Watcher stopping")

    def _stop(self) -> None:
        self._running = False

    async def _poll_cycle(self) -> None:
        """Iterate sessions, capture panes, detect status, update state, notify."""
        sessions = await list_sessions()
        for session in sessions:
            if session.status.value == "stopped":
                continue

            # Skip polling if session has a recent heartbeat
            if session.status_source == StatusSource.hook and session.last_heartbeat:
                elapsed = (datetime.now(UTC) - session.last_heartbeat).total_seconds()
                if elapsed < HEARTBEAT_STALE_SECONDS:
                    logger.debug(
                        "Skipping %s: hook heartbeat %.0fs ago",
                        session.name,
                        elapsed,
                    )
                    continue
                logger.warning(
                    "Hook heartbeat stale for %s (%.0fs), falling back to watcher",
                    session.name,
                    elapsed,
                )
                await update_session(session.id, status_source=StatusSource.watcher)

            provider = provider_for_session(session)

            # 1. Check runtime liveness + capture provider-owned observation
            try:
                tool_config = load_tool_config(session.tool)
            except FileNotFoundError:
                logger.warning(
                    "[%s] Tool config missing for '%s', skipping",
                    session.id,
                    session.tool,
                )
                continue

            observation = await provider.async_observe(session, tool_config, lines=20)
            if not observation.alive:
                if session.status.value != "stopped":
                    await update_session(
                        session.id, status=SessionStatus.stopped, last_activity=datetime.now(UTC)
                    )
                    logger.info("Session %s: marked stopped (runtime gone)", session.id)
                continue

            runtime_updates: dict[str, object] = {}
            if observation.runtime != session.runtime:
                runtime_updates["runtime"] = observation.runtime

            if session.pid and observation.pid and session.pid != observation.pid:
                logger.info(
                    "Session %s: PID changed %s → %s", session.id, session.pid, observation.pid
                )
                runtime_updates["pid"] = observation.pid
            elif not session.pid and observation.pid:
                runtime_updates["pid"] = observation.pid

            if runtime_updates:
                await update_session(session.id, **runtime_updates)

            if not observation.output:
                continue

            # 2. Detect status from runtime output
            new_status = detect_status(observation.output, tool_config)

            # 3. Update if changed
            if new_status.value != session.status.value:
                old_status = session.status
                update_fields: dict[str, object] = {
                    "status": new_status,
                    "last_activity": datetime.now(UTC),
                }
                if "runtime" in runtime_updates:
                    update_fields["runtime"] = runtime_updates["runtime"]
                if "pid" in runtime_updates:
                    update_fields["pid"] = runtime_updates["pid"]

                await update_session(session.id, **update_fields)
                logger.info("Session %s: %s → %s", session.id, old_status.value, new_status.value)

                from shoal.models.state import LifecycleEvent
                from shoal.services.lifecycle import emit

                await emit(
                    LifecycleEvent.status_changed,
                    session=session,
                    old_status=old_status,
                    new_status=new_status,
                )

                # Emit command_failed when transitioning into error status.
                # This is the canonical signal for proactive assistance.
                if new_status.value == "error":
                    await emit(
                        LifecycleEvent.command_failed,
                        session=session,
                        pane_snapshot=observation.output,
                        old_status=old_status,
                    )

                if new_status.value == "waiting":
                    notify(
                        "Shoal",
                        f"Session '{session.name}' is waiting for input",
                    )


def main() -> None:
    """Entry point for running as a module."""
    import contextlib

    from shoal.core.db import with_db

    watcher = Watcher()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(with_db(watcher.run()))


if __name__ == "__main__":
    main()
