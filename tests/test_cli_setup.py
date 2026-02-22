"""Tests for cli/setup.py."""

from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.setup import app

runner = CliRunner()


def test_setup_fish_install():
    """Test setup fish command dispatches to install."""
    with patch(
        "shoal.integrations.fish.installer.install_fish_integration", return_value=True
    ) as mock_install:
        result = runner.invoke(app, [], catch_exceptions=False)
        assert result.exit_code == 0
        mock_install.assert_called_once_with(force=False)


def test_setup_fish_install_force():
    """Test setup fish command with --force."""
    with patch(
        "shoal.integrations.fish.installer.install_fish_integration", return_value=True
    ) as mock_install:
        result = runner.invoke(app, ["--force"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_install.assert_called_once_with(force=True)


def test_setup_fish_uninstall():
    """Test setup fish command dispatches to uninstall."""
    with patch(
        "shoal.integrations.fish.installer.uninstall_fish_integration", return_value=True
    ) as mock_uninstall:
        result = runner.invoke(app, ["--uninstall"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_uninstall.assert_called_once()


def test_setup_fish_fail():
    """Test setup fish command handling failure."""
    with patch("shoal.integrations.fish.installer.install_fish_integration", return_value=False):
        result = runner.invoke(app, [], catch_exceptions=False)
        assert result.exit_code == 1
