"""macOS notifications via osascript."""

from __future__ import annotations

import subprocess
import sys


def _escape_applescript_string(s: str) -> str:
    r"""Escape special characters for AppleScript string literals.
    
    AppleScript strings use backslash escaping for quotes and backslashes.
    We escape:
    - Backslash (\) -> \\
    - Double quote (") -> \"
    """
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str) -> None:
    """Send a macOS notification. No-op on non-Darwin platforms.

    Args:
        title: Notification title (will be escaped for AppleScript)
        message: Notification message (will be escaped for AppleScript)
    """
    if sys.platform != "darwin":
        return

    # Escape title and message to prevent injection
    safe_title = _escape_applescript_string(title)
    safe_message = _escape_applescript_string(message)

    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)
