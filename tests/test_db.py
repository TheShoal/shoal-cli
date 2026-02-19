"""Tests for the async database layer (v0.4.0)."""

import pytest
import aiosqlite
from pathlib import Path
from shoal.core.db import ShoalDB
from shoal.models.state import SessionState, SessionStatus, RoboState
from datetime import datetime, UTC


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "shoal.db"
    db = ShoalDB(db_path)
    await db.connect()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_db_initialization(tmp_path):
    db_path = tmp_path / "shoal.db"
    db = ShoalDB(db_path)
    await db.connect()
    assert db_path.exists()

    # Check if table exists
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None

    await db.close()


@pytest.mark.asyncio
async def test_create_and_get_session(db):
    session = SessionState(
        id="test-id",
        name="test-session",
        tool="claude",
        path="/tmp/repo",
        tmux_session="shoal_test",
        status=SessionStatus.idle,
    )

    await db.save_session(session)
    loaded = await db.get_session("test-id")

    assert loaded is not None
    assert loaded.id == "test-id"
    assert loaded.name == "test-session"
    assert loaded.status == SessionStatus.idle


@pytest.mark.asyncio
async def test_list_sessions(db):
    s1 = SessionState(id="id1", name="n1", tool="t", path="p", tmux_session="ts1")
    s2 = SessionState(id="id2", name="n2", tool="t", path="p", tmux_session="ts2")

    await db.save_session(s1)
    await db.save_session(s2)

    sessions = await db.list_sessions()
    assert len(sessions) == 2
    assert "id1" in [s.id for s in sessions]
    assert "id2" in [s.id for s in sessions]


@pytest.mark.asyncio
async def test_update_session(db):
    s1 = SessionState(id="id1", name="n1", tool="t", path="p", tmux_session="ts1")
    await db.save_session(s1)

    await db.update_session("id1", status=SessionStatus.running, pid=1234)

    updated = await db.get_session("id1")
    assert updated.status == SessionStatus.running
    assert updated.pid == 1234


@pytest.mark.asyncio
async def test_delete_session(db):
    s1 = SessionState(id="id1", name="n1", tool="t", path="p", tmux_session="ts1")
    await db.save_session(s1)

    await db.delete_session("id1")
    assert await db.get_session("id1") is None


@pytest.mark.asyncio
async def test_save_and_get_robo(db):
    """Test saving and retrieving a robo state."""
    robo = RoboState(
        name="test-robo",
        tool="opencode",
        tmux_session="__test",
        status=SessionStatus.running,
    )

    await db.save_robo(robo)
    loaded = await db.get_robo("test-robo")

    assert loaded is not None
    assert loaded.name == "test-robo"
    assert loaded.tool == "opencode"
    assert loaded.tmux_session == "__test"
    assert loaded.status == SessionStatus.running


@pytest.mark.asyncio
async def test_get_robo_not_found(db):
    """Test getting a non-existent robo returns None."""
    result = await db.get_robo("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_robos(db):
    """Test listing all robo states."""
    r1 = RoboState(
        name="robo1",
        tool="claude",
        tmux_session="__1",
        status=SessionStatus.running,
    )
    r2 = RoboState(
        name="robo2",
        tool="opencode",
        tmux_session="__2",
        status=SessionStatus.stopped,
    )

    await db.save_robo(r1)
    await db.save_robo(r2)

    robos = await db.list_robos()
    assert len(robos) == 2
    assert "robo1" in [r.name for r in robos]
    assert "robo2" in [r.name for r in robos]


@pytest.mark.asyncio
async def test_update_robo(db):
    """Test updating a robo state."""
    robo = RoboState(
        name="test-robo",
        tool="claude",
        tmux_session="__test",
        status=SessionStatus.running,
    )
    await db.save_robo(robo)

    # Update the robo
    robo.status = SessionStatus.stopped
    await db.save_robo(robo)

    updated = await db.get_robo("test-robo")
    assert updated.status == SessionStatus.stopped


@pytest.mark.asyncio
async def test_list_robos_empty(db):
    """Test listing robos when none exist."""
    robos = await db.list_robos()
    assert robos == []
