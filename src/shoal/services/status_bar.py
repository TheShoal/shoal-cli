"""Tmux status bar segment generator — entry point for shoal-status."""

from __future__ import annotations

import asyncio
from shoal.core.config import state_dir
from shoal.core.state import get_session, list_sessions


async def generate_status() -> str:
    """Generate the tmux status-right segment string."""
    ids = await list_sessions()
    if not ids:
        return ""

    counts = {"running": 0, "idle": 0, "error": 0, "waiting": 0}

    for sid in ids:
        session = await get_session(sid)
        if not session:
            continue

        if session.status.value in counts:
            counts[session.status.value] += 1

    total = sum(counts.values())
    if total == 0:
        return ""

    return f"#[fg=green]● {counts['running']} #[fg=white]○ {counts['idle']} #[fg=red]● {counts['error']} #[fg=yellow]◉ {counts['waiting']}#[default]"


def main() -> None:
    """Entry point for shoal-status console script."""
    print(asyncio.run(generate_status()))


if __name__ == "__main__":
    main()
