"""Tests for services/status_bar.py."""

import pytest

from shoal.models.state import SessionStatus
from shoal.services.status_bar import generate_status


class TestGenerateStatus:
    @pytest.mark.asyncio
    async def test_empty(self, mock_dirs):
        result = await generate_status()
        assert result == {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    @pytest.mark.asyncio
    async def test_with_sessions(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("test-session", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 1
        assert result["idle"] == 0

    @pytest.mark.asyncio
    async def test_stopped_contributes_to_inactive(self, mock_dirs):
        """Stopped sessions count toward the inactive category."""
        from shoal.core.state import create_session, update_session

        s = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result["inactive"] == 1

    @pytest.mark.asyncio
    async def test_all_same_status(self, mock_dirs):
        """Multiple sessions with the same status are counted correctly."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.running)
        s2 = await create_session("s2", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 2
        assert result["idle"] == 0
        assert result["waiting"] == 0
        assert result["error"] == 0
        assert result["inactive"] == 0

    @pytest.mark.asyncio
    async def test_large_session_count(self, mock_dirs):
        """Status bar should correctly handle large session counts."""
        from shoal.core.state import create_session, update_session

        for i in range(100):
            s = await create_session(f"s{i}", "claude", "/tmp")
            await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 100

    @pytest.mark.asyncio
    async def test_all_stopped(self, mock_dirs):
        """All stopped sessions count as inactive."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result["inactive"] == 1
        assert result["running"] == 0

    @pytest.mark.asyncio
    async def test_waiting_counted(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.waiting)

        result = await generate_status()
        assert result["waiting"] == 1

    @pytest.mark.asyncio
    async def test_multiple_mixed_statuses(self, mock_dirs):
        """Status counts are correct across different states."""
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

        s6 = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s6.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result == {"running": 2, "idle": 1, "waiting": 1, "error": 1, "inactive": 1}

    @pytest.mark.asyncio
    async def test_stopped_shows_as_inactive(self, mock_dirs):
        """Stopped sessions count toward inactive, not their own category."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        s2 = await create_session("running-one", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 1
        assert result["inactive"] == 1
        assert result["idle"] == 0
