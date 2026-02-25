"""FastAPI server tests (Async)."""

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

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
class TestCors:
    """Tests for CORS middleware configuration."""

    async def test_cors_allows_origin(self, async_client):
        response = await async_client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "*"

    async def test_cors_no_credentials(self, async_client):
        response = await async_client.get("/", headers={"Origin": "http://localhost:3000"})
        # allow_credentials=False means no access-control-allow-credentials header
        assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
class TestRequestId:
    """Tests for request ID middleware."""

    async def test_response_includes_request_id(self, async_client):
        response = await async_client.get("/")
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 8

    async def test_custom_request_id_echoed_back(self, async_client):
        response = await async_client.get("/", headers={"x-request-id": "custom42"})
        assert response.headers["x-request-id"] == "custom42"


@pytest.mark.asyncio
class TestHealth:
    """Tests for health endpoint."""

    async def test_health_returns_component_status(self, async_client):
        with patch("shoal.api.server.tmux.async_has_session", return_value=False):
            response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "components" in data
        assert "database" in data["components"]


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

    async def test_attach_mcp_auto_start(self, async_client):
        """Test POST /sessions/{id}/mcp/{name} auto-starts a registered server."""
        s = await create_session("auto-start-test", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx -y @modelcontextprotocol/server-memory"},
            ),
            patch(
                "shoal.api.server.start_mcp_server",
                return_value=(1234, "/tmp/mcp.sock", "npx cmd"),
            ),
            patch("shoal.services.mcp_configure.subprocess.run"),
        ):
            mock_socket.return_value = type("P", (), {"exists": lambda self: False})()
            response = await async_client.post(f"/sessions/{s.id}/mcp/memory")
            assert response.status_code == 200
            data = response.json()
            assert "Attached" in data["message"]

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


@pytest.mark.asyncio
class TestGetSessionFound:
    """Tests for GET /sessions/{id} when session exists."""

    async def test_get_session_returns_session_data(self, async_client):
        """Test GET /sessions/{id} returns full session response for existing session."""
        s = await create_session("get-test", "claude", "/tmp/test")

        response = await async_client.get(f"/sessions/{s.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == s.id
        assert data["name"] == "get-test"
        assert data["tool"] == "claude"
        assert data["path"] == "/tmp/test"
        assert data["status"] == "idle"
        assert "created_at" in data
        assert "last_activity" in data
        assert "tmux_session" in data


@pytest.mark.asyncio
class TestDeleteSession:
    """Tests for DELETE /sessions/{id} with lifecycle mocking."""

    async def test_delete_session_success(self, async_client):
        """Test DELETE /sessions/{id} calls kill_session_lifecycle and returns 204."""
        s = await create_session("kill-me", "claude", "/tmp/test")

        with patch(
            "shoal.api.server.kill_session_lifecycle",
            new_callable=AsyncMock,
            return_value={
                "tmux_killed": True,
                "worktree_removed": False,
                "branch_deleted": False,
                "db_deleted": True,
                "mcp_stopped": [],
            },
        ) as mock_kill:
            response = await async_client.delete(f"/sessions/{s.id}")
            assert response.status_code == 204
            mock_kill.assert_called_once_with(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree=s.worktree,
                git_root=s.path,
                branch=s.branch,
                remove_worktree=False,
                force=False,
            )

    async def test_delete_session_with_remove_worktree(self, async_client):
        """Test DELETE /sessions/{id}?remove_worktree=true passes flag through."""
        s = await create_session("kill-wt", "claude", "/tmp/test")

        with patch(
            "shoal.api.server.kill_session_lifecycle",
            new_callable=AsyncMock,
            return_value={
                "tmux_killed": True,
                "worktree_removed": True,
                "branch_deleted": True,
                "db_deleted": True,
                "mcp_stopped": [],
            },
        ) as mock_kill:
            response = await async_client.delete(
                f"/sessions/{s.id}?remove_worktree=true&force=true"
            )
            assert response.status_code == 204
            mock_kill.assert_called_once_with(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree=s.worktree,
                git_root=s.path,
                branch=s.branch,
                remove_worktree=True,
                force=True,
            )

    async def test_delete_session_dirty_worktree(self, async_client):
        """Test DELETE /sessions/{id} returns 409 when worktree is dirty."""
        from shoal.services.lifecycle import DirtyWorktreeError

        s = await create_session("dirty-wt", "claude", "/tmp/test")

        with patch(
            "shoal.api.server.kill_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=DirtyWorktreeError(
                "Worktree has uncommitted changes",
                session_id=s.id,
                dirty_files="M file.txt\n?? new.py",
            ),
        ):
            response = await async_client.delete(f"/sessions/{s.id}?remove_worktree=true")
            assert response.status_code == 409
            data = response.json()
            assert "dirty_files" in data["detail"]
            assert "M file.txt" in data["detail"]["dirty_files"]


