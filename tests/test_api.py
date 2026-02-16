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
            patch("shoal.api.server.tmux.set_environment") as mock_set_env,
            patch("shoal.api.server.tmux.send_keys") as mock_send_keys,
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
        assert "version" in data
        assert data["total"] >= 2


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
