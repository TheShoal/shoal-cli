"""Tmux status bar segment generator — entry point for shoal-status."""

from __future__ import annotations

import asyncio

from shoal.core.state import list_sessions
from shoal.core.theme import STATUS_STYLES, tmux_status_segment


async def generate_status() -> str:
    """Generate the tmux status-right segment string."""
    sessions = await list_sessions()
    if not sessions:
        return ""

    counts = {"running": 0, "idle": 0, "error": 0, "waiting": 0, "stopped": 0, "unknown": 0}

    for session in sessions:
        status_val = session.status.value
        if status_val in counts:
            counts[status_val] += 1
        else:
            counts["unknown"] += 1

    # Build status segments for active statuses (running, idle, waiting, error).
    # Only include segments with non-zero counts to keep the status bar compact.
    # Stopped and unknown sessions are intentionally excluded from the status bar
    # because they represent inactive sessions and would add noise to the display.
    segments = []
    for status_key in ["running", "idle", "waiting", "error"]:
        count = counts[status_key]
        if count > 0:
            style = STATUS_STYLES[status_key]
            segment = tmux_status_segment(
                icon=style.icon,
                count=count,
                color=style.tmux,
            )
            segments.append(segment)

    if not segments:
        return ""

    return " ".join(segments) + "#[default]"


def main() -> None:
    """Entry point for shoal-status console script."""
    from shoal.core.db import with_db

    print(asyncio.run(with_db(generate_status())))


if __name__ == "__main__":
    main()
