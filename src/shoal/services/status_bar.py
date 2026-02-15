"""Tmux status bar segment generator — entry point for shoal-status."""

from __future__ import annotations

from shoal.core.config import load_tool_config, state_dir
from shoal.core.state import get_session, list_sessions


def generate_status() -> str:
    """Generate the tmux status-right segment string."""
    sessions_dir = state_dir() / "sessions"
    if not sessions_dir.exists():
        return ""

    counts = {"running": 0, "idle": 0, "error": 0, "waiting": 0}

    for sid in list_sessions():
        session = get_session(sid)
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
    print(generate_status())


if __name__ == "__main__":
    main()
