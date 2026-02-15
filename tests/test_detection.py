"""Tests for core/detection.py — pure status detection."""

from shoal.core.detection import detect_status
from shoal.models.config import DetectionPatterns, ToolConfig
from shoal.models.state import SessionStatus


def _make_tool(**kwargs) -> ToolConfig:
    return ToolConfig(
        name="test",
        command="test",
        detection=DetectionPatterns(**kwargs),
    )


class TestDetectStatus:
    def test_empty_content(self):
        tool = _make_tool(busy_patterns=["thinking"])
        assert detect_status("", tool) == SessionStatus.idle
        assert detect_status("   \n  ", tool) == SessionStatus.idle

    def test_error_highest_priority(self):
        tool = _make_tool(
            error_patterns=["Error:"],
            waiting_patterns=["Allow"],
            busy_patterns=["thinking"],
        )
        # Content has all patterns — error should win
        content = "Error: something failed\nAllow this action?\nthinking..."
        assert detect_status(content, tool) == SessionStatus.error

    def test_waiting_over_busy(self):
        tool = _make_tool(
            error_patterns=["FATAL"],
            waiting_patterns=["Allow"],
            busy_patterns=["thinking"],
        )
        content = "Allow this?\nthinking about it"
        assert detect_status(content, tool) == SessionStatus.waiting

    def test_busy(self):
        tool = _make_tool(
            error_patterns=["FATAL"],
            waiting_patterns=["Allow"],
            busy_patterns=["⠋", "thinking"],
        )
        content = "⠋ Processing files..."
        assert detect_status(content, tool) == SessionStatus.running

    def test_idle_fallback(self):
        tool = _make_tool(
            error_patterns=["FATAL"],
            waiting_patterns=["Allow"],
            busy_patterns=["thinking"],
        )
        content = "$ ls\nfile1.txt  file2.txt"
        assert detect_status(content, tool) == SessionStatus.idle

    def test_no_patterns_is_idle(self):
        tool = _make_tool()
        content = "anything here"
        assert detect_status(content, tool) == SessionStatus.idle

    def test_claude_spinner_detection(self):
        tool = _make_tool(busy_patterns=["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        for spinner in ["⠋", "⠙", "⠹"]:
            assert detect_status(f"{spinner} Generating code...", tool) == SessionStatus.running

    def test_claude_permission_detection(self):
        tool = _make_tool(waiting_patterns=["Yes/No", "Allow", "Deny"])
        assert detect_status("Allow this bash command? Yes/No", tool) == SessionStatus.waiting
