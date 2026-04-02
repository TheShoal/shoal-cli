"""Tests for services/status_bar.py."""

import json
import urllib.error

import pytest

from shoal.models.state import SessionStatus
from shoal.services.status_bar import generate_status


class TestGenerateStatus:
    @pytest.mark.asyncio
    async def test_empty(self, mock_dirs):
        result = await generate_status()
        assert result == {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    @pytest.mark.asyncio
    async def test_with_sessions(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("test-session", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 1
        assert result["idle"] == 0

    @pytest.mark.asyncio
    async def test_stopped_contributes_to_inactive(self, mock_dirs):
        """Stopped sessions count toward the inactive category."""
        from shoal.core.state import create_session, update_session

        s = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result["inactive"] == 1

    @pytest.mark.asyncio
    async def test_all_same_status(self, mock_dirs):
        """Multiple sessions with the same status are counted correctly."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.running)
        s2 = await create_session("s2", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 2
        assert result["idle"] == 0
        assert result["waiting"] == 0
        assert result["error"] == 0
        assert result["inactive"] == 0

    @pytest.mark.asyncio
    async def test_large_session_count(self, mock_dirs):
        """Status bar should correctly handle large session counts."""
        from shoal.core.state import create_session, update_session

        for i in range(100):
            s = await create_session(f"s{i}", "claude", "/tmp")
            await update_session(s.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 100

    @pytest.mark.asyncio
    async def test_all_stopped(self, mock_dirs):
        """All stopped sessions count as inactive."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("s1", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result["inactive"] == 1
        assert result["running"] == 0

    @pytest.mark.asyncio
    async def test_waiting_counted(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.waiting)

        result = await generate_status()
        assert result["waiting"] == 1

    @pytest.mark.asyncio
    async def test_multiple_mixed_statuses(self, mock_dirs):
        """Status counts are correct across different states."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("running-one", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.running)

        s2 = await create_session("running-two", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        s3 = await create_session("idle-one", "claude", "/tmp")
        await update_session(s3.id, status=SessionStatus.idle)

        s4 = await create_session("error-one", "claude", "/tmp")
        await update_session(s4.id, status=SessionStatus.error)

        s5 = await create_session("waiting-one", "claude", "/tmp")
        await update_session(s5.id, status=SessionStatus.waiting)

        s6 = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s6.id, status=SessionStatus.stopped)

        result = await generate_status()
        assert result == {"running": 2, "idle": 1, "waiting": 1, "error": 1, "inactive": 1}

    @pytest.mark.asyncio
    async def test_stopped_shows_as_inactive(self, mock_dirs):
        """Stopped sessions count toward inactive, not their own category."""
        from shoal.core.state import create_session, update_session

        s1 = await create_session("stopped-one", "claude", "/tmp")
        await update_session(s1.id, status=SessionStatus.stopped)

        s2 = await create_session("running-one", "claude", "/tmp")
        await update_session(s2.id, status=SessionStatus.running)

        result = await generate_status()
        assert result["running"] == 1
        assert result["inactive"] == 1
        assert result["idle"] == 0


class TestGenerateRemoteStatus:
    """Unit tests for generate_remote_status() — no network calls."""

    def _make_response(self, payload: dict) -> object:
        """Build a fake urllib response context manager."""
        from unittest.mock import MagicMock

        body = json.dumps(payload).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_success_maps_fields(self) -> None:
        """Successful response maps all StatusResponse fields correctly."""
        from unittest.mock import patch

        from shoal.services.status_bar import generate_remote_status

        payload = {
            "total": 5,
            "running": 2,
            "idle": 1,
            "waiting": 1,
            "error": 0,
            "stopped": 1,
            "unknown": 0,
            "version": "0.34.0",
        }
        with patch("urllib.request.urlopen", return_value=self._make_response(payload)):
            result = generate_remote_status("remote-host", 8080)

        assert result == {"running": 2, "idle": 1, "waiting": 1, "error": 0, "inactive": 1}

    def test_stopped_and_unknown_both_go_to_inactive(self) -> None:
        """Both stopped and unknown counts are summed into inactive."""
        from unittest.mock import patch

        from shoal.services.status_bar import generate_remote_status

        payload = {
            "total": 4,
            "running": 1,
            "idle": 0,
            "waiting": 0,
            "error": 0,
            "stopped": 2,
            "unknown": 1,
            "version": "0.34.0",
        }
        with patch("urllib.request.urlopen", return_value=self._make_response(payload)):
            result = generate_remote_status("host", 8080)

        assert result["inactive"] == 3
        assert result["running"] == 1

    def test_connection_error_returns_zeros(self) -> None:
        """URLError during request returns all-zero counts instead of raising."""
        from unittest.mock import patch

        from shoal.services.status_bar import generate_remote_status

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = generate_remote_status("dead-host", 9999)

        assert result == {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    def test_unexpected_error_returns_zeros(self) -> None:
        """Any non-URL exception also returns zero counts safely."""
        from unittest.mock import patch

        from shoal.services.status_bar import generate_remote_status

        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = generate_remote_status("host", 8080)

        assert result == {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    def test_correct_url_constructed(self) -> None:
        """The HTTP request targets the correct /status endpoint URL."""
        from unittest.mock import call, patch

        from shoal.services.status_bar import generate_remote_status

        payload = {"running": 0, "idle": 0, "waiting": 0, "error": 0, "stopped": 0, "unknown": 0}
        with patch(
            "urllib.request.urlopen", return_value=self._make_response(payload)
        ) as mock_open:
            generate_remote_status("10.0.0.1", 9000)

        assert mock_open.call_args == call("http://10.0.0.1:9000/status", timeout=5)


class TestMain:
    """Unit tests for the main() entry point argument parsing."""

    def test_no_args_uses_local_db(self) -> None:
        """Calling main() with no args prints local DB counts as JSON."""
        from unittest.mock import patch

        from shoal.services.status_bar import main

        counts = {"running": 3, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}
        with (
            patch("sys.argv", ["shoal-status"]),
            patch("shoal.services.status_bar.asyncio") as mock_asyncio,
            patch("builtins.print") as mock_print,
        ):
            mock_asyncio.run.return_value = counts
            main()
            mock_print.assert_called_once_with(json.dumps(counts))

    def test_remote_flag_calls_generate_remote_status(self) -> None:
        """--remote <name> resolves the host from config and calls generate_remote_status."""
        from unittest.mock import MagicMock, patch

        from shoal.services.status_bar import main

        fake_cfg = MagicMock()
        fake_cfg.remote = {
            "prod": MagicMock(host="prod.example.com", api_port=8080),
        }
        expected = {"running": 1, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}
        with (
            patch("sys.argv", ["shoal-status", "--remote", "prod"]),
            patch("shoal.core.config.load_config", return_value=fake_cfg),
            patch(
                "shoal.services.status_bar.generate_remote_status", return_value=expected
            ) as mock_remote,
            patch("builtins.print") as mock_print,
        ):
            main()
            mock_remote.assert_called_once_with("prod.example.com", 8080)
            mock_print.assert_called_once_with(json.dumps(expected))

    def test_remote_flag_unknown_name_exits_1(self) -> None:
        """--remote with an unknown host name prints an error JSON and exits 1."""
        from unittest.mock import MagicMock, patch

        from shoal.services.status_bar import main

        fake_cfg = MagicMock()
        fake_cfg.remote = {}
        with (
            patch("sys.argv", ["shoal-status", "--remote", "nope"]),
            patch("shoal.core.config.load_config", return_value=fake_cfg),
            patch("builtins.print"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_remote_flag_missing_name_exits_1(self) -> None:
        """--remote with no following argument prints an error JSON and exits 1."""
        from unittest.mock import patch

        from shoal.services.status_bar import main

        with (
            patch("sys.argv", ["shoal-status", "--remote"]),
            patch("builtins.print"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
