"""Tests for the async database layer (v0.4.0)."""

import pytest
import aiosqlite
from pathlib import Path
from shoal.core.db import ShoalDB
from shoal.models.state import SessionState, SessionStatus
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
