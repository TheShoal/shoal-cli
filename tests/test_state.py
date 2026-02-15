"""Tests for core/state.py — session CRUD."""

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


class TestSessionCRUD:
    def test_create_and_get(self, mock_dirs):
        session = create_session("test", "claude", "/tmp/repo", "/tmp/wt", "feat/test")
        assert session.name == "test"
        assert session.tool == "claude"
        assert session.status == SessionStatus.idle
        assert session.tmux_session.startswith("shoal_")

        loaded = get_session(session.id)
        assert loaded is not None
        assert loaded.name == "test"
        assert loaded.id == session.id

    def test_get_missing(self, mock_dirs):
        assert get_session("nonexistent") is None

    def test_update(self, mock_dirs):
        session = create_session("test", "claude", "/tmp/repo")
        updated = update_session(session.id, status=SessionStatus.running, pid=1234)
        assert updated is not None
        assert updated.status == SessionStatus.running
        assert updated.pid == 1234

        # Verify persisted
        loaded = get_session(session.id)
        assert loaded is not None
        assert loaded.status == SessionStatus.running

    def test_update_missing(self, mock_dirs):
        assert update_session("nonexistent", status="running") is None

    def test_delete(self, mock_dirs):
        session = create_session("test", "claude", "/tmp/repo")
        assert delete_session(session.id) is True
        assert get_session(session.id) is None
        assert delete_session(session.id) is False

    def test_list_sessions(self, mock_dirs):
        s1 = create_session("a", "claude", "/tmp")
        s2 = create_session("b", "opencode", "/tmp")
        sessions = list_sessions()
        assert s1.id in sessions
        assert s2.id in sessions

    def test_find_by_name(self, mock_dirs):
        session = create_session("unique-name", "claude", "/tmp")
        assert find_by_name("unique-name") == session.id
        assert find_by_name("nonexistent") is None

    def test_touch(self, mock_dirs):
        session = create_session("test", "claude", "/tmp")
        original_time = session.last_activity
        touch_session(session.id)
        loaded = get_session(session.id)
        assert loaded is not None
        assert loaded.last_activity >= original_time


class TestMCPTracking:
    def test_add_and_remove(self, mock_dirs):
        session = create_session("test", "claude", "/tmp")
        add_mcp_to_session(session.id, "memory")
        loaded = get_session(session.id)
        assert loaded is not None
        assert "memory" in loaded.mcp_servers

        add_mcp_to_session(session.id, "memory")  # duplicate
        loaded = get_session(session.id)
        assert loaded is not None
        assert loaded.mcp_servers.count("memory") == 1

        add_mcp_to_session(session.id, "filesystem")
        loaded = get_session(session.id)
        assert loaded is not None
        assert "filesystem" in loaded.mcp_servers

        remove_mcp_from_session(session.id, "memory")
        loaded = get_session(session.id)
        assert loaded is not None
        assert "memory" not in loaded.mcp_servers
        assert "filesystem" in loaded.mcp_servers


class TestResolveSession:
    def test_resolve_by_id(self, mock_dirs):
        session = create_session("test", "claude", "/tmp")
        assert resolve_session(session.id) == session.id

    def test_resolve_by_name(self, mock_dirs):
        session = create_session("my-session", "claude", "/tmp")
        assert resolve_session("my-session") == session.id

    def test_resolve_missing(self, mock_dirs):
        assert resolve_session("nonexistent") is None
