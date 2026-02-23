"""Asyncio background daemon that polls tmux panes for status detection."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from datetime import UTC, datetime

from shoal.core import tmux
from shoal.core.config import ensure_dirs, load_tool_config, runtime_dir
from shoal.core.detection import detect_status
from shoal.core.notify import notify
from shoal.core.state import list_sessions, update_session
from shoal.models.state import SessionStatus

logger = logging.getLogger("shoal.watcher")

_MAX_BACKOFF = 300.0  # seconds — cap for exponential backoff on consecutive errors


def _find_session_tool_pane(
    panes: list[dict[str, str]],
    pane_title: str,
) -> str | None:
    """Pick the pane tagged for this session.

    We intentionally key on pane title (shoal:<session_id>) because
    pane_current_command is not stable when users split panes, switch focus,
    or when tools spawn subprocesses.
    """
    for pane in panes:
        if pane.get("title") == pane_title:
            return pane.get("id")
    return None


class Watcher:
    def __init__(self, poll_interval: float = 5.0) -> None:
        self.poll_interval = poll_interval
        self._running = True
        self._consecutive_errors = 0

    async def run(self) -> None:
        """Main loop with signal handling + PID file."""
        ensure_dirs()

        log_file = runtime_dir() / "logs" / "watcher.log"
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

        pid_file = runtime_dir() / "watcher.pid"
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

            # 1. Check if tmux session still exists
            if not await tmux.async_has_session(session.tmux_session):
                if session.status.value != "stopped":
                    await update_session(
                        session.id, status=SessionStatus.stopped, last_activity=datetime.now(UTC)
                    )
                    logger.info("Session %s: marked stopped (tmux gone)", session.id)
                continue

            # 2. Resolve the pane to track by session tool command
            try:
                tool_config = load_tool_config(session.tool)
            except FileNotFoundError:
                logger.warning(
                    "[%s] Tool config missing for '%s', skipping",
                    session.id,
                    session.tool,
                )
                continue

            pane_title = f"shoal:{session.id}"
            panes = await tmux.async_list_panes(session.tmux_session)
            pane_target = _find_session_tool_pane(panes, pane_title)
            if not pane_target:
                logger.debug("Session %s: no pane tagged '%s'", session.id, pane_title)
                continue

            # 3. Verify PID if we have one
            current_pane_pid = await tmux.async_pane_pid(pane_target)
            if session.pid and session.pid != current_pane_pid:
                # PID changed (e.g. process restarted in same pane)
                logger.info(
                    "Session %s: PID changed %s → %s", session.id, session.pid, current_pane_pid
                )
                await update_session(session.id, pid=current_pane_pid)
            elif not session.pid and current_pane_pid:
                # PID found for first time
                await update_session(session.id, pid=current_pane_pid)

            # 4. Capture pane content
            pane_content = await tmux.async_capture_pane(pane_target, lines=20)
            if not pane_content:
                continue

            # Detect status
            new_status = detect_status(pane_content, tool_config)

            # Update if changed
            if new_status.value != session.status.value:
                await update_session(
                    session.id,
                    status=new_status,
                    last_activity=datetime.now(UTC),
                )
                logger.info(
                    "Session %s: %s → %s", session.id, session.status.value, new_status.value
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
