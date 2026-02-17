"""Tests for services/status_bar.py."""

import pytest
from shoal.models.state import SessionStatus
from shoal.services.status_bar import generate_status


class TestGenerateStatus:
    @pytest.mark.asyncio
    async def test_empty(self, mock_dirs):
        assert await generate_status() == ""

    @pytest.mark.asyncio
    async def test_with_sessions(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("test-session", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert "#[fg=green]" in result
        assert "1" in result

    @pytest.mark.asyncio
    async def test_stopped_excluded(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.stopped)

        # Stopped sessions don't affect the count of running/idle/waiting/error
        # The result should be empty since no active sessions exist
        assert await generate_status() == ""

    @pytest.mark.asyncio
    async def test_all_same_status(self, mock_dirs):
        """Only one segment should be rendered if all sessions have the same status."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.running)
        s2 = await create_session("s2", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        assert "● 2" in result
        assert "○" not in result
        assert "◉" not in result
        assert "✗" not in result

    @pytest.mark.asyncio
    async def test_large_session_count(self, mock_dirs):
        """Status bar should correctly handle large session counts."""
        from shoal.core.state import create_session, update_session

        # Add 100 running sessions
        for i in range(100):
            s = await create_session(f"s{i}", "claude", "/tmp")
            await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert "● 100" in result

    @pytest.mark.asyncio
    async def test_all_stopped(self, mock_dirs):
        """Status bar should be empty if all sessions are stopped."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        assert await generate_status() == ""

    @pytest.mark.asyncio
    async def test_waiting_style(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.waiting)

        result = await generate_status()
        assert "#[fg=yellow]" in result
        assert "1" in result

    @pytest.mark.asyncio
    async def test_multiple_mixed_statuses(self, mock_dirs):
        """Status bar should correctly count sessions across different states."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("running-one", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.running)

        s2 = await create_session("running-two", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        s3 = await create_session("idle-one", "claude", "/tmp")
        await update_session(s3.id, status=SessionStatus.idle)

        s4 = await create_session("error-one", "claude", "/tmp")
        await update_session(s4.id, status=SessionStatus.error)

        s5 = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s5.id, status=SessionStatus.waiting)

        result = await generate_status()
        # Should have 2 running, 1 idle, 1 waiting, 1 error
        # Unicode icons: ● (running), ○ (idle), ◉ (waiting), ✗ (error)
        assert "#[fg=green]● 2" in result
        assert "#[fg=white]○ 1" in result
        assert "#[fg=yellow]◉ 1" in result
        assert "#[fg=red]✗ 1" in result

    @pytest.mark.asyncio
    async def test_stopped_and_unknown_not_displayed(self, mock_dirs):
        """Stopped and unknown sessions should not appear in the status bar."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        s2 = await create_session("running-one", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        # Should show 1 running (● 1), and stopped/unknown should not contribute
        assert "#[fg=green]● 1" in result
        # Should not show stopped or unknown counts
        assert "stopped" not in result.lower()
        assert "unknown" not in result.lower()
