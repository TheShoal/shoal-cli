"""Tests for cli/nvim.py and dynamic socket contract behavior."""

import asyncio
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from shoal.cli.nvim import app
from shoal.core.db import with_db
from shoal.core.state import create_session, get_session, resolve_nvim_socket, update_session
from shoal.models.state import SessionStatus

runner = CliRunner()


def test_nvim_send_success_dynamic_socket(mock_dirs, tmp_path):
    """shoal nvim send resolves socket at execution time."""
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        await create_session("test-nvim", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.nvim.resolve_nvim_socket", return_value=str(socket_path)),
        patch("shoal.cli.nvim.shutil.which", return_value="/usr/bin/nvr"),
        patch("shoal.cli.nvim.subprocess.run") as mock_run,
    ):
        result = runner.invoke(app, ["send", "test-nvim", "w"])
        assert result.exit_code == 0
        assert "Sent to test-nvim nvim: :w" in result.stdout
        args = mock_run.call_args[0][0]
        assert "nvr" in args
        assert str(socket_path) in args
        assert ":w" in args[4]


def test_same_session_different_window_routing(mock_dirs):
    """Socket target changes with window_id within same tmux session."""
    import os

    runtime_base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")

    async def scenario():
        s = await create_session("test-routing", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running, tmux_session="_test-routing")

        session = await get_session(s.id)
        assert session is not None

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.preferred_pane", return_value="%1"),
            patch(
                "shoal.core.tmux.pane_coordinates",
                side_effect=[("$1", "@1"), ("$1", "@2")],
            ),
        ):
            sock_a = await resolve_nvim_socket(session)
            refreshed = await get_session(s.id)
            assert refreshed is not None
            sock_b = await resolve_nvim_socket(refreshed)

        latest = await get_session(s.id)
        assert latest is not None
        assert sock_a == f"{runtime_base}/nvim-$1-@1.sock"
        assert sock_b == f"{runtime_base}/nvim-$1-@2.sock"
        assert latest.tmux_session_id == "$1"
        assert latest.tmux_window == "@2"

    asyncio.run(with_db(scenario()))


def test_session_rename_stability_id_based_socket(mock_dirs):
    """Socket path remains stable across tmux session-name renames."""
    import os

    runtime_base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")

    async def scenario():
        s = await create_session("old-name", "claude", "/tmp")
        await update_session(s.id, name="new-name", tmux_session="_new-name")

        renamed = await get_session(s.id)
        assert renamed is not None

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.preferred_pane", return_value="%7"),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$9", "@3")),
        ):
            socket = await resolve_nvim_socket(renamed)

        assert socket == f"{runtime_base}/nvim-$9-@3.sock"
        assert "new-name" not in socket
        assert "old-name" not in socket

    asyncio.run(with_db(scenario()))


def test_nvim_send_stale_socket_handling(mock_dirs):
    """Missing dynamic socket returns clear stale-socket style failure."""

    async def setup():
        await create_session("test-stale-socket", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.nvim.resolve_nvim_socket", return_value="/tmp/nvim-$stale-@999.sock"),
        patch("shoal.cli.nvim.shutil.which", return_value="/usr/bin/nvr"),
    ):
        result = runner.invoke(app, ["send", "test-stale-socket", "w"])
        assert result.exit_code == 1
        assert "Nvim socket not found" in result.stdout


def test_nvim_diagnostics_success(mock_dirs, tmp_path):
    """Diagnostics command uses dynamically resolved socket."""
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        await create_session("test-diag", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    mock_result = MagicMock()
    mock_result.stdout = "file.py:10: [Error] something broke"

    with (
        patch("shoal.cli.nvim.resolve_nvim_socket", return_value=str(socket_path)),
        patch("shoal.cli.nvim.shutil.which", return_value="/usr/bin/nvr"),
        patch("shoal.cli.nvim.subprocess.run", return_value=mock_result) as mock_run,
    ):
        result = runner.invoke(app, ["diagnostics", "test-diag"])
        assert result.exit_code == 0
        assert "Diagnostics for session 'test-diag':" in result.stdout
        assert "file.py:10" in result.stdout
        mock_run.assert_called_once()


def test_nvim_no_nvr(mock_dirs, tmp_path):
    """nvim commands fail gracefully when nvr is missing."""
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        await create_session("test-no-nvr", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.nvim.resolve_nvim_socket", return_value=str(socket_path)),
        patch("shoal.cli.nvim.shutil.which", return_value=None),
    ):
        result = runner.invoke(app, ["send", "test-no-nvr", "w"])
        assert result.exit_code == 1
        assert "nvr not found" in result.stdout
