"""Coverage tests for session CLI commands: status, info, rename."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli import app
from shoal.models.state import SessionState, SessionStatus

runner = CliRunner()


def _make_session(
    name: str = "test",
    status: str = "running",
    tool: str = "claude",
    worktree: str = "",
    mcp_servers: list[str] | None = None,
) -> SessionState:
    return SessionState(
        id=f"id-{name}",
        name=name,
        tool=tool,
        path="/tmp/repo",
        tmux_session=f"_{name}",
        tmux_window=f"_{name}:0",
        worktree=worktree or "",
        branch="main",
        status=SessionStatus(status),
        mcp_servers=mcp_servers or [],
        pid=12345,
        pane_coordinates="_{name}:0.0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_activity=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestStatusWithSessions:
    """Cover the status command with sessions (lines 706-783)."""

    def test_status_mixed_statuses(self, mock_dirs):
        sessions = [
            _make_session("s1", "running"),
            _make_session("s2", "waiting"),
            _make_session("s3", "error"),
            _make_session("s4", "idle"),
            _make_session("s5", "stopped"),
            _make_session("s6", "unknown"),
        ]
        with patch("shoal.cli.session.list_sessions", return_value=sessions):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "running" in result.output
        assert "waiting" in result.output
        assert "error" in result.output
        assert "idle" in result.output
        assert "stopped" in result.output
        assert "unknown" in result.output

    def test_status_plain_format_with_sessions(self, mock_dirs):
        sessions = [
            _make_session("s1", "running"),
            _make_session("s2", "waiting"),
            _make_session("s3", "idle"),
        ]
        with patch("shoal.cli.session.list_sessions", return_value=sessions):
            result = runner.invoke(app, ["status", "--format", "plain"])
        assert result.exit_code == 0
        assert "Total: 3" in result.output
        assert "1 running" in result.output
        assert "1 waiting" in result.output
        assert "1 idle" in result.output

    def test_status_waiting_shows_attach_hints(self, mock_dirs):
        sessions = [_make_session("needs-input", "waiting")]
        with patch("shoal.cli.session.list_sessions", return_value=sessions):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "needs-input" in result.output

    def test_status_error_shows_error_hints(self, mock_dirs):
        sessions = [_make_session("broken", "error")]
        with patch("shoal.cli.session.list_sessions", return_value=sessions):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "broken" in result.output


class TestInfoCommand:
    """Cover the info command (lines 957-1062)."""

    def test_info_shows_session_details(self, mock_dirs):
        s = _make_session("my-session", "running", worktree="/tmp/wt", mcp_servers=["memory"])

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.tmux.has_session", return_value=False),
            patch(
                "shoal.cli.session.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
        ):
            result = runner.invoke(app, ["info", "my-session"])
        assert result.exit_code == 0
        assert "my-session" in result.output

    def test_info_with_tmux_output(self, mock_dirs):
        s = _make_session("live-session", "running")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.tmux.has_session", return_value=True),
            patch("shoal.cli.session.tmux.preferred_pane", return_value="_live-session:0.0"),
            patch("shoal.cli.session.tmux.capture_pane", return_value="hello output\nline 2\n"),
            patch(
                "shoal.cli.session.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
        ):
            result = runner.invoke(app, ["info", "live-session"])
        assert result.exit_code == 0
        assert "Recent Output" in result.output

    def test_info_color_always(self, mock_dirs):
        s = _make_session("color-test", "idle")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.tmux.has_session", return_value=False),
            patch(
                "shoal.cli.session.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
        ):
            result = runner.invoke(app, ["info", "color-test", "--color", "always"])
        assert result.exit_code == 0

    def test_info_color_never(self, mock_dirs):
        s = _make_session("no-color", "idle")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.tmux.has_session", return_value=False),
            patch(
                "shoal.cli.session.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
        ):
            result = runner.invoke(app, ["info", "no-color", "--color", "never"])
        assert result.exit_code == 0

    def test_info_empty_output(self, mock_dirs):
        s = _make_session("empty-pane", "running")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.tmux.has_session", return_value=True),
            patch("shoal.cli.session.tmux.preferred_pane", return_value="_empty-pane:0.0"),
            patch("shoal.cli.session.tmux.capture_pane", return_value=""),
            patch(
                "shoal.cli.session.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
        ):
            result = runner.invoke(app, ["info", "empty-pane"])
        assert result.exit_code == 0
        assert "no output captured" in result.output


class TestRenameCommand:
    """Cover the rename command (lines 919-954)."""

    def test_rename_success(self, mock_dirs):
        s = _make_session("old-name", "running")

        async def mock_resolve(name):
            return s.id if name == "old-name" else None

        with (
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.cli.session.find_by_name", return_value=None),
            patch("shoal.cli.session.tmux.has_session", return_value=True),
            patch("shoal.cli.session.tmux.rename_session"),
            patch("shoal.cli.session.update_session"),
        ):
            result = runner.invoke(app, ["rename", "old-name", "new-name"])
        assert result.exit_code == 0
        assert "Renamed" in result.output

    def test_rename_invalid_name(self, mock_dirs):
        result = runner.invoke(app, ["rename", "old", "bad;name"])
        assert result.exit_code == 1
        assert "Invalid" in result.output

    def test_rename_not_found(self, mock_dirs):
        async def mock_resolve(name):
            return None

        with patch("shoal.core.state.resolve_session", side_effect=mock_resolve):
            result = runner.invoke(app, ["rename", "nonexistent", "new-name"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_rename_duplicate(self, mock_dirs):
        s = _make_session("existing", "running")

        async def mock_resolve(name):
            return s.id

        with (
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.get_session", return_value=s),
            patch("shoal.cli.session.find_by_name", return_value=_make_session("taken")),
        ):
            result = runner.invoke(app, ["rename", "existing", "taken"])
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestMcpLsWithServers:
    """Cover mcp ls with running servers (lines 54-93)."""

    def test_mcp_ls_with_running_server(self, mock_dirs):
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        socket_dir.mkdir(parents=True, exist_ok=True)
        (socket_dir / "memory.sock").touch()

        pid_dir = tmp_state / "mcp-pool" / "pids"
        pid_dir.mkdir(parents=True, exist_ok=True)
        (pid_dir / "memory.pid").write_text("99999")

        sessions = [_make_session("s1", "running", mcp_servers=["memory"])]

        with (
            patch("shoal.cli.mcp.list_sessions", return_value=sessions),
            patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        ):
            result = runner.invoke(app, ["mcp", "ls"])
        assert result.exit_code == 0
        assert "memory" in result.output

    def test_mcp_ls_dead_server(self, mock_dirs):
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        socket_dir.mkdir(parents=True, exist_ok=True)
        (socket_dir / "dead.sock").touch()

        pid_dir = tmp_state / "mcp-pool" / "pids"
        pid_dir.mkdir(parents=True, exist_ok=True)
        (pid_dir / "dead.pid").write_text("99999")

        with (
            patch("shoal.cli.mcp.list_sessions", return_value=[]),
            patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        ):
            result = runner.invoke(app, ["mcp", "ls"])
        assert result.exit_code == 0
        assert "dead" in result.output
