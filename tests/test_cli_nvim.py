"""Tests for cli/nvim.py."""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from shoal.cli.nvim import app
from shoal.core.state import create_session, update_session
from shoal.models.state import SessionStatus

runner = CliRunner()


import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from shoal.cli.nvim import app
from shoal.core.state import create_session, update_session
from shoal.models.state import SessionStatus
from shoal.core.db import with_db
import asyncio

runner = CliRunner()


def test_nvim_send_success(mock_dirs, tmp_path):
    """Test nvim send command successfully."""
    # Create a session with a fake nvim socket
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        s = await create_session("test-nvim", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running, nvim_socket=str(socket_path))

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.nvim.shutil.which", return_value="/usr/bin/nvr"),
        patch("shoal.cli.nvim.subprocess.run") as mock_run,
    ):
        result = runner.invoke(app, ["send", "test-nvim", "w"])
        assert result.exit_code == 0
        assert "Sent to test-nvim nvim: :w" in result.stdout
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "nvr" in args
        assert str(socket_path) in args
        assert ":w" in args[4]


def test_nvim_send_no_socket(mock_dirs):
    """Test nvim send when no socket is set (empty string)."""

    async def setup():
        s = await create_session("test-no-socket", "claude", "/tmp")
        # Explicitly clear the default nvim_socket to empty string
        await update_session(s.id, status=SessionStatus.running, nvim_socket="")

    asyncio.run(with_db(setup()))

    result = runner.invoke(app, ["send", "test-no-socket", "w"])
    assert result.exit_code == 1
    assert "No nvim socket for session 'test-no-socket'" in result.stdout


def test_nvim_send_socket_missing(mock_dirs):
    """Test nvim send when socket path doesn't exist."""

    async def setup():
        s = await create_session("test-missing-socket", "claude", "/tmp")
        await update_session(
            s.id, status=SessionStatus.running, nvim_socket="/tmp/nonexistent.sock"
        )

    asyncio.run(with_db(setup()))

    result = runner.invoke(app, ["send", "test-missing-socket", "w"])
    assert result.exit_code == 1
    assert "Nvim socket not found" in result.stdout


def test_nvim_diagnostics_success(mock_dirs, tmp_path):
    """Test nvim diagnostics command successfully."""
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        s = await create_session("test-diag", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running, nvim_socket=str(socket_path))

    asyncio.run(with_db(setup()))

    mock_result = MagicMock()
    mock_result.stdout = "file.py:10: [Error] something broke"

    with (
        patch("shoal.cli.nvim.shutil.which", return_value="/usr/bin/nvr"),
        patch("shoal.cli.nvim.subprocess.run", return_value=mock_result) as mock_run,
    ):
        result = runner.invoke(app, ["diagnostics", "test-diag"])
        assert result.exit_code == 0
        assert "Diagnostics for session 'test-diag':" in result.stdout
        assert "file.py:10" in result.stdout
        mock_run.assert_called_once()


def test_nvim_no_nvr(mock_dirs, tmp_path):
    """Test nvim commands when nvr is missing."""
    socket_path = tmp_path / "nvim.sock"
    socket_path.touch()

    async def setup():
        s = await create_session("test-no-nvr", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running, nvim_socket=str(socket_path))

    asyncio.run(with_db(setup()))

    with patch("shoal.cli.nvim.shutil.which", return_value=None):
        result = runner.invoke(app, ["send", "test-no-nvr", "w"])
        assert result.exit_code == 1
        assert "nvr not found" in result.stdout
