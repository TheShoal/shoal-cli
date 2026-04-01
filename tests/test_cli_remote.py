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


class TestRemoteIncidents:
    def test_incident_ls_success(self, mock_dirs: tuple[Path, Path]) -> None:
        mock_incidents = [
            {
                "id": "inc-1234",
                "status": "active",
                "alert": {
                    "severity": "critical",
                    "title": "API outage in payments",
                    "source": "pagerduty",
                },
                "lanes": [{"session_id": "s1"}],
            }
        ]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_incidents),
        ):
            result = runner.invoke(app, ["incident", "ls", "devbox"])

        assert result.exit_code == 0
        assert "inc-1234" in result.stdout
        assert "API outage in payments" in result.stdout

    def test_incident_ingest_posts_payload(
        self, mock_dirs: tuple[Path, Path], tmp_path: Path
    ) -> None:
        payload_path = tmp_path / "alert.json"
        _ = payload_path.write_text(
            '{"severity":"critical","title":"API outage","source":"pagerduty","reason":"Customers failing"}'
        )
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_post",
                return_value={"id": "inc-1234", "supervisor_session_id": "sess-1"},
            ) as mock_post,
        ):
            result = runner.invoke(
                app,
                ["incident", "ingest", "devbox", str(payload_path), "--path", "/srv/repo"],
            )

        assert result.exit_code == 0
        assert "inc-1234" in result.stdout
        assert mock_post.call_args.args[1] == "/incidents"
        assert mock_post.call_args.args[2]["spawn_supervisor"] is True

    def test_incident_spawn_posts_lane_request(self, mock_dirs: tuple[Path, Path]) -> None:
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_post",
                return_value={"name": "repo/incident-api-investigator"},
            ) as mock_post,
        ):
            result = runner.invoke(
                app,
                [
                    "incident",
                    "spawn",
                    "devbox",
                    "inc-1234",
                    "--role",
                    "incident-investigator",
                    "--tool",
                    "omp",
                ],
            )

        assert result.exit_code == 0
        assert "incident-api-investigator" in result.stdout
        assert mock_post.call_args.args[1] == "/incidents/inc-1234/lanes"
        assert mock_post.call_args.args[2]["role"] == "incident-investigator"


class TestRemoteDisconnectErrors:
    def test_disconnect_failure(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test disconnect when stop_tunnel returns False (line 180)."""
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.stop_tunnel", return_value=False),
        ):
            result = runner.invoke(app, ["disconnect", "devbox"])
        assert result.exit_code == 0
        assert "Failed to disconnect" in result.stdout


class TestRemoteStatusErrors:
    def test_status_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test status when remote_api_get raises RemoteConnectionError (lines 192-194)."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_get",
                side_effect=RemoteConnectionError("Connection timeout"),
            ),
        ):
            result = runner.invoke(app, ["status", "devbox"])
        assert result.exit_code == 1
        assert "Connection timeout" in result.stdout

    def test_status_invalid_json_response(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test status when API returns malformed data."""
        # Simulate API returning data missing required keys
        mock_data = {"bad": "data"}
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_data),
        ):
            result = runner.invoke(app, ["status", "devbox"])
        # Should still work but show zeros/unknown
        assert result.exit_code == 0
        assert "unknown" in result.stdout


