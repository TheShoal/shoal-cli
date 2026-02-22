"""CLI/API parity tests — verify both entry points share lifecycle behavior.

These tests prove that CLI and API session lifecycle operations delegate
to the same shared lifecycle service in services/lifecycle.py, ensuring
identical behavior contracts.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from shoal.cli import app as cli_app
from shoal.models.state import SessionState, SessionStatus
from shoal.services.lifecycle import (
    DirtyWorktreeError,
    SessionExistsError,
)

runner = CliRunner()


def _make_session(name: str = "test", status: str = "running") -> SessionState:
    return SessionState(
        id=f"id-{name}",
        name=name,
        tool="claude",
        path="/tmp/repo",
        tmux_session=f"_{name}",
        tmux_window=f"_{name}:0",
        worktree="",
        branch="main",
        status=SessionStatus(status),
        mcp_servers=[],
        pid=12345,
        pane_coordinates=f"_{name}:0.0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_activity=datetime(2026, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Structural parity: both CLI and API import from the same lifecycle module
# ---------------------------------------------------------------------------


class TestLifecycleSharing:
    """Verify CLI and API share the same lifecycle functions."""

    def test_cli_imports_create_from_lifecycle(self):
        """CLI session_create module imports create_session_lifecycle from services."""
        from shoal.cli import session_create as cli_create

        assert hasattr(cli_create, "create_session_lifecycle")
        assert cli_create.create_session_lifecycle.__module__ == "shoal.services.lifecycle"

    def test_api_imports_create_from_lifecycle(self):
        """API server module imports create_session_lifecycle from services."""
        from shoal.api import server as api_server

        assert hasattr(api_server, "create_session_lifecycle")
        assert api_server.create_session_lifecycle.__module__ == "shoal.services.lifecycle"

    def test_cli_imports_kill_from_lifecycle(self):
        """CLI session_create module imports kill_session_lifecycle from services."""
        from shoal.cli import session_create as cli_create

        assert hasattr(cli_create, "kill_session_lifecycle")

    def test_api_imports_kill_from_lifecycle(self):
        """API server module imports kill_session_lifecycle from services."""
        from shoal.api import server as api_server

        assert hasattr(api_server, "kill_session_lifecycle")

    def test_both_use_same_create_function(self):
        """CLI and API reference the exact same create_session_lifecycle."""
        from shoal.api import server as api_server
        from shoal.cli import session_create as cli_create

        assert cli_create.create_session_lifecycle is api_server.create_session_lifecycle

    def test_both_use_same_kill_function(self):
        """CLI and API reference the exact same kill_session_lifecycle."""
        from shoal.api import server as api_server
        from shoal.cli import session_create as cli_create

        assert cli_create.kill_session_lifecycle is api_server.kill_session_lifecycle

    def test_both_use_same_exception_types(self):
        """CLI and API import the same exception classes."""
        from shoal.api import server as api_server
        from shoal.cli import session_create as cli_create

        assert cli_create.SessionExistsError is api_server.SessionExistsError
        assert cli_create.StartupCommandError is api_server.StartupCommandError
        assert cli_create.TmuxSetupError is api_server.TmuxSetupError

    def test_create_session_lifecycle_is_async(self):
        """create_session_lifecycle must be async (used with await in both CLI and API)."""
        from shoal.services.lifecycle import create_session_lifecycle

        assert inspect.iscoroutinefunction(create_session_lifecycle)

    def test_kill_session_lifecycle_is_async(self):
        """kill_session_lifecycle must be async."""
        from shoal.services.lifecycle import kill_session_lifecycle

        assert inspect.iscoroutinefunction(kill_session_lifecycle)


# ---------------------------------------------------------------------------
# Error handling parity
# ---------------------------------------------------------------------------


class TestErrorHandlingParity:
    """Both CLI and API handle lifecycle errors, just with different outputs."""

    def test_cli_handles_session_exists_error(self, mock_dirs, tmp_path):
        """CLI exits 1 on SessionExistsError."""
        with (
            patch("shoal.cli.session_create.git.is_git_repo", return_value=True),
            patch("shoal.cli.session_create.git.git_root", return_value=str(tmp_path)),
            patch("shoal.cli.session_create.load_tool_config") as mock_tool,
            patch(
                "shoal.cli.session_create.create_session_lifecycle",
                side_effect=SessionExistsError("exists"),
            ),
        ):
            mock_tool.return_value = MagicMock(command="claude", icon="●")
            result = runner.invoke(cli_app, ["new", str(tmp_path)])
        assert result.exit_code == 1

    async def test_api_returns_409_on_session_exists_error(self, mock_dirs, async_client):
        """API returns 409 on SessionExistsError."""
        with (
            patch("shoal.api.server.git.is_git_repo", return_value=True),
            patch("shoal.api.server.git.git_root", return_value="/tmp/repo"),
            patch("shoal.api.server.git.current_branch", return_value="main"),
            patch("shoal.api.server.load_tool_config") as mock_tool,
            patch("shoal.api.server.find_by_name", return_value=None),
            patch(
                "shoal.api.server.create_session_lifecycle",
                side_effect=SessionExistsError("exists"),
            ),
        ):
            mock_tool.return_value = MagicMock(command="claude", icon="●")
            resp = await async_client.post(
                "/sessions",
                json={"path": "/tmp/repo", "tool": "claude", "name": "dup"},
            )
        assert resp.status_code == 409

    async def test_api_returns_409_on_dirty_worktree(self, mock_dirs, async_client):
        """API returns 409 with dirty_files on DirtyWorktreeError."""
        session = _make_session("dirty")
        mock_kill = AsyncMock(
            side_effect=DirtyWorktreeError("dirty", session_id="id-dirty", dirty_files="M file.py")
        )
        with (
            patch("shoal.api.server.get_session", return_value=session),
            patch("shoal.api.server.kill_session_lifecycle", mock_kill),
        ):
            resp = await async_client.delete("/sessions/id-dirty")
        assert resp.status_code == 409
        assert "dirty_files" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Rename validation parity
# ---------------------------------------------------------------------------


class TestRenameValidationParity:
    """Both CLI and API reject invalid session names."""

    def test_cli_rejects_shell_metacharacters(self, mock_dirs):
        result = runner.invoke(cli_app, ["rename", "old", "bad;name"])
        assert result.exit_code == 1

    async def test_api_rejects_shell_metacharacters(self, mock_dirs, async_client):
        session = _make_session("old")
        with patch("shoal.api.server.get_session", return_value=session):
            resp = await async_client.put(
                "/sessions/id-old/rename",
                json={"name": "bad;name"},
            )
        assert resp.status_code == 422

    def test_cli_rejects_empty_name(self, mock_dirs):
        result = runner.invoke(cli_app, ["rename", "old", ""])
        assert result.exit_code == 1

    async def test_api_rejects_empty_name(self, mock_dirs, async_client):
        session = _make_session("old")
        with patch("shoal.api.server.get_session", return_value=session):
            resp = await async_client.put(
                "/sessions/id-old/rename",
                json={"name": ""},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Fork: CLI-only by design
# ---------------------------------------------------------------------------


class TestForkIntentionallyCliOnly:
    """Fork has no API endpoint — deliberate design choice.

    The fork operation requires interactive tmux context (worktree creation,
    branch management) that doesn't map cleanly to a REST API.
    """

    async def test_no_fork_api_endpoint(self, mock_dirs, async_client):
        """No POST /sessions/fork route exists."""
        resp = await async_client.post("/sessions/fork", json={"id": "test"})
        assert resp.status_code in (404, 405, 422)

    async def test_no_fork_on_session(self, mock_dirs, async_client):
        """No POST /sessions/{id}/fork route exists."""
        resp = await async_client.post("/sessions/id-test/fork")
        assert resp.status_code in (404, 405)
