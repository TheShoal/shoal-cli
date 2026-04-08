"""Integration tests for heartbeat push observation flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shoal.core.state import create_session, update_session
from shoal.models.state import SessionStatus, StatusSource


@pytest.mark.asyncio
class TestHeartbeatEndpoint:
    """Tests for POST /sessions/{session_ref}/heartbeat."""

    async def test_heartbeat_updates_status_and_source(self, async_client, mock_dirs):
        """Heartbeat should update status and set status_source to hook."""
        # Create a test session
        session = await create_session(
            name="test-hb-1",
            tool="omp",
            git_root="/tmp",
        )

        # Push heartbeat
        resp = await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={"status": "waiting", "summary": "Task completed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status_source"] == "hook"
        assert data["status"] == "waiting"

        # Verify session state changed
        from shoal.core.state import get_session

        updated = await get_session(session.id)
        assert updated is not None
        assert updated.status == SessionStatus.waiting
        assert updated.status_source == StatusSource.hook
        assert updated.last_heartbeat is not None

    async def test_heartbeat_resolves_session_by_id(self, async_client, mock_dirs):
        """Heartbeat should work with session ID, not just name."""
        session = await create_session(
            name="test-hb-2",
            tool="omp",
            git_root="/tmp",
        )

        resp = await async_client.post(
            f"/sessions/{session.id}/heartbeat",
            json={"status": "running", "summary": "Working on it"},
        )
        assert resp.status_code == 200
        assert resp.json()["status_source"] == "hook"

    async def test_heartbeat_404_for_unknown_session(self, async_client, mock_dirs):
        """Heartbeat should return 404 for non-existent session."""
        resp = await async_client.post(
            "/sessions/nonexistent/heartbeat",
            json={"status": "waiting", "summary": "Test"},
        )
        assert resp.status_code == 404

    async def test_heartbeat_invalid_status(self, async_client, mock_dirs):
        """Heartbeat should reject invalid status values."""
        session = await create_session(
            name="test-hb-3",
            tool="omp",
            git_root="/tmp",
        )

        resp = await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={"status": "flying", "summary": "Invalid"},
        )
        assert resp.status_code == 422

    async def test_heartbeat_with_optional_fields(self, async_client, mock_dirs):
        """Heartbeat should accept all optional fields."""
        session = await create_session(
            name="test-hb-4",
            tool="omp",
            git_root="/tmp",
        )

        resp = await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={
                "status": "running",
                "summary": "Calling tool",
                "turn_number": 5,
                "tool_name": "read_file",
                "tool_result": "ok",
                "metadata": {"key": "val"},
            },
        )
        assert resp.status_code == 200

    async def test_heartbeat_writes_journal_entry(self, async_client, mock_dirs):
        """Heartbeat with summary should append a journal entry."""
        session = await create_session(
            name="test-hb-5",
            tool="omp",
            git_root="/tmp",
        )

        await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={"status": "waiting", "summary": "Turn done"},
        )

        from shoal.core.journal import read_journal

        entries = read_journal(session.id, limit=5)
        assert any("[heartbeat] Turn done" in e.content for e in entries)

    async def test_heartbeat_no_journal_without_summary(self, async_client, mock_dirs):
        """Heartbeat without summary should NOT append a journal entry."""
        session = await create_session(
            name="test-hb-6",
            tool="omp",
            git_root="/tmp",
        )

        await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={"status": "waiting"},
        )

        from shoal.core.journal import read_journal

        entries = read_journal(session.id, limit=5)
        assert not any("[heartbeat]" in e.content for e in entries)

    async def test_session_response_includes_status_source(self, async_client, mock_dirs):
        """GET /sessions should include status_source and last_heartbeat."""
        session = await create_session(
            name="test-hb-7",
            tool="omp",
            git_root="/tmp",
        )

        # Default is watcher
        resp = await async_client.get(f"/sessions/{session.id}")
        assert resp.status_code == 200
        assert resp.json()["status_source"] == "watcher"
        assert resp.json()["last_heartbeat"] is None

        # After heartbeat, should be hook
        await async_client.post(
            f"/sessions/{session.name}/heartbeat",
            json={"status": "waiting", "summary": "Test"},
        )

        resp = await async_client.get(f"/sessions/{session.id}")
        assert resp.json()["status_source"] == "hook"
        assert resp.json()["last_heartbeat"] is not None


@pytest.mark.asyncio
class TestWatcherSkipLogic:
    """Tests for Watcher skip behavior with hook-instrumented sessions."""

    async def test_status_source_defaults_to_watcher(self, mock_dirs):
        """New sessions should have status_source=watcher by default."""
        session = await create_session(
            name="test-watcher-default",
            tool="omp",
            git_root="/tmp",
        )
        assert session.status_source == StatusSource.watcher
        assert session.last_heartbeat is None

    async def test_heartbeat_sets_status_source_to_hook(self, mock_dirs):
        """After heartbeat, status_source should be hook."""
        session = await create_session(
            name="test-hook-source",
            tool="omp",
            git_root="/tmp",
        )

        now = datetime.now(UTC)
        updated = await update_session(
            session.id,
            status=SessionStatus.waiting,
            status_source=StatusSource.hook,
            last_heartbeat=now,
        )
        assert updated is not None
        assert updated.status_source == StatusSource.hook
        assert updated.last_heartbeat is not None

    async def test_stale_heartbeat_falls_back_to_watcher(self, mock_dirs):
        """Session with stale heartbeat should be set back to watcher."""
        session = await create_session(
            name="test-stale-hb",
            tool="omp",
            git_root="/tmp",
        )

        # Set a heartbeat that's 120s ago (stale)
        stale_time = datetime.now(UTC) - timedelta(seconds=120)
        await update_session(
            session.id,
            status=SessionStatus.waiting,
            status_source=StatusSource.hook,
            last_heartbeat=stale_time,
        )

        # Simulate what the watcher does: check staleness
        from shoal.core.state import get_session

        s = await get_session(session.id)
        assert s is not None
        assert s.status_source == StatusSource.hook

        elapsed = (datetime.now(UTC) - s.last_heartbeat).total_seconds()
        assert elapsed > 60.0  # Stale

        # Watcher would switch back to watcher mode
        await update_session(s.id, status_source=StatusSource.watcher)
        s = await get_session(session.id)
        assert s.status_source == StatusSource.watcher
