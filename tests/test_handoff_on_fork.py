"""Tests for auto-loading parent handoff artifacts when forking a session."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from shoal.core.journal import (
    HandoffArtifact,
    JournalEntry,
    append_entry,
    handoff_artifact_path,
    read_journal,
    write_handoff_artifact,
)
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState
from shoal.services.lifecycle import fork_session_lifecycle


@pytest.fixture()
def journals_dir(tmp_path: Path) -> Path:
    """Create a temporary journals directory and patch data_dir."""
    jdir = tmp_path / "journals"
    jdir.mkdir()
    with patch("shoal.core.journal.data_dir", return_value=tmp_path):
        yield jdir


@pytest.fixture()
def parent_session() -> SessionState:
    """Create a parent session for testing."""
    return SessionState(
        id="parent-id",
        name="parent-session",
        tool="claude",
        path="/tmp/repo",
        worktree="parent-wt",
        branch="parent-branch",
        runtime=TmuxRuntimeState(session_name="shoal_parent-session"),
        status=SessionStatus.running,
    )


@pytest.fixture()
def parent_handoff() -> HandoffArtifact:
    """Create a sample parent handoff artifact."""
    return HandoffArtifact(
        session_name="parent-session",
        tool="claude",
        branch="parent-branch",
        status="running",
        urgency_label="running",
        time_in_status="10m",
        last_active="2026-04-09 12:00 UTC",
        recent_entries=[
            JournalEntry(
                timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC),
                source="agent",
                content="Implemented feature X",
            )
        ],
        transition_summary=["2026-04-09 11:50  idle → running"],
        suggested_next="Continue work on feature X",
        worktree="parent-wt",
        git_diff_summary="3 files changed, 42 insertions(+), 7 deletions(-)",
        commit_count=2,
    )


class TestHandoffOnFork:
    """Test handoff inheritance when forking sessions."""

    @pytest.mark.asyncio()
    async def test_fork_loads_existing_handoff(
        self,
        journals_dir: Path,
        parent_session: SessionState,
        parent_handoff: HandoffArtifact,
    ) -> None:
        """Fork with existing handoff artifact loads it into child journal."""
        # Write parent handoff
        write_handoff_artifact("parent-id", parent_handoff)

        child_session = SessionState(
            id="child-id",
            name="child-session",
            tool="claude",
            path="/tmp/repo",
            worktree="child-wt",
            branch="child-branch",
            runtime=TmuxRuntimeState(session_name="shoal_child-session"),
            status=SessionStatus.idle,
            parent_id="parent-id",
            inherited_context="parent-session",
        )

        async def mock_get_session(session_id: str) -> SessionState | None:
            if session_id == "parent-id":
                return parent_session
            if session_id == "child-id":
                return child_session
            return None

        # Mock dependencies
        with (
            patch(
                "shoal.services.lifecycle.get_session",
                new_callable=AsyncMock,
                side_effect=mock_get_session,
            ),
            patch(
                "shoal.services.lifecycle.create_session",
                new_callable=AsyncMock,
                return_value=child_session,
            ),
            patch("shoal.services.lifecycle.tmux.async_new_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_first_pane", new_callable=AsyncMock, return_value="pane-id"),
            patch("shoal.services.lifecycle.tmux.async_set_environment", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_set_pane_title", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_pane_pid", new_callable=AsyncMock, return_value=12345),
            patch("shoal.services.lifecycle.tmux.async_pane_coordinates", new_callable=AsyncMock, return_value=("$1", "@1")),
            patch("shoal.services.lifecycle.update_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle._run_default_startup_commands_async", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.emit", new_callable=AsyncMock),
        ):
            result = await fork_session_lifecycle(
                session_name="child-session",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="parent-branch",
                wt_path="/tmp/repo/.worktrees/child-wt",
                work_dir="/tmp/repo/.worktrees/child-wt",
                new_branch="child-branch",
                tool_command="claude",
                startup_commands=[],
                parent_id="parent-id",
            )

        # Verify child session was created with inherited context
        assert result.inherited_context == "parent-session"

        # Verify handoff was loaded into child journal
        entries = read_journal("child-id")
        assert len(entries) == 1
        assert entries[0].source == "inherited"
        assert "parent-session" in entries[0].content
        assert "Implemented feature X" in entries[0].content

    @pytest.mark.asyncio()
    async def test_fork_generates_handoff_if_missing(
        self,
        journals_dir: Path,
        parent_session: SessionState,
    ) -> None:
        """Fork without handoff generates one first, then loads."""
        # Add some parent journal entries
        append_entry("parent-id", "Parent work in progress", source="agent")

        child_session = SessionState(
            id="child-id-2",
            name="child-session-2",
            tool="claude",
            path="/tmp/repo",
            worktree="child-wt-2",
            branch="child-branch-2",
            runtime=TmuxRuntimeState(session_name="shoal_child-session-2"),
            status=SessionStatus.idle,
            parent_id="parent-id",
            inherited_context="parent-session",
        )

        async def mock_get_session(session_id: str) -> SessionState | None:
            if session_id == "parent-id":
                return parent_session
            if session_id == "child-id-2":
                return child_session
            return None

        mock_db = AsyncMock()
        mock_db.get_status_transitions = AsyncMock(return_value=[])

        with (
            patch(
                "shoal.services.lifecycle.get_session",
                new_callable=AsyncMock,
                side_effect=mock_get_session,
            ),
            patch(
                "shoal.services.lifecycle.create_session",
                new_callable=AsyncMock,
                return_value=child_session,
            ),
            patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=mock_db),
            patch("shoal.services.lifecycle.tmux.async_new_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_first_pane", new_callable=AsyncMock, return_value="pane-id"),
            patch("shoal.services.lifecycle.tmux.async_set_environment", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_set_pane_title", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_pane_pid", new_callable=AsyncMock, return_value=12345),
            patch("shoal.services.lifecycle.tmux.async_pane_coordinates", new_callable=AsyncMock, return_value=("$1", "@1")),
            patch("shoal.services.lifecycle.update_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle._run_default_startup_commands_async", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.emit", new_callable=AsyncMock),
        ):
            await fork_session_lifecycle(
                session_name="child-session-2",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="parent-branch",
                wt_path="/tmp/repo/.worktrees/child-wt-2",
                work_dir="/tmp/repo/.worktrees/child-wt-2",
                new_branch="child-branch-2",
                tool_command="claude",
                startup_commands=[],
                parent_id="parent-id",
            )

        # Verify handoff was generated
        handoff_path = handoff_artifact_path("parent-id")
        assert handoff_path.exists()

        # Verify handoff was loaded into child journal
        entries = read_journal("child-id-2")
        assert len(entries) == 1
        assert entries[0].source == "inherited"

    @pytest.mark.asyncio()
    async def test_fork_without_parent_has_no_inherited_context(
        self,
        journals_dir: Path,
    ) -> None:
        """Fork without parent_id has no inherited_context."""
        child_session = SessionState(
            id="child-no-parent",
            name="child-no-parent",
            tool="claude",
            path="/tmp/repo",
            worktree="child-wt",
            branch="child-branch",
            runtime=TmuxRuntimeState(session_name="shoal_child-no-parent"),
            status=SessionStatus.idle,
        )

        async def mock_get_session(session_id: str) -> SessionState | None:
            if session_id == "child-no-parent":
                return child_session
            return None

        with (
            patch(
                "shoal.services.lifecycle.get_session",
                new_callable=AsyncMock,
                side_effect=mock_get_session,
            ),
            patch(
                "shoal.services.lifecycle.create_session",
                new_callable=AsyncMock,
                return_value=child_session,
            ),
            patch("shoal.services.lifecycle.tmux.async_new_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_first_pane", new_callable=AsyncMock, return_value="pane-id"),
            patch("shoal.services.lifecycle.tmux.async_set_environment", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_set_pane_title", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_pane_pid", new_callable=AsyncMock, return_value=12345),
            patch("shoal.services.lifecycle.tmux.async_pane_coordinates", new_callable=AsyncMock, return_value=("$1", "@1")),
            patch("shoal.services.lifecycle.update_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle._run_default_startup_commands_async", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.emit", new_callable=AsyncMock),
        ):
            result = await fork_session_lifecycle(
                session_name="child-no-parent",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="/tmp/repo/.worktrees/child-wt",
                work_dir="/tmp/repo/.worktrees/child-wt",
                new_branch="child-branch",
                tool_command="claude",
                startup_commands=[],
                parent_id="",  # No parent
            )

        # Verify no inherited context
        assert result.inherited_context is None

        # Verify no journal entries were created
        entries = read_journal("child-no-parent")
        assert len(entries) == 0

    @pytest.mark.asyncio()
    async def test_fork_of_fork_propagates_context(
        self,
        journals_dir: Path,
        parent_handoff: HandoffArtifact,
    ) -> None:
        """Fork of a fork propagates context (grandparent -> parent -> child)."""
        # Create grandparent session and handoff
        grandparent_session = SessionState(
            id="grandparent-id",
            name="grandparent-session",
            tool="claude",
            path="/tmp/repo",
            runtime=TmuxRuntimeState(session_name="shoal_grandparent-session"),
            status=SessionStatus.running,
        )
        write_handoff_artifact("grandparent-id", parent_handoff)

        # Create parent session with inherited context
        parent_session = SessionState(
            id="parent-id",
            name="parent-session",
            tool="claude",
            path="/tmp/repo",
            runtime=TmuxRuntimeState(session_name="shoal_parent-session"),
            status=SessionStatus.running,
            parent_id="grandparent-id",
            inherited_context="grandparent-session",
        )

        # Add parent journal entry
        append_entry("parent-id", "Parent work", source="agent")

        # Write parent handoff
        from dataclasses import replace
        parent_handoff_updated = replace(
            parent_handoff,
            session_name="parent-session"
        )
        write_handoff_artifact("parent-id", parent_handoff_updated)

        child_session = SessionState(
            id="child-id",
            name="child-session",
            tool="claude",
            path="/tmp/repo",
            runtime=TmuxRuntimeState(session_name="shoal_child-session"),
            status=SessionStatus.idle,
            parent_id="parent-id",
            inherited_context="parent-session",
        )

        mock_db = AsyncMock()
        mock_db.get_status_transitions = AsyncMock(return_value=[])

        async def mock_get_session(session_id: str) -> SessionState | None:
            if session_id == "parent-id":
                return parent_session
            if session_id == "grandparent-id":
                return grandparent_session
            if session_id == "child-id":
                return child_session
            return None

        with (
            patch(
                "shoal.services.lifecycle.get_session",
                new_callable=AsyncMock,
                side_effect=mock_get_session,
            ),
            patch(
                "shoal.services.lifecycle.create_session",
                new_callable=AsyncMock,
                return_value=child_session,
            ),
            patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=mock_db),
            patch("shoal.services.lifecycle.tmux.async_new_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_first_pane", new_callable=AsyncMock, return_value="pane-id"),
            patch("shoal.services.lifecycle.tmux.async_set_environment", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_set_pane_title", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_pane_pid", new_callable=AsyncMock, return_value=12345),
            patch("shoal.services.lifecycle.tmux.async_pane_coordinates", new_callable=AsyncMock, return_value=("$1", "@1")),
            patch("shoal.services.lifecycle.update_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle._run_default_startup_commands_async", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.emit", new_callable=AsyncMock),
        ):
            result = await fork_session_lifecycle(
                session_name="child-session",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="parent-branch",
                wt_path="/tmp/repo/.worktrees/child-wt",
                work_dir="/tmp/repo/.worktrees/child-wt",
                new_branch="child-branch",
                tool_command="claude",
                startup_commands=[],
                parent_id="parent-id",
            )

        # Verify child has inherited context from parent
        assert result.inherited_context == "parent-session"

        # Verify parent's handoff was loaded into child journal
        entries = read_journal("child-id")
        assert len(entries) == 1
        assert entries[0].source == "inherited"
        assert "parent-session" in entries[0].content

    @pytest.mark.asyncio()
    async def test_inherited_context_field_set_correctly(
        self,
        journals_dir: Path,
        parent_session: SessionState,
        parent_handoff: HandoffArtifact,
    ) -> None:
        """inherited_context field is set correctly on child SessionState."""
        write_handoff_artifact("parent-id", parent_handoff)

        created_session = SessionState(
            id="child-id",
            name="child-session",
            tool="claude",
            path="/tmp/repo",
            runtime=TmuxRuntimeState(session_name="shoal_child-session"),
            status=SessionStatus.idle,
            parent_id="parent-id",
            inherited_context="parent-session",
        )

        async def mock_get_session(session_id: str) -> SessionState | None:
            if session_id == "parent-id":
                return parent_session
            if session_id == "child-id":
                return created_session
            return None

        with (
            patch(
                "shoal.services.lifecycle.get_session",
                new_callable=AsyncMock,
                side_effect=mock_get_session,
            ),
            patch(
                "shoal.services.lifecycle.create_session",
                new_callable=AsyncMock,
                return_value=created_session,
            ) as mock_create,
            patch("shoal.services.lifecycle.tmux.async_new_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_first_pane", new_callable=AsyncMock, return_value="pane-id"),
            patch("shoal.services.lifecycle.tmux.async_set_environment", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_set_pane_title", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.tmux.async_pane_pid", new_callable=AsyncMock, return_value=12345),
            patch("shoal.services.lifecycle.tmux.async_pane_coordinates", new_callable=AsyncMock, return_value=("$1", "@1")),
            patch("shoal.services.lifecycle.update_session", new_callable=AsyncMock),
            patch("shoal.services.lifecycle._run_default_startup_commands_async", new_callable=AsyncMock),
            patch("shoal.services.lifecycle.emit", new_callable=AsyncMock),
        ):
            result = await fork_session_lifecycle(
                session_name="child-session",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="parent-branch",
                wt_path="/tmp/repo/.worktrees/child-wt",
                work_dir="/tmp/repo/.worktrees/child-wt",
                new_branch="child-branch",
                tool_command="claude",
                startup_commands=[],
                parent_id="parent-id",
            )

        # Verify create_session was called with inherited_context
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["inherited_context"] == "parent-session"

        # Verify result has inherited_context
        assert result.inherited_context == "parent-session"
