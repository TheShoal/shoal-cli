"""Tests covering gaps in src/shoal/cli/session.py (attach, detach, rename, prune, popup)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from shoal.cli import app
from shoal.models.state import SessionState, SessionStatus


@pytest.fixture()
def runner() -> CliRunner:
    """Per-test CliRunner to avoid shared mutable state."""
    return CliRunner()


def _make_session(
    name: str = "test",
    status: str = "running",
) -> SessionState:
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


class TestAttachFlow:
    """Cover attach lines 42-56."""

    def test_attach_get_session_returns_none(self, mock_dirs, runner):
        """Line 42: get_session returns None."""
        s = _make_session("ghost")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch(
                "shoal.cli.session._resolve_session_interactive_impl",
                side_effect=mock_resolve,
            ),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=None),
        ):
            result = runner.invoke(app, ["attach", "ghost"])
        assert result.exit_code == 1

    def test_attach_tmux_not_found(self, mock_dirs, runner):
        """Lines 44-49: tmux session not found, marks stopped."""
        s = _make_session("dead-sess")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch(
                "shoal.cli.session._resolve_session_interactive_impl",
                side_effect=mock_resolve,
            ),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=s),
            patch("shoal.cli.session.tmux.has_session", return_value=False),
            patch("shoal.cli.session.update_session", new_callable=AsyncMock) as mock_update,
        ):
            result = runner.invoke(app, ["attach", "dead-sess"])
        assert result.exit_code == 1
        assert "not found" in result.output
        mock_update.assert_called_once_with(s.id, status=SessionStatus.stopped)

    def test_attach_inside_tmux_switches_client(self, mock_dirs, runner):
        """Lines 51-54: touch + switch_client."""
        s = _make_session("my-sess")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch(
                "shoal.cli.session._resolve_session_interactive_impl",
                side_effect=mock_resolve,
            ),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=s),
            patch("shoal.cli.session.tmux.has_session", return_value=True),
            patch("shoal.cli.session.touch_session", new_callable=AsyncMock),
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=True),
            patch("shoal.cli.session.tmux.switch_client") as mock_switch,
        ):
            result = runner.invoke(app, ["attach", "my-sess"])
        assert result.exit_code == 0
        mock_switch.assert_called_once_with(s.tmux_session)

    def test_attach_outside_tmux_attaches(self, mock_dirs, runner):
        """Lines 55-56: attach_session."""
        s = _make_session("my-sess")

        async def mock_resolve(name_or_id):
            return s.id

        with (
            patch(
                "shoal.cli.session._resolve_session_interactive_impl",
                side_effect=mock_resolve,
            ),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=s),
            patch("shoal.cli.session.tmux.has_session", return_value=True),
            patch("shoal.cli.session.touch_session", new_callable=AsyncMock),
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=False),
            patch("shoal.cli.session.tmux.attach_session") as mock_attach,
        ):
            result = runner.invoke(app, ["attach", "my-sess"])
        assert result.exit_code == 0
        mock_attach.assert_called_once_with(s.tmux_session)


class TestDetachFlow:
    """Cover detach lines 61-70."""

    def test_detach_not_inside_tmux(self, mock_dirs, runner):
        """Lines 61-63: not inside tmux."""
        with patch("shoal.cli.session.tmux.is_inside_tmux", return_value=False):
            result = runner.invoke(app, ["detach"])
        assert result.exit_code == 1
        assert "Not inside a tmux session" in result.output

    def test_detach_not_shoal_session(self, mock_dirs, runner):
        """Lines 65-68: inside tmux but not a shoal session."""
        with (
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=True),
            patch("shoal.cli.session.tmux.current_session_name", return_value="personal"),
        ):
            result = runner.invoke(app, ["detach"])
        assert result.exit_code == 1
        assert "Not inside a shoal session" in result.output

    def test_detach_success(self, mock_dirs, runner):
        """Lines 65-70: successful detach."""
        with (
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=True),
            patch(
                "shoal.cli.session.tmux.current_session_name",
                return_value="_my-session",
            ),
            patch("shoal.cli.session.is_shoal_tmux_session_name", return_value=True),
            patch("shoal.cli.session.tmux.detach_client") as mock_detach,
        ):
            result = runner.invoke(app, ["detach"])
        assert result.exit_code == 0
        mock_detach.assert_called_once()


class TestRenameGetSessionNone:
    """Cover rename line 99."""

    def test_rename_get_session_returns_none(self, mock_dirs, runner):
        """Line 99: resolve succeeds but get_session returns None."""

        async def mock_resolve(name):
            return "some-id"

        with (
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=None),
        ):
            result = runner.invoke(app, ["rename", "old-name", "new-name"])
        assert result.exit_code == 1

    def test_rename_no_tmux_session(self, mock_dirs, runner):
        """Lines 110-112: tmux session does not exist, still renames in DB."""
        s = _make_session("old-name")

        async def mock_resolve(name):
            return s.id if name == "old-name" else None

        with (
            patch("shoal.core.state.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.session.get_session", new_callable=AsyncMock, return_value=s),
            patch("shoal.cli.session.find_by_name", new_callable=AsyncMock, return_value=None),
            patch("shoal.cli.session.tmux.has_session", return_value=False),
            patch("shoal.cli.session.tmux.rename_session") as mock_tmux_rename,
            patch("shoal.cli.session.update_session", new_callable=AsyncMock),
        ):
            result = runner.invoke(app, ["rename", "old-name", "new-name"])
        assert result.exit_code == 0
        mock_tmux_rename.assert_not_called()
        assert "Renamed session" in result.output


class TestPruneConfirmation:
    """Cover prune lines 128-147."""

    def test_prune_confirm_yes(self, mock_dirs, runner):
        """Lines 138-143: user confirms prune."""
        import asyncio

        from shoal.core.state import create_session, update_session

        s = asyncio.run(create_session("dead-sess", "claude", "/tmp/repo"))
        asyncio.run(update_session(s.id, status=SessionStatus.stopped))

        result = runner.invoke(app, ["prune"], input="y\n")
        assert result.exit_code == 0
        assert "dead-sess" in result.output
        assert "Removed" in result.output

    def test_prune_confirm_no(self, mock_dirs, runner):
        """Lines 138-143: user declines prune."""
        import asyncio

        from shoal.core.state import create_session, update_session

        s = asyncio.run(create_session("keep-sess", "claude", "/tmp/repo"))
        asyncio.run(update_session(s.id, status=SessionStatus.stopped))

        result = runner.invoke(app, ["prune"], input="n\n")
        assert result.exit_code != 0  # typer.Abort

    def test_prune_no_stopped_sessions(self, mock_dirs, runner):
        """Lines 133-135: no stopped sessions to prune."""
        result = runner.invoke(app, ["prune"])
        assert result.exit_code == 0
        assert "No stopped sessions" in result.output

    def test_prune_force(self, mock_dirs, runner):
        """Line 137: force skips confirmation."""
        import asyncio

        from shoal.core.state import create_session, update_session

        s = asyncio.run(create_session("force-del", "claude", "/tmp/repo"))
        asyncio.run(update_session(s.id, status=SessionStatus.stopped))

        result = runner.invoke(app, ["prune", "--force"])
        assert result.exit_code == 0
        assert "Removed" in result.output


class TestPopupFlow:
    """Cover popup lines 150-164."""

    def test_popup_inside_tmux(self, mock_dirs, runner):
        """Lines 153-155: inside tmux launches popup."""
        with (
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=True),
            patch("shoal.cli.session.tmux.popup") as mock_popup,
        ):
            result = runner.invoke(app, ["popup"])
        assert result.exit_code == 0
        mock_popup.assert_called_once_with("shoal _popup-inner")

    def test_popup_outside_tmux(self, mock_dirs, runner):
        """Lines 156-157: outside tmux runs inner impl."""
        with (
            patch("shoal.cli.session.tmux.is_inside_tmux", return_value=False),
            patch("shoal.cli.session._popup_inner_impl") as mock_inner,
        ):
            result = runner.invoke(app, ["popup"])
        assert result.exit_code == 0
        mock_inner.assert_called_once()

    def test_popup_inner_impl(self):
        """Lines 162-164: _popup_inner_impl calls run_popup."""
        with patch("shoal.dashboard.popup.run_popup") as mock_run:
            from shoal.cli.session import _popup_inner_impl

            _popup_inner_impl()
        mock_run.assert_called_once()
