"""FastAPI server tests."""

import pytest
from fastapi.testclient import TestClient

from shoal.api.server import app


@pytest.fixture
def client():
    """Test client for the Shoal API."""
    return TestClient(app)


class TestRoot:
    """Tests for root endpoint."""

    def test_root_returns_service_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "shoal"
        assert "version" in data


class TestHealth:
    """Tests for health endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSessions:
    """Tests for session management endpoints."""

    def test_list_sessions_empty(self, client, mock_dirs):
        response = client.get("/sessions")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_session_not_found(self, client, mock_dirs):
        response = client.get("/sessions/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_session_not_found(self, client, mock_dirs):
        response = client.delete("/sessions/nonexistent")
        assert response.status_code == 404


class TestMcp:
    """Tests for MCP server pool endpoints."""

    def test_list_mcp_empty(self, client, mock_dirs):
        response = client.get("/mcp")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_known_servers(self, client, mock_dirs):
        response = client.get("/mcp/known")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Known servers should include memory, filesystem, github, fetch
        names = [item["name"] for item in data]
        assert "memory" in names
        assert "filesystem" in names

    def test_get_mcp_not_found(self, client, mock_dirs):
        response = client.get("/mcp/nonexistent")
        assert response.status_code == 404

    def test_stop_mcp_not_found(self, client, mock_dirs):
        response = client.delete("/mcp/nonexistent")
        assert response.status_code == 404

    def test_attach_mcp_session_not_found(self, client, mock_dirs):
        response = client.post("/sessions/nonexistent/mcp/memory")
        assert response.status_code == 404

    def test_detach_mcp_session_not_found(self, client, mock_dirs):
        response = client.delete("/sessions/nonexistent/mcp/memory")
        assert response.status_code == 404


class TestWebSocket:
    """Tests for WebSocket endpoint."""

    def test_websocket_connect(self, client):
        with client.websocket_connect("/ws") as ws:
            # Connection should succeed
            assert ws is not None
