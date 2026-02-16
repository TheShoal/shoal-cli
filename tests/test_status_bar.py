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
        # The result should show all counts as 0
        result = await generate_status()
        assert "1" not in result

    @pytest.mark.asyncio
    async def test_waiting_style(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.waiting)

        result = await generate_status()
        assert "#[fg=yellow]" in result
        assert "1" in result
