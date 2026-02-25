"""Tests for XDG Base Directory compliance in path functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from shoal.core.config import config_dir, runtime_dir, state_dir
from shoal.core.state import build_nvim_socket_path


class TestConfigDir:
    def test_default_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = config_dir()
        assert result == Path.home() / ".config" / "shoal"

    def test_xdg_config_home_override(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": str(tmp_path)}):
            result = config_dir()
        assert result == tmp_path / "shoal"


class TestStateDir:
    def test_default_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = state_dir()
        assert result == Path.home() / ".local" / "share" / "shoal"

    def test_xdg_data_home_override(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"XDG_DATA_HOME": str(tmp_path)}):
            result = state_dir()
        assert result == tmp_path / "shoal"


class TestRuntimeDir:
    def test_default_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = runtime_dir()
        assert result == Path.home() / ".local" / "state" / "shoal"

    def test_xdg_state_home_override(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"XDG_STATE_HOME": str(tmp_path)}):
            result = runtime_dir()
        assert result == tmp_path / "shoal"


class TestNvimSocketPath:
    def test_default_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = build_nvim_socket_path("$1", "@2")
        assert result == "/tmp/nvim-$1-@2.sock"

    def test_xdg_runtime_dir_override(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"XDG_RUNTIME_DIR": str(tmp_path)}):
            result = build_nvim_socket_path("$1", "@2")
        assert result == f"{tmp_path}/nvim-$1-@2.sock"
