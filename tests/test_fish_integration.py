"""Tests for fish shell integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from shoal.integrations.fish.installer import (
    get_fish_config_dir,
    get_template_dir,
    install_fish_integration,
    is_fish_installed,
    uninstall_fish_integration,
)


def test_get_template_dir():
    """Test that template directory exists and contains expected files."""
    template_dir = get_template_dir()
    assert template_dir.exists()
    assert template_dir.is_dir()

    # Check that all required template files exist
    assert (template_dir / "completions.fish").exists()
    assert (template_dir / "bootstrap.fish").exists()
    assert (template_dir / "quick-attach.fish").exists()
    assert (template_dir / "dashboard.fish").exists()
    assert (template_dir / "remote.fish").exists()


def test_is_fish_installed():
    """Test fish installation detection."""
    # This test depends on the actual system, so we just check it returns a bool
    result = is_fish_installed()
    assert isinstance(result, bool)


def test_get_fish_config_dir():
    """Test fish config directory detection."""
    config_dir = get_fish_config_dir()
    # Should return Path or None
    assert config_dir is None or isinstance(config_dir, Path)


@patch("shoal.integrations.fish.installer.is_fish_installed")
@patch("shoal.integrations.fish.installer.Console")
def test_install_fish_integration_no_fish(mock_console, mock_is_fish):
    """Test installation fails gracefully when fish is not installed."""
    mock_is_fish.return_value = False

    result = install_fish_integration()

    assert result is False
    # Verify error message was printed
    mock_console.return_value.print.assert_called()


@patch("shoal.integrations.fish.installer.is_fish_installed")
@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.Console")
def test_install_fish_integration_no_config_dir(mock_console, mock_get_config, mock_is_fish):
    """Test installation fails when fish config directory can't be found."""
    mock_is_fish.return_value = True
    mock_get_config.return_value = None

    result = install_fish_integration()

    assert result is False
    mock_console.return_value.print.assert_called()


@patch("shoal.integrations.fish.installer.is_fish_installed")
@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.shutil.copy2")
@patch("shoal.integrations.fish.installer.Console")
def test_install_fish_integration_success(
    mock_console, mock_copy, mock_get_config, mock_is_fish, tmp_path
):
    """Test successful fish integration installation."""
    mock_is_fish.return_value = True
    mock_get_config.return_value = tmp_path / "fish"

    # Create fish config directories
    fish_config = tmp_path / "fish"
    (fish_config / "completions").mkdir(parents=True)
    (fish_config / "conf.d").mkdir(parents=True)
    (fish_config / "functions").mkdir(parents=True)

    result = install_fish_integration()

    # Should succeed
    assert result is True

    # Verify files were copied (5 files: completions, bootstrap, 3 functions)
    assert mock_copy.call_count == 5


@patch("shoal.integrations.fish.installer.is_fish_installed")
@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.shutil.copy2")
@patch("shoal.integrations.fish.installer.Console")
def test_install_fish_integration_skip_existing(
    mock_console, mock_copy, mock_get_config, mock_is_fish, tmp_path
):
    """Test that existing files are skipped without --force."""
    mock_is_fish.return_value = True
    mock_get_config.return_value = tmp_path / "fish"

    # Create fish config directories
    fish_config = tmp_path / "fish"
    completions_dir = fish_config / "completions"
    conf_d_dir = fish_config / "conf.d"
    functions_dir = fish_config / "functions"

    completions_dir.mkdir(parents=True)
    conf_d_dir.mkdir(parents=True)
    functions_dir.mkdir(parents=True)

    # Create existing files
    (completions_dir / "shoal.fish").touch()
    (conf_d_dir / "shoal.fish").touch()

    result = install_fish_integration(force=False)

    # Should still succeed but skip existing files
    assert result is True

    # Only 3 new files should be copied (the function files)
    assert mock_copy.call_count == 3


@patch("shoal.integrations.fish.installer.is_fish_installed")
@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.shutil.copy2")
@patch("shoal.integrations.fish.installer.Console")
def test_install_fish_integration_force(
    mock_console, mock_copy, mock_get_config, mock_is_fish, tmp_path
):
    """Test that --force overwrites existing files."""
    mock_is_fish.return_value = True
    mock_get_config.return_value = tmp_path / "fish"

    # Create fish config directories
    fish_config = tmp_path / "fish"
    completions_dir = fish_config / "completions"
    conf_d_dir = fish_config / "conf.d"
    functions_dir = fish_config / "functions"

    completions_dir.mkdir(parents=True)
    conf_d_dir.mkdir(parents=True)
    functions_dir.mkdir(parents=True)

    # Create existing files
    (completions_dir / "shoal.fish").write_text("old content")
    (conf_d_dir / "shoal.fish").write_text("old content")

    result = install_fish_integration(force=True)

    # Should succeed and overwrite all files
    assert result is True


@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.Console")
def test_uninstall_fish_integration_success(mock_console, mock_get_config, tmp_path):
    """Test successful fish integration removal."""
    fish_config = tmp_path / "fish"
    mock_get_config.return_value = fish_config

    # Create directories and files
    completions_dir = fish_config / "completions"
    conf_d_dir = fish_config / "conf.d"
    functions_dir = fish_config / "functions"
    completions_dir.mkdir(parents=True)
    conf_d_dir.mkdir(parents=True)
    functions_dir.mkdir(parents=True)

    f1 = completions_dir / "shoal.fish"
    f2 = conf_d_dir / "shoal.fish"
    f1.touch()
    f2.touch()

    result = uninstall_fish_integration()

    assert result is True
    assert not f1.exists()
    assert not f2.exists()
    # Verify success message printed
    mock_console.return_value.print.assert_called()


@patch("shoal.integrations.fish.installer.get_fish_config_dir")
@patch("shoal.integrations.fish.installer.Console")
def test_uninstall_fish_integration_not_found(mock_console, mock_get_config, tmp_path):
    """Test uninstall when no files exist."""
    fish_config = tmp_path / "nonexistent"
    mock_get_config.return_value = fish_config

    result = uninstall_fish_integration()

    assert result is True
    # Verify "not found" message printed
    mock_console.return_value.print.assert_called()
