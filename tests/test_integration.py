"""Integration tests for Shoal session lifecycle."""

import pytest
from shoal.core.state import create_session, get_session, delete_session, update_session
from shoal.models.state import SessionStatus
import asyncio
from unittest.mock import patch, MagicMock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_lifecycle_integration(mock_dirs):
    """
    Test the full lifecycle of a session:
    create -> update -> kill -> cleanup
    """
    # 1. Create session
    repo_path = "/tmp/repo"
    session_name = "integration-test"

    with (
        patch("shoal.core.tmux.has_session", return_value=False),
        patch("shoal.core.tmux.new_session"),
        patch("shoal.core.tmux.run_command"),
    ):
        s = await create_session(session_name, "claude", repo_path)
        assert s.name == session_name
        assert s.status == SessionStatus.idle

        # 2. Update status
        updated = await update_session(s.id, status=SessionStatus.running)
        assert updated.status == SessionStatus.running

        # 3. Verify in DB
        fetched = await get_session(s.id)
        assert fetched.id == s.id
        assert fetched.status == SessionStatus.running

        # 4. Delete session
        success = await delete_session(s.id)
        assert success is True

        # 5. Verify gone
        gone = await get_session(s.id)
        assert gone is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fork_workflow_integration(mock_dirs):
    """Test forking a session inherits properties and creates new state."""
    # This exercises the core logic used by the fork CLI command
    from shoal.cli.session import _fork_impl

    # Create source session
    s_source = await create_session("source", "claude", "/tmp/repo", branch="main")

    with (
        patch("shoal.core.tmux.has_session", return_value=False),
        patch("shoal.core.tmux.new_session"),
        patch("shoal.core.tmux.run_command"),
        patch("shoal.core.tmux.set_environment"),
        patch("shoal.core.git.worktree_add"),
        patch("shoal.core.git.current_branch", return_value="feat/fork"),
        patch("shoal.cli.session.console.print"),
    ):
        # We use _fork_impl to test the application logic
        await _fork_impl("source", "forked", no_worktree=True)

        # Verify forked session exists
        from shoal.core.state import find_by_name

        forked_id = await find_by_name("forked")
        assert forked_id is not None

        s_forked = await get_session(forked_id)
        assert s_forked.tool == s_source.tool
        assert s_forked.path == s_source.path
        assert s_forked.name == "forked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_session_status_aggregation(mock_dirs):
    """Test aggregating status across multiple sessions."""
    await create_session("s1", "claude", "/tmp")
    s2 = await create_session("s2", "claude", "/tmp")
    await update_session(s2.id, status=SessionStatus.running)
    s3 = await create_session("s3", "claude", "/tmp")
    await update_session(s3.id, status=SessionStatus.error)

    from shoal.services.status_bar import generate_status

    with patch("shoal.core.tmux.has_session", return_value=True):
        status_line = await generate_status()

        from shoal.core.theme import Symbols

        # Should show 1 running, 1 idle, 1 error, waiting and inactive as placeholders
        assert "● 1" in status_line  # running
        assert "○ 1" in status_line  # idle
        assert "✗ 1" in status_line  # error
        # waiting and inactive should show as placeholders
        assert status_line.count(Symbols.BULLET_OFF) >= 2
