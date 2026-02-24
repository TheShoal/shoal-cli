"""Async programmatic supervision loop for Shoal robo sessions.

Monitors sessions for 'waiting' status and auto-approves safe prompts
or escalates ambiguous/timed-out cases.  Follows the same daemon pattern
as ``services/watcher.py`` (PID file, signal handling, exponential backoff).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import UTC, datetime

from shoal.core import tmux
from shoal.core.config import ensure_dirs, load_tool_config, runtime_dir
from shoal.core.db import get_db
from shoal.core.journal import append_entry
from shoal.core.state import list_sessions
from shoal.models.config import RoboProfileConfig, ToolConfig
from shoal.models.state import SessionState, SessionStatus

logger = logging.getLogger("shoal.robo_supervisor")

_MAX_BACKOFF = 300.0  # cap for exponential backoff on consecutive errors


class RoboSupervisor:
    """Async supervision loop that monitors sessions and acts on waiting agents.

    Polls at ``profile.monitoring.poll_interval`` seconds.  For each session
    in ``waiting`` status:

    1. Capture pane content and check if the prompt is safe to auto-approve.
    2. If safe **and** ``profile.auto_approve`` is enabled → send Enter.
    3. If the session has been waiting longer than ``waiting_timeout`` → escalate.
    4. Otherwise, wait for the next poll cycle.

    Every decision is logged to the session journal with ``source="robo"``.
    """

    def __init__(self, profile: RoboProfileConfig) -> None:
        self.profile = profile
        self._running = True
        self._consecutive_errors = 0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the supervision loop with signal handling and PID file."""
        ensure_dirs()

        log_file = runtime_dir() / "logs" / f"robo-{self.profile.name}.log"
        handler = logging.FileHandler(str(log_file))
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(name)s: %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        shoal_logger = logging.getLogger("shoal")
        shoal_logger.setLevel(logging.INFO)
        shoal_logger.addHandler(handler)

        pid_file = runtime_dir() / f"robo-{self.profile.name}.pid"
        pid_file.write_text(str(os.getpid()))

        logger.info(
            "Robo supervisor started (pid: %d, profile: %s, auto_approve: %s)",
            os.getpid(),
            self.profile.name,
            self.profile.auto_approve,
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop)

        poll_interval = float(self.profile.monitoring.poll_interval)

        try:
            while self._running:
                try:
                    await self._poll()
                    self._consecutive_errors = 0
                except Exception:
                    self._consecutive_errors += 1
                    logger.exception("Poll cycle failed, continuing")

                if self._consecutive_errors > 0:
                    delay = min(
                        poll_interval * (2 ** (self._consecutive_errors - 1)),
                        _MAX_BACKOFF,
                    )
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(poll_interval)
        finally:
            pid_file.unlink(missing_ok=True)
            logger.info("Robo supervisor stopping")

    def _stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll(self) -> None:
        """Single poll iteration: check all sessions, handle waiting ones."""
        sessions = await list_sessions()
        for session in sessions:
            if session.status == SessionStatus.waiting:
                await self._handle_waiting(session)

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    async def _handle_waiting(self, session: SessionState) -> None:
        """Decide what to do with a waiting session: approve, escalate, or wait."""
        # Resolve pane target
        pane_title = f"shoal:{session.id}"
        pane_target = await tmux.async_preferred_pane(session.tmux_session, title=pane_title)

        # Capture current pane content
        pane_content = await tmux.async_capture_pane(pane_target, lines=20)
        if not pane_content:
            return

        # Load tool config for pattern matching
        try:
            tool_config = await asyncio.to_thread(load_tool_config, session.tool)
        except FileNotFoundError:
            logger.warning(
                "[%s] Tool config missing for '%s', skipping",
                session.id,
                session.tool,
            )
            return

        # Check for auto-approve
        if self._safe_to_approve(pane_content, tool_config):
            await self._auto_approve(session, pane_target)
            return

        # Check for timeout escalation
        waiting_duration = await self._waiting_duration_seconds(session.id)
        timeout = float(self.profile.monitoring.waiting_timeout)

        if waiting_duration is not None and waiting_duration > timeout:
            await self._escalate(
                session,
                f"Waiting timeout exceeded ({waiting_duration:.0f}s > {timeout:.0f}s)",
            )
            return

        # Under timeout, not safe to approve — do nothing this cycle
        logger.debug(
            "[%s] Waiting (%.0fs / %.0fs), not safe to approve",
            session.id,
            waiting_duration or 0,
            timeout,
        )

    def _safe_to_approve(self, pane_content: str, tool_config: ToolConfig) -> bool:
        """Check if pane content matches known-safe waiting patterns.

        Returns True only when ALL of these are true:
        - ``profile.auto_approve`` is enabled
        - Content matches a waiting pattern (permission prompt, Yes/No, etc.)
        - Content does NOT match an error pattern
        """
        if not self.profile.auto_approve:
            return False

        # Never approve if there's an error on screen
        for pattern in tool_config.detection._compiled_error:
            if pattern.search(pane_content):
                return False

        # Must match at least one waiting pattern
        for pattern in tool_config.detection._compiled_waiting:
            if pattern.search(pane_content):
                return True

        return False

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _auto_approve(self, session: SessionState, pane_target: str) -> None:
        """Send Enter to approve a waiting session and journal the decision."""
        logger.info("[%s] Auto-approving session '%s'", session.id, session.name)
        await tmux.async_send_keys(pane_target, "", enter=True)
        await self._journal_decision(
            session, "approved", "Auto-approved: safe waiting pattern detected"
        )

    async def _escalate(self, session: SessionState, reason: str) -> None:
        """Escalate a waiting session and journal the decision."""
        logger.warning("[%s] Escalating session '%s': %s", session.id, session.name, reason)
        await self._journal_decision(session, "escalated", reason)

    async def _journal_decision(self, session: SessionState, decision: str, detail: str) -> None:
        """Append a robo decision entry to the session journal."""
        content = f"**Robo decision**: {decision}\n\n{detail}"
        await asyncio.to_thread(append_entry, session.id, content, "robo")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _waiting_duration_seconds(self, session_id: str) -> float | None:
        """How long has this session been in 'waiting' status?

        Queries the most recent status_transition where to_status='waiting'.
        Returns None if no transition record is found.
        """
        db = await get_db()
        transitions = await db.get_status_transitions(session_id, limit=10)
        for t in transitions:
            if t["to_status"] == "waiting":
                entered = datetime.fromisoformat(t["timestamp"])
                now = datetime.now(UTC)
                return (now - entered).total_seconds()
        return None


def main() -> None:
    """Entry point for running as a daemon.

    Accepts an optional profile name as ``sys.argv[1]`` (defaults to "default").
    Called by the ``shoal-robo-supervisor`` console script entry point and by
    ``python -m shoal.services.robo_supervisor <profile>``.
    """
    import contextlib
    import sys

    from shoal.core.config import load_robo_profile
    from shoal.core.db import with_db

    profile_name = sys.argv[1] if len(sys.argv) > 1 else "default"
    profile = load_robo_profile(profile_name)
    supervisor = RoboSupervisor(profile)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(with_db(supervisor.run()))


if __name__ == "__main__":
    main()
