"""Dreamer service — log tailing and LLM summarization for agent sessions.

The Dreamer watches agent pane output, periodically summarizes activity using
an LLM (gpt-oss-20b by default), and maintains a running narrative of session
progress.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shoal.models.config import DreamerConfig

logger = logging.getLogger("shoal.dreamer")


@dataclass
class DreamerSession:
    """Tracks state for a single dreamer-watched session."""

    session_id: str
    session_name: str
    dreamer_pane_id: str
    tmux_session: str
    config: DreamerConfig
    last_summary_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    accumulated_logs: list[str] = field(default_factory=list)
    summary_history: list[str] = field(default_factory=list)


class DreamerService:
    """Background service that tails agent logs and generates LLM summaries.

    The Dreamer service:
    - Tails the agent pane output at regular intervals
    - Accumulates log lines up to config.log_lines
    - Calls the LLM summarization engine periodically (config.summary_interval_seconds)
    - Stores summaries in memory (future: persist to DB)
    """

    def __init__(self, config: DreamerConfig) -> None:
        self.config: DreamerConfig = config
        self._sessions: dict[str, DreamerSession] = {}
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the dreamer background loop."""
        if self._running:
            logger.warning("Dreamer service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Dreamer service started (model=%s, interval=%ds)",
            self.config.model,
            self.config.summary_interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the dreamer background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Dreamer service stopped")

    async def watch_session(
        self,
        session_id: str,
        session_name: str,
        dreamer_pane_id: str,
        tmux_session: str,
    ) -> None:
        """Register a session for dreamer monitoring.

        Args:
            session_id: Unique session identifier.
            session_name: Human-readable session name.
            dreamer_pane_id: Tmux pane ID for the dreamer pane.
            tmux_session: Tmux session name.
        """
        async with self._lock:
            self._sessions[session_id] = DreamerSession(
                session_id=session_id,
                session_name=session_name,
                dreamer_pane_id=dreamer_pane_id,
                tmux_session=tmux_session,
                config=self.config,
            )
            logger.info("Dreamer watching session %s (%s)", session_id, session_name)

    async def unwatch_session(self, session_id: str) -> None:
        """Stop monitoring a session.

        Args:
            session_id: Session to stop watching.
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Dreamer stopped watching session %s", session_id)

    async def _run_loop(self) -> None:
        """Main dreamer loop — tails logs and generates summaries."""
        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Dreamer poll cycle failed")

            await asyncio.sleep(self.config.summary_interval_seconds / 10)  # Poll at 10x frequency

    async def _poll_cycle(self) -> None:
        """Single poll cycle — tail logs and potentially summarize."""
        async with self._lock:
            sessions = list(self._sessions.values())

        for session in sessions:
            await self._tail_logs(session)

            now = datetime.now(UTC)
            elapsed = (now - session.last_summary_time).total_seconds()
            if elapsed >= self.config.summary_interval_seconds:
                await self._summarize(session)
                session.last_summary_time = now

    async def _tail_logs(self, session: DreamerSession) -> None:
        """Capture recent output from the agent pane.

        Args:
            session: Dreamer session to tail logs for.
        """
        from shoal.core import tmux

        try:
            # Capture the agent pane (first pane in the session, not the dreamer pane)
            agent_pane = await tmux.async_first_pane(session.tmux_session)
            content = await tmux.async_capture_pane(agent_pane, lines=self.config.log_lines)
            lines = content.strip().split("\n") if content.strip() else []

            # Keep only new lines (simple dedup by tracking last N lines)
            session.accumulated_logs.extend(lines)
            # Trim to max log_lines to prevent unbounded growth
            if len(session.accumulated_logs) > self.config.log_lines:
                session.accumulated_logs = session.accumulated_logs[-self.config.log_lines :]
        except Exception as exc:
            logger.warning("Failed to tail logs for session %s: %s", session.session_id, exc)

    async def _summarize(self, session: DreamerSession) -> None:
        """Generate LLM summary of accumulated logs.

        Args:
            session: Dreamer session to summarize.
        """
        if not session.accumulated_logs:
            return

        logs_text = "\n".join(session.accumulated_logs[-self.config.log_lines :])

        try:
            summary = await self._call_llm(session.session_name, logs_text)
            session.summary_history.append(summary)
            logger.info("Dreamer summary for %s: %s", session.session_id, summary[:100])
            session.accumulated_logs.clear()  # Clear after summarizing
        except Exception as exc:
            logger.warning("Failed to summarize session %s: %s", session.session_id, exc)

    async def _call_llm(self, session_name: str, logs: str) -> str:
        """Call the LLM summarization engine.

        Args:
            session_name: Name of the session being summarized.
            logs: Accumulated log text to summarize.

        Returns:
            Generated summary text.

        Raises:
            Exception: If LLM call fails.
        """
        # Use AWS Bedrock or direct API call for gpt-oss-20b
        # This is a placeholder implementation — in production this would
        # integrate with the US Mobile AI Gateway or AWS Bedrock
        prompt = self._build_prompt(session_name, logs)

        try:
            # Attempt to use the internal AI SDK if available
            from shoal.services.ai_client import call_llm  # type: ignore[import-untyped]

            response = await call_llm(
                model=self.config.model,
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
            )
            return str(response)
        except ImportError:
            logger.debug("AI client not available, using fallback summarization")
            return self._fallback_summarize(session_name, logs)
        except Exception as exc:
            logger.warning("LLM call failed for %s: %s", session_name, exc)
            return self._fallback_summarize(session_name, logs)

    def _build_prompt(self, session_name: str, logs: str) -> str:
        """Build the LLM prompt for summarization.

        Args:
            session_name: Name of the session.
            logs: Log content to summarize.

        Returns:
            Formatted prompt string.
        """
        return f"""You are an AI assistant monitoring a coding agent session named "{session_name}".

Below is the recent output from the agent's terminal. Provide a concise 2-3 sentence summary of:
1. What the agent is currently working on
2. Any errors or blockers encountered
3. Progress toward the goal

Agent output:
{logs}

Summary:"""

    def _fallback_summarize(self, session_name: str, logs: str) -> str:
        """Fallback summarization when LLM is unavailable.

        Args:
            session_name: Name of the session.
            logs: Log content.

        Returns:
            Simple fallback summary.
        """
        lines = logs.strip().split("\n")
        line_count = len(lines)
        last_line = lines[-1][:80] if lines else ""
        return f"[Dreamer fallback] Session {session_name}: {line_count} lines. Last: {last_line}"

    def get_summary(self, session_id: str) -> str | None:
        """Get the latest summary for a session.

        Args:
            session_id: Session to get summary for.

        Returns:
            Latest summary text, or None if not found.
        """
        session = self._sessions.get(session_id)
        if session and session.summary_history:
            return session.summary_history[-1]
        return None

    def get_all_summaries(self, session_id: str) -> list[str]:
        """Get all summaries for a session.

        Args:
            session_id: Session to get summaries for.

        Returns:
            List of all summary texts.
        """
        session = self._sessions.get(session_id)
        if session:
            return session.summary_history.copy()
        return []


# Global singleton instance
_dreamer_instance: DreamerService | None = None


def get_dreamer() -> DreamerService | None:
    """Get the global dreamer service instance.

    Returns:
        DreamerService instance, or None if not initialized.
    """
    return _dreamer_instance


def init_dreamer(config: DreamerConfig) -> DreamerService:
    """Initialize the global dreamer service.

    Args:
        config: Dreamer configuration.

    Returns:
        Initialized DreamerService instance.
    """
    global _dreamer_instance
    _dreamer_instance = DreamerService(config)
    return _dreamer_instance
