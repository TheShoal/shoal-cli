"""FastAPI server tests (Async)."""

from unittest.mock import patch

import pytest

from shoal.core.state import create_session


@pytest.mark.asyncio
class TestRoot:
    """Tests for root endpoint."""

    async def test_root_returns_service_info(self, async_client):
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "shoal"
        assert "version" in data


@pytest.mark.asyncio
class TestHealth:
    """Tests for health endpoint."""

    async def test_health_returns_ok(self, async_client):
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
class TestSessions:
    """Tests for session management endpoints."""

    async def test_list_sessions_empty(self, async_client):
        response = await async_client.get("/sessions")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_session_not_found(self, async_client):
        response = await async_client.get("/sessions/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_delete_session_not_found(self, async_client):
        response = await async_client.delete("/sessions/nonexistent")
        assert response.status_code == 404

    @pytest.mark.skip(reason="Complex integration test - needs full mocking of tmux/git chain")
    async def test_create_session(self, async_client, tmp_path):
        """Test POST /sessions creates a new session."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.tmux.new_session") as mock_new_session,
            patch("shoal.api.server.tmux.set_environment"),
            patch("shoal.api.server.tmux.send_keys"),
        ):
            response = await async_client.post(
                "/sessions",
                json={
                    "path": str(test_dir),
                    "tool": "claude",
                    "name": "test-session",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-session"
            assert data["tool"] == "claude"
            assert "id" in data

            # Verify tmux session was created
            assert mock_new_session.called

    async def test_send_keys(self, async_client):
        """Test POST /sessions/{id}/send sends keys to tmux."""
        # Create a session first
        s = await create_session("test-send", "claude", "/tmp/test")

        with patch("shoal.api.server.tmux.send_keys") as mock_send_keys:
            response = await async_client.post(
                f"/sessions/{s.id}/send",
                json={"keys": "echo hello"},
            )
            assert response.status_code == 200
            assert response.json()["message"] == "Keys sent"

            # Verify send_keys was called
            mock_send_keys.assert_called_once_with(s.tmux_session, "echo hello")

    async def test_send_keys_session_not_found(self, async_client):
        """Test POST /sessions/{id}/send with non-existent session."""
        response = await async_client.post(
            "/sessions/nonexistent/send",
            json={"keys": "echo hello"},
        )
        assert response.status_code == 404

    async def test_get_status(self, async_client):
        """Test GET /status returns aggregate status."""
        # Create a few sessions
        await create_session("s1", "claude", "/tmp/test")
        await create_session("s2", "opencode", "/tmp/test")

        response = await async_client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "running" in data
        assert "unknown" in data
        assert "version" in data
        assert data["total"] >= 2

    async def test_get_status_with_unknown(self, async_client):
        """Test GET /status correctly counts unknown sessions."""
        from shoal.core.state import update_session
        from shoal.models.state import SessionStatus

        # Create a session and mark it as unknown
        s = await create_session("unknown-test", "claude", "/tmp/test")
        await update_session(s.id, status=SessionStatus.unknown)

        response = await async_client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["unknown"] >= 1
        assert data["total"] >= 1

    async def test_create_session_invalid_name(self, async_client, tmp_path):
        """Test POST /sessions rejects invalid session names via Pydantic validation."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
        ):
            response = await async_client.post(
                "/sessions",
                json={
                    "path": str(test_dir),
                    "tool": "claude",
                    "name": "bad;name",  # Invalid: contains semicolon
                },
            )
            assert response.status_code == 422  # Pydantic validation error
            assert "detail" in response.json()

    async def test_rename_session_success(self, async_client):
        """Test PUT /sessions/{id}/rename successfully renames a session."""
        s = await create_session("old-name", "claude", "/tmp/test")

        with patch("shoal.api.server.tmux.has_session", return_value=False):
            response = await async_client.put(
                f"/sessions/{s.id}/rename",
                json={"name": "new-name"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new-name"
        assert data["id"] == s.id

    async def test_rename_session_not_found(self, async_client):
        """Test PUT /sessions/{id}/rename returns 404 for non-existent session."""
        response = await async_client.put(
            "/sessions/nonexistent/rename",
            json={"name": "new-name"},
        )
        assert response.status_code == 404

    async def test_rename_session_invalid_name(self, async_client):
        """Test PUT /sessions/{id}/rename rejects invalid names via Pydantic validation."""
        s = await create_session("valid-name", "claude", "/tmp/test")

        response = await async_client.put(
            f"/sessions/{s.id}/rename",
            json={"name": "bad;name"},  # Invalid: contains semicolon
        )
        assert response.status_code == 422  # Pydantic validation error

    async def test_rename_session_duplicate_name(self, async_client):
        """Test PUT /sessions/{id}/rename rejects duplicate names."""
        await create_session("first", "claude", "/tmp/test")
        s2 = await create_session("second", "claude", "/tmp/test")

        with patch("shoal.api.server.tmux.has_session", return_value=False):
            response = await async_client.put(
                f"/sessions/{s2.id}/rename",
                json={"name": "first"},  # Name already exists
            )

        assert response.status_code == 409  # Conflict
        assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
class TestMcp:
    """Tests for MCP server pool endpoints."""

    async def test_list_mcp_empty(self, async_client):
        response = await async_client.get("/mcp")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_known_servers(self, async_client):
        response = await async_client.get("/mcp/known")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [item["name"] for item in data]
        assert "memory" in names
        assert "filesystem" in names

    async def test_get_mcp_not_found(self, async_client):
        response = await async_client.get("/mcp/nonexistent")
        assert response.status_code == 404

    async def test_stop_mcp_not_found(self, async_client):
        response = await async_client.delete("/mcp/nonexistent")
        assert response.status_code == 404

    async def test_attach_mcp_session_not_found(self, async_client):
        response = await async_client.post("/sessions/nonexistent/mcp/memory")
        assert response.status_code == 404

    async def test_detach_mcp_session_not_found(self, async_client):
        response = await async_client.delete("/sessions/nonexistent/mcp/memory")
        assert response.status_code == 404

    async def test_list_mcp_avoids_n_plus_one(self, async_client, mock_dirs, tmp_path):
        """Test GET /mcp pre-fetches sessions to avoid N+1 queries."""
        from shoal.core.state import list_sessions as real_list_sessions

        # Create a few sessions
        await create_session("s1", "claude", "/tmp/test")
        await create_session("s2", "claude", "/tmp/test")

        # Mock list_sessions to count calls
        call_count = 0

        async def mock_list_sessions():
            nonlocal call_count
            call_count += 1
            return await real_list_sessions()

        # Create fake socket files
        socket_dir = tmp_path / "mcp-pool" / "sockets"
        socket_dir.mkdir(parents=True, exist_ok=True)
        (socket_dir / "server1.sock").touch()
        (socket_dir / "server2.sock").touch()
        (socket_dir / "server3.sock").touch()

        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.list_sessions", side_effect=mock_list_sessions),
            patch("shoal.api.server.read_pid", return_value=None),
        ):
            # Mock mcp_socket to return path with our test directory
            mock_socket.return_value = socket_dir / "dummy.sock"

            response = await async_client.get("/mcp")
            assert response.status_code == 200

            # list_sessions should be called exactly ONCE, not once per socket
            assert call_count == 1