@pytest.mark.asyncio
class TestRenameSessionTmux:
    """Tests for PUT /sessions/{id}/rename with tmux interactions."""

    async def test_rename_with_active_tmux_session(self, async_client):
        """Test rename calls tmux.rename_session when tmux session exists."""
        s = await create_session("tmux-rename", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.tmux.has_session", return_value=True),
            patch("shoal.api.server.tmux.rename_session") as mock_rename,
        ):
            response = await async_client.put(
                f"/sessions/{s.id}/rename",
                json={"name": "renamed"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "renamed"
        mock_rename.assert_called_once()

    async def test_rename_tmux_failure(self, async_client):
        """Test rename returns 500 when tmux rename fails."""
        s = await create_session("tmux-fail", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.tmux.has_session", return_value=True),
            patch(
                "shoal.api.server.tmux.rename_session",
                side_effect=subprocess.CalledProcessError(1, "tmux"),
            ),
        ):
            response = await async_client.put(
                f"/sessions/{s.id}/rename",
                json={"name": "will-fail"},
            )

        assert response.status_code == 500
        assert "Failed to rename tmux session" in response.json()["detail"]

    async def test_rename_self_name_allowed(self, async_client):
        """Test renaming session to its own name succeeds (no conflict)."""
        s = await create_session("keep-name", "claude", "/tmp/test")

        with patch("shoal.api.server.tmux.has_session", return_value=False):
            response = await async_client.put(
                f"/sessions/{s.id}/rename",
                json={"name": "keep-name"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "keep-name"


@pytest.mark.asyncio
class TestCreateSessionErrors:
    """Tests for POST /sessions error paths."""

    async def test_create_not_git_repo(self, async_client, tmp_path):
        """Test POST /sessions returns 400 when path is not a git repo."""
        test_dir = tmp_path / "not-git"
        test_dir.mkdir()

        with patch("shoal.api.server.git.is_git_repo", return_value=False):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "test"},
            )
        assert response.status_code == 400
        assert "Not a git repository" in response.json()["detail"]

    async def test_create_unknown_tool(self, async_client, tmp_path):
        """Test POST /sessions returns 400 for unknown tool."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch(
                "shoal.api.server.load_tool_config",
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "nonexistent", "name": "test"},
            )
        assert response.status_code == 400
        assert "Unknown tool" in response.json()["detail"]

    async def test_create_duplicate_name_conflict(self, async_client, tmp_path):
        """Test POST /sessions returns 409 when session name already exists."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Pre-create a session with the same name
        await create_session("existing", "claude", "/tmp/test")

        tool_cfg = MagicMock()
        tool_cfg.command = "claude"

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.load_tool_config", return_value=tool_cfg),
            patch("shoal.api.server.git.current_branch", return_value="main"),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "existing"},
            )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    async def test_create_session_exists_error(self, async_client, tmp_path):
        """Test POST /sessions returns 409 on SessionExistsError from lifecycle."""
        from shoal.services.lifecycle import SessionExistsError

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        tool_cfg = MagicMock()
        tool_cfg.command = "claude"

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.load_tool_config", return_value=tool_cfg),
            patch("shoal.api.server.git.current_branch", return_value="main"),
            patch("shoal.api.server.find_by_name", new_callable=AsyncMock, return_value=None),
            patch(
                "shoal.api.server.create_session_lifecycle",
                new_callable=AsyncMock,
                side_effect=SessionExistsError("Session already exists"),
            ),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "collision"},
            )
        assert response.status_code == 409

    async def test_create_tmux_setup_error(self, async_client, tmp_path):
        """Test POST /sessions returns 500 on TmuxSetupError from lifecycle."""
        from shoal.services.lifecycle import TmuxSetupError

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        tool_cfg = MagicMock()
        tool_cfg.command = "claude"

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.load_tool_config", return_value=tool_cfg),
            patch("shoal.api.server.git.current_branch", return_value="main"),
            patch("shoal.api.server.find_by_name", new_callable=AsyncMock, return_value=None),
            patch(
                "shoal.api.server.create_session_lifecycle",
                new_callable=AsyncMock,
                side_effect=TmuxSetupError("tmux new-session failed"),
            ),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "tmux-fail"},
            )
        assert response.status_code == 500
        assert "tmux" in response.json()["detail"]

    async def test_create_startup_command_error(self, async_client, tmp_path):
        """Test POST /sessions returns 500 on StartupCommandError from lifecycle."""
        from shoal.services.lifecycle import StartupCommandError

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        tool_cfg = MagicMock()
        tool_cfg.command = "claude"

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.load_tool_config", return_value=tool_cfg),
            patch("shoal.api.server.git.current_branch", return_value="main"),
            patch("shoal.api.server.find_by_name", new_callable=AsyncMock, return_value=None),
            patch(
                "shoal.api.server.create_session_lifecycle",
                new_callable=AsyncMock,
                side_effect=StartupCommandError("startup cmd failed"),
            ),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "startup-fail"},
            )
        assert response.status_code == 500
        assert "startup cmd failed" in response.json()["detail"]

    async def test_create_value_error(self, async_client, tmp_path):
        """Test POST /sessions returns 400 on ValueError from lifecycle."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        tool_cfg = MagicMock()
        tool_cfg.command = "claude"

        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value=str(test_dir)),
            patch("shoal.api.server.load_tool_config", return_value=tool_cfg),
            patch("shoal.api.server.git.current_branch", return_value="main"),
            patch("shoal.api.server.find_by_name", new_callable=AsyncMock, return_value=None),
            patch(
                "shoal.api.server.create_session_lifecycle",
                new_callable=AsyncMock,
                side_effect=ValueError("invalid session config"),
            ),
        ):
            response = await async_client.post(
                "/sessions",
                json={"path": str(test_dir), "tool": "claude", "name": "val-err"},
            )
        assert response.status_code == 400
        assert "invalid session config" in response.json()["detail"]


@pytest.mark.asyncio
class TestAttachSession:
    """Tests for POST /sessions/{id}/attach."""

    async def test_attach_session_not_found(self, async_client):
        """Test POST /sessions/{id}/attach returns 404 for missing session."""
        response = await async_client.post("/sessions/nonexistent/attach")
        assert response.status_code == 404

    async def test_attach_tmux_not_found(self, async_client):
        """Test POST /sessions/{id}/attach returns 400 when tmux session missing."""
        s = await create_session("attach-no-tmux", "claude", "/tmp/test")

        with patch("shoal.api.server.tmux.has_session", return_value=False):
            response = await async_client.post(f"/sessions/{s.id}/attach")
        assert response.status_code == 400
        assert "Tmux session not found" in response.json()["detail"]

    async def test_attach_success(self, async_client):
        """Test POST /sessions/{id}/attach succeeds and calls switch_client."""
        s = await create_session("attach-ok", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.tmux.has_session", return_value=True),
            patch("shoal.api.server.tmux.switch_client") as mock_switch,
        ):
            response = await async_client.post(f"/sessions/{s.id}/attach")
        assert response.status_code == 200
        assert "Attached" in response.json()["message"]
        mock_switch.assert_called_once_with(s.tmux_session)


@pytest.mark.asyncio
class TestMcpStartAndStop:
    """Tests for POST /mcp and DELETE /mcp/{name} with server lifecycle."""

    async def test_start_mcp_server_success(self, async_client):
        """Test POST /mcp creates a new MCP server and returns 201."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch("shoal.api.server.read_pid", return_value=None),
            patch(
                "shoal.api.server.start_mcp_server",
                return_value=(9999, "/tmp/test.sock", "npx memory"),
            ),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = False
            sock_path.__str__ = lambda self: "/tmp/test.sock"
            sock_path.parent = MagicMock()
            mock_socket.return_value = sock_path

            response = await async_client.post(
                "/mcp",
                json={"name": "memory", "command": "npx memory"},
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "memory"

    async def test_start_mcp_server_already_running(self, async_client):
        """Test POST /mcp returns 409 when server is already running."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=True),
            patch("shoal.api.server.read_pid", return_value=1234),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = True
            mock_socket.return_value = sock_path

            response = await async_client.post(
                "/mcp",
                json={"name": "memory"},
            )
            assert response.status_code == 409
            assert "already running" in response.json()["detail"]

    async def test_start_mcp_server_value_error(self, async_client):
        """Test POST /mcp returns 400 on ValueError from start_mcp_server."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch(
                "shoal.api.server.start_mcp_server",
                side_effect=ValueError("unknown server"),
            ),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = False
            mock_socket.return_value = sock_path

            response = await async_client.post(
                "/mcp",
                json={"name": "memory"},
            )
            assert response.status_code == 400
            assert "unknown server" in response.json()["detail"]

    async def test_start_mcp_server_runtime_error(self, async_client):
        """Test POST /mcp returns 500 on RuntimeError from start_mcp_server."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch(
                "shoal.api.server.start_mcp_server",
                side_effect=RuntimeError("socat not found"),
            ),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = False
            mock_socket.return_value = sock_path

            response = await async_client.post(
                "/mcp",
                json={"name": "memory"},
            )
            assert response.status_code == 500
            assert "socat not found" in response.json()["detail"]

    async def test_stop_mcp_server_success_cleans_sessions(self, async_client):
        """Test DELETE /mcp/{name} stops server and cleans up session references."""
        s = await create_session("mcp-user", "claude", "/tmp/test")
        from shoal.core.state import add_mcp_to_session

        await add_mcp_to_session(s.id, "memory")

        with patch("shoal.api.server.stop_mcp_server") as mock_stop:
            response = await async_client.delete("/mcp/memory")
            assert response.status_code == 204
            mock_stop.assert_called_once_with("memory")

        # Verify MCP was removed from session
        from shoal.core.state import get_session

        updated = await get_session(s.id)
        assert updated is not None
        assert "memory" not in updated.mcp_servers

    async def test_get_mcp_server_found(self, async_client):
        """Test GET /mcp/{name} returns server info when socket exists."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.read_pid", return_value=5678),
            patch("shoal.api.server.is_mcp_running", return_value=True),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = True
            sock_path.__str__ = lambda self: "/tmp/memory.sock"
            mock_socket.return_value = sock_path

            response = await async_client.get("/mcp/memory")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "memory"
            assert data["status"] == "running"
            assert data["pid"] == 5678


