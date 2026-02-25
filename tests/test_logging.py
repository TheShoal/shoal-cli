"""Tests for logging instrumentation across modules."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest


class TestTmuxLogging:
    """Verify tmux._run() emits DEBUG log with command text."""

    def test_run_logs_command(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="shoal.tmux"),
            patch("shoal.core.tmux.subprocess.run") as mock_run,
        ):
            from shoal.core.tmux import _run

            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            _run(["has-session", "-t", "test"], check=False)

        assert any("tmux has-session -t test" in r.message for r in caplog.records)


class TestGitLogging:
    """Verify git._run() emits DEBUG log with command and cwd."""

    def test_run_logs_command(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="shoal.git"),
            patch("shoal.core.git.subprocess.run") as mock_run,
        ):
            from shoal.core.git import _run

            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            _run(["status"], cwd="/tmp", check=False)

        assert any("git status" in r.message and "/tmp" in r.message for r in caplog.records)


class TestDetectionLogging:
    """Verify detect_status emits DEBUG log."""

    def test_detect_status_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        from shoal.core.detection import detect_status
        from shoal.models.config import DetectionPatterns, MCPToolConfig, ToolConfig

        tool = ToolConfig(
            name="test",
            command="test",
            icon="T",
            detection=DetectionPatterns(),
            mcp=MCPToolConfig(),
        )

        with caplog.at_level(logging.DEBUG, logger="shoal.detection"):
            detect_status("some content", tool)

        assert any("detect_status" in r.message and "test" in r.message for r in caplog.records)


class TestDbLogging:
    """Verify DB operations emit DEBUG logs with timing."""

    @pytest.mark.asyncio
    async def test_save_session_logs(
        self, caplog: pytest.LogCaptureFixture, mock_dirs: object
    ) -> None:
        from shoal.core.state import create_session

        with caplog.at_level(logging.DEBUG, logger="shoal.db"):
            await create_session("log-test", "claude", "/tmp/test")

        assert any("save_session" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_list_sessions_logs_timing(
        self, caplog: pytest.LogCaptureFixture, mock_dirs: object
    ) -> None:
        from shoal.core.state import create_session, list_sessions

        await create_session("timing-test", "claude", "/tmp/test")

        with caplog.at_level(logging.DEBUG, logger="shoal.db"):
            await list_sessions()

        assert any("list_sessions" in r.message and "ms" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_get_session_logs_timing(
        self, caplog: pytest.LogCaptureFixture, mock_dirs: object
    ) -> None:
        from shoal.core.state import create_session, get_session

        s = await create_session("get-timing", "claude", "/tmp/test")

        with caplog.at_level(logging.DEBUG, logger="shoal.db"):
            await get_session(s.id)

        assert any("get_session" in r.message and "ms" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_delete_session_logs_timing(
        self, caplog: pytest.LogCaptureFixture, mock_dirs: object
    ) -> None:
        from shoal.core.state import create_session, delete_session

        s = await create_session("del-timing", "claude", "/tmp/test")

        with caplog.at_level(logging.DEBUG, logger="shoal.db"):
            await delete_session(s.id)

        assert any("delete_session" in r.message and "ms" in r.message for r in caplog.records)


class TestJsonFormatter:
    """Verify JsonFormatter produces valid JSON with expected fields."""

    def test_basic_output(self) -> None:
        from shoal.core.logging_config import JsonFormatter

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="shoal.test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "shoal.test"
        assert data["msg"] == "hello world"
        assert "ts" in data

    def test_context_fields_included(self) -> None:
        from shoal.core.logging_config import JsonFormatter

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="shoal.test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        # Simulate ContextFilter injecting fields
        record.session_id = "sid-123"  # type: ignore[attr-defined]
        record.request_id = "rid-456"  # type: ignore[attr-defined]

        output = formatter.format(record)
        data = json.loads(output)
        assert data["session_id"] == "sid-123"
        assert data["request_id"] == "rid-456"

    def test_error_field_on_exception(self) -> None:
        from shoal.core.logging_config import JsonFormatter

        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="shoal.test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )

        output = formatter.format(record)
        data = json.loads(output)
        assert data["error"] == "test error"


class TestConfigureLogging:
    """Verify configure_logging sets up the shoal logger correctly."""

    def test_configure_debug_level(self) -> None:
        from shoal.core.logging_config import configure_logging

        configure_logging(level="DEBUG")
        shoal_logger = logging.getLogger("shoal")
        assert shoal_logger.level == logging.DEBUG
        # Clean up
        shoal_logger.handlers.clear()

    def test_configure_json_formatter(self) -> None:
        from shoal.core.logging_config import JsonFormatter, configure_logging

        configure_logging(level="INFO", json_logs=True)
        shoal_logger = logging.getLogger("shoal")
        assert any(isinstance(h.formatter, JsonFormatter) for h in shoal_logger.handlers)
        # Clean up
        shoal_logger.handlers.clear()

    def test_configure_file_handler(self, tmp_path: object) -> None:
        from shoal.core.logging_config import configure_logging

        log_file = str(tmp_path) + "/test.log"  # type: ignore[operator]
        configure_logging(level="INFO", log_file=log_file)
        shoal_logger = logging.getLogger("shoal")
        assert any(isinstance(h, logging.FileHandler) for h in shoal_logger.handlers)
        # Clean up
        shoal_logger.handlers.clear()