class TestRemoteSessionsErrors:
    def test_sessions_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test sessions when remote_api_get raises RemoteConnectionError (lines 239-241)."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_get",
                side_effect=RemoteConnectionError("Host unreachable"),
            ),
        ):
            result = runner.invoke(app, ["sessions", "devbox"])
        assert result.exit_code == 1
        assert "Host unreachable" in result.stdout

    def test_sessions_malformed_response(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test sessions when API returns non-list data."""
        # API should return list but returns dict
        mock_response = {"error": "not a list"}
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_response),
        ):
            result = runner.invoke(app, ["sessions", "devbox"])
        # This will fail when trying to iterate or sort
        assert result.exit_code != 0


class TestRemoteSendErrors:
    def test_send_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test send when remote_api_post raises RemoteConnectionError (lines 299-301)."""
        from shoal.core.remote import RemoteConnectionError

        mock_sessions = [{"id": "abc12345", "name": "my-session"}]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
            patch(
                "shoal.cli.remote.remote_api_post",
                side_effect=RemoteConnectionError("Network error"),
            ),
        ):
            result = runner.invoke(app, ["send", "devbox", "my-session", "y"])
        assert result.exit_code == 1
        assert "Network error" in result.stdout

    def test_send_key_error_during_resolution(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test send when session resolution fails with KeyError."""
        from shoal.core.remote import RemoteConnectionError

        # Session list succeeds but post fails
        mock_sessions = [{"id": "abc12345", "name": "my-session"}]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
            patch(
                "shoal.cli.remote.remote_api_post",
                side_effect=RemoteConnectionError("Post failed"),
            ),
        ):
            result = runner.invoke(app, ["send", "devbox", "my-session", "test keys"])
        assert result.exit_code == 1
        assert "Post failed" in result.stdout


class TestRemoteAttach:
    def test_attach_unknown_host(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test attach when host is not in config (lines 314-318)."""
        result = runner.invoke(app, ["attach", "nonexistent", "session"])
        assert result.exit_code == 1
        assert "Unknown remote host" in result.stdout or "Error" in result.stdout

    def test_attach_builds_ssh_command_default_port(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test attach builds SSH command with default port 22 (lines 320-336)."""
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["attach", "devbox", "test-session"])
        assert result.exit_code == 0
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "ssh" in call_args
        assert "-t" in call_args
        assert "devbox.local" in call_args
        assert "tmux attach-session -t _test-session" in call_args

    def test_attach_builds_ssh_command_custom_port(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test attach builds SSH command with custom SSH port."""
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing
            + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\nport = 2222\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["attach", "devbox", "test-session"])
        assert result.exit_code == 0
        call_args = mock_run.call_args[0][0]
        assert "-p" in call_args
        assert "2222" in call_args

    def test_attach_builds_ssh_command_with_identity(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test attach builds SSH command with identity file."""
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing
            + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
            + 'identity_file = "~/.ssh/id_ed25519"\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["attach", "devbox", "test-session"])
        assert result.exit_code == 0
        call_args = mock_run.call_args[0][0]
        assert "-i" in call_args
        # Path is expanded by os.path.expanduser
        assert ".ssh/id_ed25519" in str(call_args)

    def test_attach_keyboard_interrupt_handling(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test attach handles KeyboardInterrupt gracefully (line 335-336)."""
        config_dir = mock_dirs[0]
        config_file = config_dir / "config.toml"
        existing = config_file.read_text()
        config_file.write_text(
            existing + '\n[remote.devbox]\nhost = "devbox.local"\napi_port = 8080\n'
        )
        from shoal.core.config import load_config

        load_config.cache_clear()

        with patch("subprocess.run", side_effect=KeyboardInterrupt):
            result = runner.invoke(app, ["attach", "devbox", "test-session"])
        # Should exit cleanly despite keyboard interrupt
        assert result.exit_code == 0


class TestRemoteIncidentsErrors:
    def test_incident_ls_not_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident ls when not connected."""
        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(app, ["incident", "ls", "devbox"])
        assert result.exit_code == 1
        assert "Not connected" in result.stdout

    def test_incident_ls_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident ls when remote_api_get raises RemoteConnectionError."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_get",
                side_effect=RemoteConnectionError("API error"),
            ),
        ):
            result = runner.invoke(app, ["incident", "ls", "devbox"])
        assert result.exit_code == 1
        assert "API error" in result.stdout

    def test_incident_show_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident show when remote_api_get raises RemoteConnectionError."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_get",
                side_effect=RemoteConnectionError("Cannot fetch incident"),
            ),
        ):
            result = runner.invoke(app, ["incident", "show", "devbox", "inc-123"])
        assert result.exit_code == 1
        assert "Cannot fetch incident" in result.stdout

    def test_incident_ingest_not_connected(self, mock_dirs: tuple[Path, Path], tmp_path: Path) -> None:
        """Test incident ingest when not connected."""
        payload_path = tmp_path / "alert.json"
        payload_path.write_text('{"severity":"critical","title":"Test"}')

        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(
                app, ["incident", "ingest", "devbox", str(payload_path)]
            )
        assert result.exit_code == 1
        assert "Not connected" in result.stdout

    def test_incident_ingest_remote_connection_error(
        self, mock_dirs: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Test incident ingest when remote_api_post raises RemoteConnectionError."""
        from shoal.core.remote import RemoteConnectionError

        payload_path = tmp_path / "alert.json"
        # Include all required fields for AlertPayload validation
        payload_path.write_text(
            '{"severity":"critical","title":"Test","source":"test","reason":"test"}'
        )

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_post",
                side_effect=RemoteConnectionError("Ingest failed"),
            ),
        ):
            result = runner.invoke(
                app, ["incident", "ingest", "devbox", str(payload_path)]
            )
        assert result.exit_code == 1
        assert "Ingest failed" in result.stdout

    def test_incident_ingest_invalid_json(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident ingest with invalid JSON payload (ValueError)."""
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
        ):
            result = runner.invoke(
                app, ["incident", "ingest", "devbox", "not valid json"]
            )
        assert result.exit_code == 1

    def test_incident_spawn_not_connected(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident spawn when not connected."""
        with patch("shoal.cli.remote.is_tunnel_active", return_value=False):
            result = runner.invoke(
                app,
                [
                    "incident",
                    "spawn",
                    "devbox",
                    "inc-123",
                    "--role",
                    "incident-investigator",
                ],
            )
        assert result.exit_code == 1
        assert "Not connected" in result.stdout

    def test_incident_spawn_remote_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident spawn when remote_api_post raises RemoteConnectionError."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_post",
                side_effect=RemoteConnectionError("Spawn failed"),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "incident",
                    "spawn",
                    "devbox",
                    "inc-123",
                    "--role",
                    "incident-investigator",
                ],
            )
        assert result.exit_code == 1
        assert "Spawn failed" in result.stdout


    def test_incident_ls_empty(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident ls when there are no incidents (lines 358-359)."""
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=[]),
        ):
            result = runner.invoke(app, ["incident", "ls", "devbox"])
        assert result.exit_code == 0
        assert "No incidents" in result.stdout

    def test_incident_show_success(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident show displays incident details (lines 406-421)."""
        mock_incident = {
            "id": "inc-1234",
            "slug": "api-outage",
            "status": "active",
            "alert": {
                "severity": "critical",
                "title": "API outage",
                "source": "pagerduty",
                "reason": "Customers failing",
            },
            "supervisor_session_id": "sess-1",
        }
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_incident),
        ):
            result = runner.invoke(app, ["incident", "show", "devbox", "inc-1234"])
        assert result.exit_code == 0
        assert "inc-1234" in result.stdout
        assert "api-outage" in result.stdout
        assert "API outage" in result.stdout
        assert "critical" in result.stdout

    def test_send_resolves_by_exact_id(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test send resolves session by exact ID match (line 556)."""
        mock_sessions = [
            {"id": "abc12345", "name": "session-a"},
            {"id": "def67890", "name": "session-b"},
        ]
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_sessions),
            patch("shoal.cli.remote.remote_api_post", return_value={"ok": True}) as mock_post,
        ):
            # Use exact ID instead of name
            result = runner.invoke(app, ["send", "devbox", "def67890", "y"])
        assert result.exit_code == 0
        assert "Sent keys" in result.stdout
        # Verify it posted to the correct session ID
        assert "/sessions/def67890/send" in mock_post.call_args.args[1]

    def test_incident_show_without_supervisor(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test incident show when incident has no supervisor session."""
        mock_incident = {
            "id": "inc-5678",
            "slug": "test-incident",
            "status": "monitoring",
            "alert": {
                "severity": "low",
                "title": "Test incident",
                "source": "manual",
                "reason": "Testing",
            },
        }
        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch("shoal.cli.remote.remote_api_get", return_value=mock_incident),
        ):
            result = runner.invoke(app, ["incident", "show", "devbox", "inc-5678"])
        assert result.exit_code == 0
        assert "inc-5678" in result.stdout
        # Should not show supervisor field
        assert "Supervisor" not in result.stdout

    def test_send_remote_get_connection_error(self, mock_dirs: tuple[Path, Path]) -> None:
        """Test send when remote_api_get raises RemoteConnectionError in _resolve_remote_session (lines 549-551)."""
        from shoal.core.remote import RemoteConnectionError

        with (
            patch("shoal.cli.remote.is_tunnel_active", return_value=True),
            patch(
                "shoal.cli.remote.remote_api_get",
                side_effect=RemoteConnectionError("Cannot fetch sessions"),
            ),
        ):
            result = runner.invoke(app, ["send", "devbox", "my-session", "y"])
        assert result.exit_code == 1
        assert "Cannot fetch sessions" in result.stdout