@pytest.mark.asyncio
class TestMcpDetach:
    """Tests for DELETE /sessions/{id}/mcp/{name} (detach)."""

    async def test_detach_mcp_not_attached(self, async_client):
        """Test detach returns 400 when MCP is not attached to session."""
        s = await create_session("no-mcp", "claude", "/tmp/test")

        response = await async_client.delete(f"/sessions/{s.id}/mcp/memory")
        assert response.status_code == 400
        assert "not attached" in response.json()["detail"]

    async def test_detach_mcp_success(self, async_client):
        """Test detach removes MCP from session and returns 204."""
        s = await create_session("has-mcp", "claude", "/tmp/test")
        from shoal.core.state import add_mcp_to_session

        await add_mcp_to_session(s.id, "memory")

        response = await async_client.delete(f"/sessions/{s.id}/mcp/memory")
        assert response.status_code == 204

        # Verify MCP was removed
        from shoal.core.state import get_session

        updated = await get_session(s.id)
        assert updated is not None
        assert "memory" not in updated.mcp_servers


@pytest.mark.asyncio
class TestMcpAttachEdgeCases:
    """Tests for POST /sessions/{id}/mcp/{name} edge cases."""

    async def test_attach_mcp_invalid_name(self, async_client):
        """Test attach returns 400 for invalid MCP name."""
        s = await create_session("mcp-invalid", "claude", "/tmp/test")

        response = await async_client.post(f"/sessions/{s.id}/mcp/bad;name")
        assert response.status_code == 400

    async def test_attach_mcp_not_running_not_in_registry(self, async_client):
        """Test attach returns 400 when MCP is not running and not in registry."""
        s = await create_session("mcp-unknown", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={},
            ),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = False
            mock_socket.return_value = sock_path

            response = await async_client.post(f"/sessions/{s.id}/mcp/unknown")
            assert response.status_code == 400
            assert "not running and not in registry" in response.json()["detail"]

    async def test_attach_mcp_auto_start_failure(self, async_client):
        """Test attach returns 500 when auto-start of MCP server fails."""
        s = await create_session("mcp-start-fail", "claude", "/tmp/test")

        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.is_mcp_running", return_value=False),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx -y @modelcontextprotocol/server-memory"},
            ),
            patch(
                "shoal.api.server.start_mcp_server",
                side_effect=RuntimeError("failed to start"),
            ),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = False
            mock_socket.return_value = sock_path

            response = await async_client.post(f"/sessions/{s.id}/mcp/memory")
            assert response.status_code == 500
            assert "Failed to auto-start" in response.json()["detail"]

    async def test_attach_mcp_stale_socket_cleanup(self, async_client):
        """Test attach cleans up stale socket before auto-starting."""
        s = await create_session("mcp-stale", "claude", "/tmp/test")

        is_running_calls = [False, False, True]  # stale check, then running after start
        call_idx = 0

        def is_running_side_effect(name: str) -> bool:
            nonlocal call_idx
            result = is_running_calls[min(call_idx, len(is_running_calls) - 1)]
            call_idx += 1
            return result

        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch(
                "shoal.api.server.is_mcp_running",
                side_effect=is_running_side_effect,
            ),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx -y @modelcontextprotocol/server-memory"},
            ),
            patch(
                "shoal.api.server.start_mcp_server",
                return_value=(1234, "/tmp/mcp.sock", "npx cmd"),
            ),
            patch("shoal.api.server.stop_mcp_server") as mock_stop,
            patch("shoal.services.mcp_configure.subprocess.run"),
        ):
            sock_path = MagicMock()
            # Socket exists (stale) on first check
            sock_path.exists.return_value = True
            sock_path.__str__ = lambda self: "/tmp/mcp.sock"
            mock_socket.return_value = sock_path

            response = await async_client.post(f"/sessions/{s.id}/mcp/memory")
            assert response.status_code == 200
            # Verify stale socket cleanup was attempted
            mock_stop.assert_called_once_with("memory")


