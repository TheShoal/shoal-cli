"""Tests for shoal.cli.remote — remote session CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.remote import app

runner = CliRunner()


class TestRemoteLs:
    def test_ls_no_hosts(self, mock_dirs: tuple[Path, Path]) -> None:
        result = runner.invoke(app, ["ls"])
        assert result.exit_code == 0
        assert "No remote hosts configured" in result.stdout

    def test_ls_with_hosts(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(app, ["ls"])
        assert result.exit_code == 0
        assert "devbox" in result.stdout
        assert "devbox.local" in result.stdout

    def test_ls_connected_host(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.read_tunnel_port", return_value=12345),
        ):
            result = runner.invoke(app, ["ls"])
        assert result.exit_code == 0
        assert "connected" in result.stdout

    def test_ls_plain_no_hosts(self, mock_dirs: tuple[Path, Path]) -> None:
        result = runner.invoke(app, ["ls", "--format", "plain"])
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_ls_plain_with_hosts(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing
            + '\n[remote.devbox]\nhost = "devbox.local"\n'
            + '\n[remote.alpha]\nhost = "alpha.local"\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        result = runner.invoke(app, ["ls", "--format", "plain"])
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert lines == ["alpha", "devbox"]


class TestRemoteConnect:
    def test_connect_unknown_host(self, mock_dirs: tuple[Path, Path]) -> None:
        result = runner.invoke(app, ["connect", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown remote host" in result.stdout

    def test_connect_already_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.read_tunnel_port", return_value=12345),
        ):
            result = runner.invoke(app, ["connect", "devbox"])
        assert result.exit_code == 0
        assert "Already connected" in result.stdout

    def test_connect_success(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=False),
            patch("shoal.cli.remote.start_tunnel", return_value=12345),
        ):
            result = runner.invoke(app, ["connect", "devbox"])
        assert result.exit_code == 0
        assert "Connected" in result.stdout
        assert "12345" in result.stdout

    def test_connect_failure(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=False),
            patch("shoal.cli.remote.start_tunnel", side_effect=RuntimeError("Connection refused")),
        ):
            result = runner.invoke(app, ["connect", "devbox"])
        assert result.exit_code == 1
        assert "Connection refused" in result.stdout


class TestRemoteDisconnect:
    def test_disconnect_not_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(app, ["disconnect", "devbox"])
        assert result.exit_code == 0
        assert "Not connected" in result.stdout

    def test_disconnect_success(self, mock_dirs: tuple[Path, Path]) -> None:
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.stop_tunnel", return_value=True),
        ):
            result = runner.invoke(app, ["disconnect", "devbox"])
        assert result.exit_code == 0
        assert "Disconnected" in result.stdout


class TestRemoteStatus:
    def test_status_not_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(app, ["status", "devbox"])
        assert result.exit_code == 1
        assert "Not connected" in result.stdout

    def test_status_success(self, mock_dirs: tuple[Path, Path]) -> None:
        mock_data = {
            "total": 3,
            "running": 2,
            "waiting": 1,
            "error": 0,
            "idle": 0,
            "stopped": 0,
            "unknown": 0,
            "version": "0.16.0",
        }
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_data),
        ):
            result = runner.invoke(app, ["status", "devbox"])
        assert result.exit_code == 0
        assert "devbox" in result.stdout


class TestRemoteSessions:
    def test_sessions_not_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(app, ["sessions", "devbox"])
        assert result.exit_code == 1

    def test_sessions_empty(self, mock_dirs: tuple[Path, Path]) -> None:
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=[]),
        ):
            result = runner.invoke(app, ["sessions", "devbox"])
        assert result.exit_code == 0
        assert "No sessions" in result.stdout

    def test_sessions_success(self, mock_dirs: tuple[Path, Path]) -> None:
        mock_sessions = [
            {
                "id": "abc12345",
                "name": "feature-ui",
                "tool": "claude",
                "status": "running",
                "branch": "feature-ui",
            },
        ]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
        ):
            result = runner.invoke(app, ["sessions", "devbox"])
        assert result.exit_code == 0
        assert "feature-ui" in result.stdout

    def test_sessions_plain_empty(self, mock_dirs: tuple[Path, Path]) -> None:
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=[]),
        ):
            result = runner.invoke(app, ["sessions", "devbox", "--format", "plain"])
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_sessions_plain_with_sessions(self, mock_dirs: tuple[Path, Path]) -> None:
        mock_sessions = [
            {"id": "abc12345", "name": "feature-ui", "tool": "claude", "status": "running"},
            {"id": "def67890", "name": "api-work", "tool": "pi", "status": "idle"},
        ]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
        ):
            result = runner.invoke(app, ["sessions", "devbox", "--format", "plain"])
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert lines == ["api-work", "feature-ui"]


class TestRemoteSend:
    def test_send_success(self, mock_dirs: tuple[Path, Path]) -> None:
        mock_sessions = [{"id": "abc12345", "name": "my-session"}]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
            patch("shoal.cli.remote.remote_api_post", return_value={"ok": True}),
        ):
            result = runner.invoke(app, ["send", "devbox", "my-session", "y"])
        assert result.exit_code == 0
        assert "Sent keys" in result.stdout

    def test_send_session_not_found(self, mock_dirs: tuple[Path, Path]) -> None:
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=[]),
        ):
            result = runner.invoke(app, ["send", "devbox", "nonexistent", "y"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestRemoteDefault:
    def test_default_shows_ls(self, mock_dirs: tuple[Path, Path]) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "No remote hosts configured" in result.stdout
