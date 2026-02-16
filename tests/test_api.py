"""FastAPI server tests (Async)."""

import pytest

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
