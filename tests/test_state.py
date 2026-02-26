"""Tests for core/state.py — session CRUD (Async)."""

import pytest

from shoal.core.state import (
    add_mcp_to_session,
    create_session,
    delete_session,
    find_by_name,
    generate_id,
    get_session,
    list_sessions,
    remove_mcp_from_session,
    resolve_session,
    touch_session,
    update_session,
    validate_session_name,
)
from shoal.models.state import SessionStatus


class TestGenerateId:
    def test_length(self):
        assert len(generate_id()) == 8
        assert len(generate_id(12)) == 12

    def test_charset(self):
        for _ in range(20):
            sid = generate_id()
            assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in sid)

    def test_uniqueness(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100


class TestValidateSessionName:
    def test_valid_names(self):
        """Test that valid names pass validation."""
        valid_names = [
            "my-session",
            "project/worktree",
            "My.Project-v2",
            "test_session",
            "a1b2c3",
            "very-long-but-valid-name-with-many-parts",
        ]
        for name in valid_names:
            assert validate_session_name(name) is None

    def test_empty_name(self):
        """Test that empty name fails."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_session_name("")

    def test_too_long(self):
        """Test that names over 100 chars fail."""
        long_name = "a" * 101
        with pytest.raises(ValueError, match="too long"):
            validate_session_name(long_name)

    def test_shell_metacharacters(self):
        """Test that shell metacharacters are blocked."""
        invalid_names = [
            "test$(whoami)",
            "bad;name",
            "test|pipe",
            "back`tick`",
            "test&background",
            "test>redirect",
            "test<input",
            "test'quote",
            'test"doublequote',
            "test\\backslash",
            "test*glob",
            "test?wildcard",
            "test[bracket]",
            "test{brace}",
            "test(paren)",
            "test\nnewline",
            "test\ttab",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="must contain only"):
                validate_session_name(name)

    def test_reserved_names(self):
        """Test that reserved names are blocked."""
        with pytest.raises(ValueError, match="Reserved name"):
            validate_session_name(".")
        with pytest.raises(ValueError, match="Reserved name"):
            validate_session_name("..")

    def test_control_characters(self):
        """Test that control characters are blocked."""
        with pytest.raises(ValueError, match="must contain only"):
            validate_session_name("test\x00null")
        with pytest.raises(ValueError, match="must contain only"):
            validate_session_name("test\x1besc")


@pytest.mark.asyncio
class TestSessionCRUD:
    async def test_create_and_get(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp/repo", "/tmp/wt", "feat/test")
        assert session.name == "test"
        assert session.tool == "claude"
        assert session.status == SessionStatus.idle
        assert session.tmux_session.startswith("_")

        loaded = await get_session(session.id)
        assert loaded is not None
        assert loaded.name == "test"
        assert loaded.id == session.id

    async def test_create_with_invalid_name(self, mock_dirs):
        """Test that create_session validates the name."""
        with pytest.raises(ValueError, match="must contain only"):
            await create_session("bad;name", "claude", "/tmp/repo")

    async def test_get_missing(self, mock_dirs):
        assert await get_session("nonexistent") is None

    async def test_update(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp/repo")
        updated = await update_session(session.id, status=SessionStatus.running, pid=1234)
        assert updated is not None
        assert updated.status == SessionStatus.running
        assert updated.pid == 1234

        # Verify persisted
        loaded = await get_session(session.id)
        assert loaded is not None
        assert loaded.status == SessionStatus.running

    async def test_update_with_invalid_name(self, mock_dirs):
        """Test that update_session validates the name field."""
        session = await create_session("test", "claude", "/tmp/repo")
        with pytest.raises(ValueError, match="must contain only"):
            await update_session(session.id, name="bad;name")

    async def test_update_missing(self, mock_dirs):
        assert await update_session("nonexistent", status="running") is None

    async def test_delete(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp/repo")
        assert await delete_session(session.id) is True
        assert await get_session(session.id) is None
        assert await delete_session(session.id) is False

    async def test_list_sessions(self, mock_dirs):
        s1 = await create_session("a", "claude", "/tmp")
        s2 = await create_session("b", "opencode", "/tmp")
        sessions = await list_sessions()
        session_ids = [s.id for s in sessions]
        assert s1.id in session_ids
        assert s2.id in session_ids

    async def test_find_by_name(self, mock_dirs):
        session = await create_session("unique-name", "claude", "/tmp")
        assert await find_by_name("unique-name") == session.id
        assert await find_by_name("nonexistent") is None

    async def test_touch(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp")
        original_time = session.last_activity
        await touch_session(session.id)
        loaded = await get_session(session.id)
        assert loaded is not None
        assert loaded.last_activity >= original_time


@pytest.mark.asyncio
class TestMCPTracking:
    async def test_add_and_remove(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp")
        await add_mcp_to_session(session.id, "memory")
        loaded = await get_session(session.id)
        assert loaded is not None
        assert "memory" in loaded.mcp_servers

        await add_mcp_to_session(session.id, "memory")  # duplicate
        loaded = await get_session(session.id)
        assert loaded is not None
        assert loaded.mcp_servers.count("memory") == 1

        await add_mcp_to_session(session.id, "filesystem")
        loaded = await get_session(session.id)
        assert loaded is not None
        assert "filesystem" in loaded.mcp_servers

        await remove_mcp_from_session(session.id, "memory")
        loaded = await get_session(session.id)
        assert loaded is not None
        assert "memory" not in loaded.mcp_servers
        assert "filesystem" in loaded.mcp_servers


@pytest.mark.asyncio
class TestResolveSession:
    async def test_resolve_by_id(self, mock_dirs):
        session = await create_session("test", "claude", "/tmp")
        assert await resolve_session(session.id) == session.id

    async def test_resolve_by_name(self, mock_dirs):
        session = await create_session("my-session", "claude", "/tmp")
        assert await resolve_session("my-session") == session.id

    async def test_resolve_missing(self, mock_dirs):
        assert await resolve_session("nonexistent") is None
