"""Tests for core/notify.py."""

from unittest.mock import patch

from shoal.core.notify import _escape_applescript_string, notify


def test_escape_applescript_string():
    """Test AppleScript string escaping logic."""
    assert _escape_applescript_string("hello") == "hello"
    assert _escape_applescript_string('said "hello"') == 'said \\"hello\\"'
    assert _escape_applescript_string("back\\slash") == "back\\\\slash"
    assert _escape_applescript_string('mix " \\') == 'mix \\" \\\\'


@patch("shoal.core.notify.subprocess.run")
def test_notify_darwin(mock_run):
    """Test notify on macOS (Darwin)."""
    with patch("shoal.core.notify.sys.platform", "darwin"):
        notify("Test Title", 'Test "Message"')

        mock_run.assert_called_once()
        args, _kwargs = mock_run.call_args
        assert args[0][0] == "osascript"
        assert args[0][1] == "-e"
        assert 'display notification "Test \\"Message\\"" with title "Test Title"' in args[0][2]


@patch("shoal.core.notify.subprocess.run")
def test_notify_non_darwin(mock_run):
    """Test notify on non-macOS (Linux/Windows)."""
    with patch("shoal.core.notify.sys.platform", "linux"):
        result = notify("Title", "Message")
        assert result is None
        mock_run.assert_not_called()
