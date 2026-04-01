"""Agent coordinator service for multi-agent orchestration.

The coordinator polls agent sessions for completion, manages squash-merge
of worktree commits, and coordinates handoffs between multiple agents.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shoal.models.config.workspace import CoordinatorConfig

from shoal.core import git
from shoal.core.state import get_session
from shoal.models.state import SessionStatus

logger = logging.getLogger("shoal.coordinator")


@dataclass
class CoordinatorSession:
    """Tracks state for a coordinator-managed session."""

    session_id: str
    session_name: str
    worktree_path: str
    branch_name: str
    parent_branch: str
    config: CoordinatorConfig
    last_poll_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_status: SessionStatus = SessionStatus.waiting
    squash_pending: bool = False


class CoordinatorService:
    """Coordinates multiple agent sessions with polling and squash-merge.

    The coordinator watches agent sessions for completion signals,
    then performs squash-merge of the worktree commits back to the
    parent branch.
    """

    def __init__(self, config: CoordinatorConfig) -> None:
        """Initialize the coordinator service.

        Args:
            config: Coordinator configuration with polling and merge settings.
        """
        self.config = config
        self._sessions: dict[str, CoordinatorSession] = {}
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the coordinator polling loop."""
        if self._running:
            logger.warning("Coordinator already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Coordinator service started (poll_interval=%ds)", self.config.poll_interval_seconds
        )

    async def stop(self) -> None:
        """Stop the coordinator polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Coordinator service stopped")

    async def register_session(
        self,
        session_id: str,
        session_name: str,
        worktree_path: str,
        branch_name: str,
        parent_branch: str,
    ) -> None:
        """Register a session for coordinator management.

        Args:
            session_id: Unique session identifier.
            session_name: Human-readable session name.
            worktree_path: Path to the git worktree.
            branch_name: Name of the feature branch.
            parent_branch: Name of the parent branch to merge into.
        """
        async with self._lock:
            self._sessions[session_id] = CoordinatorSession(
                session_id=session_id,
                session_name=session_name,
                worktree_path=worktree_path,
                branch_name=branch_name,
                parent_branch=parent_branch,
                config=self.config,
            )
            logger.info("Registered session %s for coordination", session_name)

    async def unregister_session(self, session_id: str) -> None:
        """Unregister a session from coordinator management.

        Args:
            session_id: Unique session identifier.
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Unregistered session %s from coordination", session_id)

    async def _poll_loop(self) -> None:
        """Main polling loop for checking session status."""
        while self._running:
            try:
                await self._poll_sessions()
            except Exception as exc:
                logger.exception("Poll loop error: %s", exc)

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _poll_sessions(self) -> None:
        """Poll all registered sessions for status changes."""
        async with self._lock:
            sessions_snapshot = list(self._sessions.values())

        for coord_session in sessions_snapshot:
            try:
                await self._check_session_status(coord_session)
            except Exception as exc:
                logger.warning(
                    "Failed to check session %s status: %s",
                    coord_session.session_name,
                    exc,
                )

    async def _check_session_status(self, coord_session: CoordinatorSession) -> None:
        """Check and update status for a single session.

        Args:
            coord_session: Coordinator session to check.
        """
        session = await get_session(coord_session.session_id)
        if not session:
            logger.warning("Session %s not found, skipping", coord_session.session_name)
            return

        current_status = session.status
        previous_status = coord_session.last_status

        # Detect transition to terminal state (error)
        if current_status == SessionStatus.error and previous_status != SessionStatus.error:
            logger.info(
                "Session %s reached terminal state: %s",
                coord_session.session_name,
                current_status.value,
            )
            coord_session.last_status = current_status

            if self.config.squash_merge:
                coord_session.squash_pending = True
                await self._perform_squash_merge(coord_session)

    async def _perform_squash_merge(self, coord_session: CoordinatorSession) -> None:
        """Perform squash merge of session worktree to parent branch.

        Args:
            coord_session: Coordinator session with worktree to merge.
        """
        logger.info(
            "Starting squash merge for session %s (%s -> %s)",
            coord_session.session_name,
            coord_session.branch_name,
            coord_session.parent_branch,
        )

        try:
            worktree_path = Path(coord_session.worktree_path)

            # Ensure we're in the worktree directory
            await asyncio.to_thread(self._checkout_branch, worktree_path, coord_session.branch_name)

            # Count commits to squash
            commit_count = await asyncio.to_thread(
                self._count_commits_ahead,
                worktree_path,
                coord_session.parent_branch,
            )

            if commit_count == 0:
                logger.info("No commits to squash for session %s", coord_session.session_name)
                coord_session.squash_pending = False
                return

            logger.info("Squashing %d commits from %s", commit_count, coord_session.branch_name)

            # Perform soft reset to parent branch
            await asyncio.to_thread(
                self._soft_reset_to_parent,
                worktree_path,
                coord_session.parent_branch,
            )

            # Create squashed commit
            await asyncio.to_thread(
                self._create_squash_commit,
                worktree_path,
                coord_session.session_name,
            )

            # Merge back to parent branch
            await asyncio.to_thread(
                self._merge_to_parent,
                worktree_path,
                coord_session.parent_branch,
                coord_session.branch_name,
            )

            logger.info(
                "Successfully squashed and merged session %s to %s",
                coord_session.session_name,
                coord_session.parent_branch,
            )

        except Exception as exc:
            logger.exception(
                "Squash merge failed for session %s: %s", coord_session.session_name, exc
            )
            raise

        finally:
            coord_session.squash_pending = False

    def _checkout_branch(self, worktree_path: Path, branch_name: str) -> None:
        """Checkout a branch in the worktree.

        Args:
            worktree_path: Path to the worktree.
            branch_name: Name of the branch to checkout.
        """
        git._run(["checkout", branch_name], cwd=str(worktree_path))

    def _count_commits_ahead(self, worktree_path: Path, parent_branch: str) -> int:
        """Count commits ahead of parent branch.

        Args:
            worktree_path: Path to the worktree.
            parent_branch: Name of the parent branch.

        Returns:
            Number of commits ahead of parent.
        """
        result = git._run(["rev-list", "--count", f"HEAD..{parent_branch}"], cwd=str(worktree_path))
        return int(result.stdout.strip())

    def _soft_reset_to_parent(self, worktree_path: Path, parent_branch: str) -> None:
        """Soft reset to parent branch, preserving changes.

        Args:
            worktree_path: Path to the worktree.
            parent_branch: Name of the parent branch.
        """
        git._run(["reset", "--soft", parent_branch], cwd=str(worktree_path))

    def _create_squash_commit(self, worktree_path: Path, session_name: str) -> None:
        """Create a squashed commit from all changes.

        Args:
            worktree_path: Path to the worktree.
            session_name: Name of the session (used in commit message).
        """
        git._run(["add", "-A"], cwd=str(worktree_path))
        git._run(
            ["commit", "-m", f"Squashed changes from session: {session_name}"],
            cwd=str(worktree_path),
        )

    def _merge_to_parent(
        self,
        worktree_path: Path,
        parent_branch: str,
        feature_branch: str,
    ) -> None:
        """Merge feature branch to parent branch.

        Args:
            worktree_path: Path to the worktree.
            parent_branch: Name of the parent branch.
            feature_branch: Name of the feature branch to merge.
        """
        git._run(["checkout", parent_branch], cwd=str(worktree_path))
        git._run(["merge", "--no-ff", feature_branch], cwd=str(worktree_path))
