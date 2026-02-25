"""Tests for Pydantic models."""

from datetime import UTC, datetime

from shoal.models.config import (
    DetectionPatterns,
    RoboProfileConfig,
    ShoalConfig,
    ToolConfig,
)
from shoal.models.state import RoboState, SessionState, SessionStatus


class TestShoalConfig:
    def test_defaults(self):
        cfg = ShoalConfig()
        assert cfg.general.default_tool == "opencode"
        assert cfg.tmux.session_prefix == "_"
        assert cfg.notifications.enabled is True
        assert cfg.robo.default_tool == "opencode"
        assert cfg.robo.session_prefix == "__"

    def test_override(self):
        cfg = ShoalConfig(general={"default_tool": "opencode"})
        assert cfg.general.default_tool == "opencode"


class TestToolConfig:
    def test_basic(self):
        cfg = ToolConfig(name="claude", command="claude", icon="🤖")
        assert cfg.name == "claude"
        assert cfg.detection.busy_patterns == []
        assert cfg.mcp.config_cmd == ""

    def test_with_detection(self):
        cfg = ToolConfig(
            name="claude",
            command="claude",
            detection=DetectionPatterns(
                busy_patterns=["thinking"],
                error_patterns=["Error:"],
            ),
        )
        assert cfg.detection.busy_patterns == ["thinking"]
        assert cfg.detection.error_patterns == ["Error:"]


class TestRoboProfileConfig:
    def test_defaults(self):
        cfg = RoboProfileConfig()
        assert cfg.name == "default"
        assert cfg.tool == "opencode"
        assert cfg.monitoring.poll_interval == 10
        assert cfg.escalation.notify is True
        assert cfg.tasks.log_file == "task-log.md"


class TestSessionStatus:
    def test_enum_values(self):
        assert SessionStatus.running == "running"
        assert SessionStatus.waiting == "waiting"
        assert SessionStatus.error == "error"
        assert SessionStatus.idle == "idle"
        assert SessionStatus.stopped == "stopped"

    def test_str_conversion(self):
        assert str(SessionStatus.running) == "running"


class TestSessionState:
    def test_create_and_serialize(self):
        now = datetime(2025, 1, 1, tzinfo=UTC)
        state = SessionState(
            id="abc12345",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            worktree="/tmp/repo/.worktrees/test",
            branch="feat/test",
            tmux_session="_abc12345",
            status=SessionStatus.running,
            created_at=now,
            last_activity=now,
        )
        assert state.id == "abc12345"
        assert state.status == SessionStatus.running

        # Round-trip JSON
        json_str = state.model_dump_json(indent=2)
        restored = SessionState.model_validate_json(json_str)
        assert restored.id == state.id
        assert restored.name == state.name
        assert restored.status == state.status

    def test_mcp_servers_default(self):
        state = SessionState(id="x", name="x", tool="claude", path="/tmp", tmux_session="_x")
        assert state.mcp_servers == []

    def test_model_copy(self):
        state = SessionState(id="x", name="x", tool="claude", path="/tmp", tmux_session="_x")
        updated = state.model_copy(update={"status": SessionStatus.waiting})
        assert updated.status == SessionStatus.waiting
        assert state.status == SessionStatus.idle  # original unchanged


class TestRoboState:
    def test_create(self):
        state = RoboState(
            name="default",
            tool="opencode",
            tmux_session="__default",
        )
        assert state.status == "running"
        json_str = state.model_dump_json()
        restored = RoboState.model_validate_json(json_str)
        assert restored.name == "default"
