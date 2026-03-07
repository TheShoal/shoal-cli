"""Tests for shoal.core.remote — SSH tunnel management and HTTP client."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

from shoal.core.remote import (
    RemoteConnectionError,
    _find_free_port,
    _pid_alive,
    _redact_ssh_cmd,
    is_tunnel_active,
    list_tunnels,
    read_tunnel_pid,
    read_tunnel_port,
    remote_api_get,
    remote_api_post,
    resolve_host,
    start_tunnel,
    stop_tunnel,
    tunnel_pid_file,
    tunnel_port_file,
)


@pytest.fixture
def remote_dir(tmp_path: Path) -> Path:
    """Create a temporary remote state directory."""
    d = tmp_path / "state" / "shoal" / "remote"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def _patch_remote_dir(remote_dir: Path):
    """Patch _remote_dir to use the temp directory."""
    with patch("shoal.core.remote._remote_dir", return_value=remote_dir):
        yield remote_dir


# --- PID/port file helpers ---


class TestTunnelFiles:
    def test_tunnel_pid_file_path(self, _patch_remote_dir: Path) -> None:
        pf = tunnel_pid_file("myhost")
        assert pf.name == "myhost.pid"
        assert pf.parent == _patch_remote_dir

    def test_tunnel_port_file_path(self, _patch_remote_dir: Path) -> None:
        pf = tunnel_port_file("myhost")
        assert pf.name == "myhost.port"
        assert pf.parent == _patch_remote_dir

    def test_read_tunnel_pid_not_found(self, _patch_remote_dir: Path) -> None:
        assert read_tunnel_pid("missing") is None

    def test_read_tunnel_pid_exists(self, _patch_remote_dir: Path) -> None:
        tunnel_pid_file("myhost").write_text("1234")
        assert read_tunnel_pid("myhost") == 1234

    def test_read_tunnel_pid_invalid(self, _patch_remote_dir: Path) -> None:
        tunnel_pid_file("myhost").write_text("not-a-number")
        assert read_tunnel_pid("myhost") is None

    def test_read_tunnel_port_not_found(self, _patch_remote_dir: Path) -> None:
        assert read_tunnel_port("missing") is None

    def test_read_tunnel_port_exists(self, _patch_remote_dir: Path) -> None:
        tunnel_port_file("myhost").write_text("9999")
        assert read_tunnel_port("myhost") == 9999


# --- Process alive check ---


class TestPidAlive:
    def test_pid_alive_current_process(self) -> None:
        assert _pid_alive(os.getpid()) is True

    def test_pid_alive_dead_process(self) -> None:
        assert _pid_alive(99999999) is False


# --- Tunnel active check ---


class TestIsTunnelActive:
    def test_no_pid_file(self, _patch_remote_dir: Path) -> None:
        assert is_tunnel_active("missing") is False

    def test_active_tunnel(self, _patch_remote_dir: Path) -> None:
        # Write current PID to simulate an active tunnel
        tunnel_pid_file("myhost").write_text(str(os.getpid()))
        tunnel_port_file("myhost").write_text("9999")
        assert is_tunnel_active("myhost") is True

    def test_stale_pid_cleaned_up(self, _patch_remote_dir: Path) -> None:
        # Write a dead PID
        tunnel_pid_file("myhost").write_text("99999999")
        tunnel_port_file("myhost").write_text("9999")
        assert is_tunnel_active("myhost") is False
        # Files should be cleaned up
        assert not tunnel_pid_file("myhost").exists()
        assert not tunnel_port_file("myhost").exists()


# --- Start tunnel ---


class TestStartTunnel:
    def test_start_tunnel_success(self, _patch_remote_dir: Path) -> None:
        with (
            patch("shoal.core.remote.subprocess.run") as mock_run,
            patch("shoal.core.remote._find_tunnel_pid", return_value=42),
            patch("shoal.core.remote._find_free_port", return_value=12345),
            patch("shoal.core.remote.time.sleep"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            port = start_tunnel(
                host="myhost",
                ssh_host="myhost.example.com",
                remote_port=8080,
            )

        assert port == 12345
        assert tunnel_pid_file("myhost").read_text() == "42"
        assert tunnel_port_file("myhost").read_text() == "12345"

    def test_start_tunnel_already_active(self, _patch_remote_dir: Path) -> None:
        # Simulate active tunnel
        tunnel_pid_file("myhost").write_text(str(os.getpid()))
        tunnel_port_file("myhost").write_text("9999")

        with pytest.raises(RuntimeError, match="already active"):
            start_tunnel(
                host="myhost",
                ssh_host="myhost.example.com",
                remote_port=8080,
            )

    def test_start_tunnel_ssh_failure(self, _patch_remote_dir: Path) -> None:
        import subprocess

        with (
            patch("shoal.core.remote.subprocess.run") as mock_run,
            patch("shoal.core.remote._find_free_port", return_value=12345),
        ):
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "ssh", stderr="Connection refused"
            )
            with pytest.raises(RuntimeError, match="failed"):
                start_tunnel(
                    host="myhost",
                    ssh_host="myhost.example.com",
                    remote_port=8080,
                )

    def test_start_tunnel_pid_not_found(self, _patch_remote_dir: Path) -> None:
        with (
            patch("shoal.core.remote.subprocess.run") as mock_run,
            patch("shoal.core.remote._find_tunnel_pid", return_value=None),
            patch("shoal.core.remote._find_free_port", return_value=12345),
            patch("shoal.core.remote.time.sleep"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            with pytest.raises(RuntimeError, match="PID not found"):
                start_tunnel(
                    host="myhost",
                    ssh_host="myhost.example.com",
                    remote_port=8080,
                )

    def test_start_tunnel_with_user_and_key(self, _patch_remote_dir: Path) -> None:
        with (
            patch("shoal.core.remote.subprocess.run") as mock_run,
            patch("shoal.core.remote._find_tunnel_pid", return_value=42),
            patch("shoal.core.remote._find_free_port", return_value=12345),
            patch("shoal.core.remote.time.sleep"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            start_tunnel(
                host="myhost",
                ssh_host="myhost.example.com",
                remote_port=8080,
                user="deploy",
                identity_file="~/.ssh/deploy_key",
                ssh_port=2222,
            )

        # Verify SSH command includes user, key, and port
        call_args = mock_run.call_args[0][0]
        assert "-p" in call_args
        assert "2222" in call_args
        assert "-i" in call_args
        assert "deploy@myhost.example.com" in call_args


# --- Stop tunnel ---


class TestStopTunnel:
    def test_stop_tunnel_not_running(self, _patch_remote_dir: Path) -> None:
        assert stop_tunnel("missing") is False

    def test_stop_tunnel_success(self, _patch_remote_dir: Path) -> None:
        tunnel_pid_file("myhost").write_text("99999999")
        tunnel_port_file("myhost").write_text("9999")

        with (
            patch("shoal.core.remote._pid_alive", return_value=True),
            patch("shoal.core.remote.os.kill") as mock_kill,
        ):
            result = stop_tunnel("myhost")

        assert result is True
        mock_kill.assert_called_once()
        assert not tunnel_pid_file("myhost").exists()
        assert not tunnel_port_file("myhost").exists()


# --- List tunnels ---


class TestListTunnels:
    def test_list_tunnels_empty(self, _patch_remote_dir: Path) -> None:
        assert list_tunnels() == []

    def test_list_tunnels_with_active(self, _patch_remote_dir: Path) -> None:
        # Create an "active" tunnel (use our own PID)
        tunnel_pid_file("myhost").write_text(str(os.getpid()))
        tunnel_port_file("myhost").write_text("9999")

        result = list_tunnels()
        assert len(result) == 1
        assert result[0][0] == "myhost"
        assert result[0][2] == 9999


# --- HTTP client helpers ---


class _MockHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for testing."""

    response_data: ClassVar[dict[str, Any]] = {"status": "ok"}
    status_code: ClassVar[int] = 200

    def do_GET(self) -> None:
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.response_data).encode())

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length:
            self.rfile.read(content_length)
        self.do_GET()

    def do_DELETE(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress log output


@pytest.fixture
def mock_server() -> tuple[HTTPServer, int]:
    """Start a mock HTTP server on a free port."""
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()


class TestRemoteApiGet:
    def test_get_success(
        self, _patch_remote_dir: Path, mock_server: tuple[HTTPServer, int]
    ) -> None:
        _, port = mock_server
        tunnel_port_file("myhost").write_text(str(port))

        result = remote_api_get("myhost", "/status")
        assert result == {"status": "ok"}

    def test_get_no_tunnel(self, _patch_remote_dir: Path) -> None:
        with pytest.raises(RemoteConnectionError, match="No active tunnel"):
            remote_api_get("missing", "/status")

    def test_get_connection_error(self, _patch_remote_dir: Path) -> None:
        # Point to a port nothing is listening on
        tunnel_port_file("myhost").write_text("1")

        with pytest.raises(RemoteConnectionError, match="Failed to connect"):
            remote_api_get("myhost", "/status")


class TestRemoteApiPost:
    def test_post_success(
        self, _patch_remote_dir: Path, mock_server: tuple[HTTPServer, int]
    ) -> None:
        _, port = mock_server
        tunnel_port_file("myhost").write_text(str(port))

        result = remote_api_post("myhost", "/sessions/abc/send", {"keys": "y"})
        assert result == {"status": "ok"}


# --- Resolve host ---


class TestResolveHost:
    def test_resolve_known_host(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )

        from shoal.core.config import load_config

        load_config.cache_clear()

        result = resolve_host("devbox")
        assert result["name"] == "devbox"
        assert result["host"] == "devbox.local"
        assert result["api_port"] == 8080

    def test_resolve_unknown_host(self, mock_dirs: tuple[Path, Path]) -> None:
        with pytest.raises(KeyError, match="Unknown remote host"):
            resolve_host("nonexistent")


# --- find_free_port ---


class TestRedactSshCmd:
    def test_redacts_identity_file(self) -> None:
        cmd = ["ssh", "-i", "/home/user/.ssh/secret_key", "host.example.com"]
        result = _redact_ssh_cmd(cmd)
        assert "<redacted>" in result
        assert "secret_key" not in result
        assert "-i" in result

    def test_passthrough_when_no_identity(self) -> None:
        cmd = ["ssh", "-N", "-L", "8080:localhost:8080", "host.example.com"]
        result = _redact_ssh_cmd(cmd)
        assert result == "ssh -N -L 8080:localhost:8080 host.example.com"

    def test_identity_flag_at_end_of_args(self) -> None:
        cmd = ["ssh", "-N", "-i"]
        result = _redact_ssh_cmd(cmd)
        assert result == "ssh -N -i"


class TestFindFreePort:
    def test_returns_valid_port(self) -> None:
        port = _find_free_port()
        assert 1 <= port <= 65535
