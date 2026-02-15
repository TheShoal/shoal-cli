"""macOS notifications via osascript."""

from __future__ import annotations

import subprocess
import sys


def notify(title: str, message: str) -> None:
    """Send a macOS notification. No-op on non-Darwin platforms."""
    if sys.platform != "darwin":
        return
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)