@pytest.mark.asyncio
class TestMcpGetInfo:
    """Tests for _get_mcp_info internal function status detection."""

    async def test_mcp_dead_status(self, async_client):
        """Test GET /mcp/{name} returns 'dead' when pid exists but process not running."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.read_pid", return_value=9999),
            patch("shoal.api.server.is_mcp_running", return_value=False),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = True
            sock_path.__str__ = lambda self: "/tmp/dead.sock"
            mock_socket.return_value = sock_path

            response = await async_client.get("/mcp/dead-server")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "dead"

    async def test_mcp_orphaned_status(self, async_client):
        """Test GET /mcp/{name} returns 'orphaned' when no pid found."""
        with (
            patch("shoal.api.server.mcp_socket") as mock_socket,
            patch("shoal.api.server.read_pid", return_value=None),
            patch("shoal.api.server.is_mcp_running", return_value=False),
        ):
            sock_path = MagicMock()
            sock_path.exists.return_value = True
            sock_path.__str__ = lambda self: "/tmp/orphan.sock"
            mock_socket.return_value = sock_path

            response = await async_client.get("/mcp/orphan-server")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "orphaned"


@pytest.mark.asyncio
class TestListMcpSocketDirMissing:
    """Tests for GET /mcp when socket directory does not exist."""

    async def test_list_mcp_no_socket_dir(self, async_client):
        """Test GET /mcp returns empty list when socket dir doesn't exist."""
        with patch("shoal.api.server.mcp_socket") as mock_socket:
            parent = MagicMock()
            parent.exists.return_value = False
            sock_path = MagicMock()
            sock_path.parent = parent
            mock_socket.return_value = sock_path

            response = await async_client.get("/mcp")
            assert response.status_code == 200
            assert response.json() == []
