"""Tests for core/detection.py — pure status detection."""

import pytest

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

    def test_regex_word_boundary(self):
        """Word boundary patterns should match whole words only."""
        tool = _make_tool(error_patterns=[r"\bError\b"])
        assert detect_status("Error: something broke", tool) == SessionStatus.error
        assert detect_status("InternalError raised", tool) == SessionStatus.idle

    def test_regex_anchor(self):
        """Anchor patterns should match at line boundaries."""
        tool = _make_tool(busy_patterns=[r"^thinking"])
        assert detect_status("thinking about code", tool) == SessionStatus.running
        assert detect_status("still thinking", tool) == SessionStatus.idle

    def test_regex_alternation(self):
        """Regex alternation should work in a single pattern."""
        tool = _make_tool(waiting_patterns=[r"Allow|Deny|Confirm"])
        assert detect_status("Confirm this action?", tool) == SessionStatus.waiting

    def test_invalid_regex_raises(self):
        """Invalid regex patterns should fail at model creation time."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            _make_tool(error_patterns=["[unclosed"])

    def test_compiled_patterns_accessible(self):
        """Pre-compiled patterns should be available on the model."""
        patterns = DetectionPatterns(
            error_patterns=["Error:"],
            busy_patterns=["thinking", "working"],
        )
        assert len(patterns._compiled_error) == 1
        assert len(patterns._compiled_busy) == 2
        assert len(patterns._compiled_waiting) == 0
