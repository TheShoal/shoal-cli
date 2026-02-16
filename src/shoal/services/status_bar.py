"""Tmux status bar segment generator — entry point for shoal-status."""

from __future__ import annotations

import asyncio

from shoal.core.state import get_session, list_sessions


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

    # Format segments: 3 chars wide total
    # Zero: "-  " (hyphen + two spaces)
    # Non-zero: "● 1" (icon + space + digit)
    def fmt(count: int, icon: str, color: str) -> str:
        if count == 0:
            return f"#[fg={color}]  "
        return f"#[fg={color}]{icon} {count}"

    # Only display active statuses (running, idle, waiting, error).
    # Stopped and unknown sessions are intentionally excluded from the status bar
    # because they represent inactive sessions and would add noise to the display.
    res = (
        fmt(counts["running"], " ", "green")
        + " "
        + fmt(counts["idle"], " ", "white")
        + " "
        + fmt(counts["waiting"], " ", "yellow")
        + " "
        + fmt(counts["error"], " ", "red")
    )
    return f"{res}#[default]"


def main() -> None:
    """Entry point for shoal-status console script."""
    from shoal.core.db import with_db

    print(asyncio.run(with_db(generate_status())))


if __name__ == "__main__":
    main()
