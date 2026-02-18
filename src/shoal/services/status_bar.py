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

    counts = {"running": 0, "idle": 0, "error": 0, "waiting": 0, "inactive": 0}

    for session in sessions:
        status_val = session.status.value
        if status_val in counts:
            counts[status_val] += 1
        elif status_val in ("stopped", "unknown"):
            counts["inactive"] += 1
        else:
            counts["inactive"] += 1

    # Build status segments for all 5 categories (running, idle, waiting, error, inactive).
    # Always show all segments for fixed-width consistency.
    segments = []
    for status_key in ["running", "idle", "waiting", "error", "inactive"]:
        count = counts[status_key]
        if status_key == "inactive":
            style = STATUS_STYLES["stopped"]  # Use stopped style for inactive
        else:
            style = STATUS_STYLES[status_key]
        segment = tmux_status_segment(
            icon=style.icon,
            count=count,
            color=style.tmux,
        )
        segments.append(segment)

    return " ".join(segments) + "#[default]"


def main() -> None:
    """Entry point for shoal-status console script."""
    from shoal.core.db import with_db

    print(asyncio.run(with_db(generate_status())))


if __name__ == "__main__":
    main()
