"""Asyncio background daemon that polls tmux panes for status detection."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import UTC, datetime

from shoal.core import tmux
from shoal.core.config import ensure_dirs, load_tool_config, runtime_dir
from shoal.core.detection import detect_status
from shoal.core.notify import notify
from shoal.core.state import get_session, list_sessions, update_session
from shoal.models.state import SessionStatus

logger = logging.getLogger("shoal.watcher")


class Watcher:
    def __init__(self, poll_interval: float = 5.0) -> None:
        self.poll_interval = poll_interval
        self._running = True

    async def run(self) -> None:
        """Main loop with signal handling + PID file."""
        ensure_dirs()

        log_file = runtime_dir() / "logs" / "watcher.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        pid_file = runtime_dir() / "watcher.pid"
        pid_file.write_text(str(os.getpid()))

        logger.info("Watcher started (pid: %d)", os.getpid())

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop)

        try:
            while self._running:
                await self._poll_cycle()
                await asyncio.sleep(self.poll_interval)
        finally:
            pid_file.unlink(missing_ok=True)
            logger.info("Watcher stopping")

    def _stop(self) -> None:
        self._running = False

    async def _poll_cycle(self) -> None:
        """Iterate sessions, capture panes, detect status, update state, notify."""
        ids = await list_sessions()
        for sid in ids:
            session = await get_session(sid)
            if not session or session.status.value == "stopped":
                continue

            # 1. Check if tmux session still exists
            if not tmux.has_session(session.tmux_session):
                if session.status.value != "stopped":
                    await update_session(
                        sid, status=SessionStatus.stopped, last_activity=datetime.now(UTC)
                    )
                    logger.info("Session %s: marked stopped (tmux gone)", sid)
                continue

            # 2. Verify PID if we have one
            current_pane_pid = tmux.pane_pid(session.tmux_session)
            if session.pid and session.pid != current_pane_pid:
                # PID changed (e.g. process restarted in same pane)
                logger.info("Session %s: PID changed %s → %s", sid, session.pid, current_pane_pid)
                await update_session(sid, pid=current_pane_pid)
            elif not session.pid and current_pane_pid:
                # PID found for first time
                await update_session(sid, pid=current_pane_pid)

            # 3. Capture pane content
            pane_content = tmux.capture_pane(session.tmux_session, lines=20)
            if not pane_content:
                continue

            # Detect status
            try:
                tool_config = load_tool_config(session.tool)
            except FileNotFoundError:
                continue

            new_status = detect_status(pane_content, tool_config)

            # Update if changed
            if new_status.value != session.status.value:
                await update_session(
                    sid,
                    status=new_status,
                    last_activity=datetime.now(UTC),
                )
                logger.info("Session %s: %s → %s", sid, session.status.value, new_status.value)

                if new_status.value == "waiting":
                    notify(
                        "Shoal",
                        f"Session '{session.name}' is waiting for input",
                    )


def main() -> None:
    """Entry point for running as a module."""
    import contextlib

    watcher = Watcher()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(watcher.run())


if __name__ == "__main__":
    main()
