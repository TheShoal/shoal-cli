"""Tmux status bar segment generator — entry point for shoal-status."""

from __future__ import annotations

from shoal.core.config import load_tool_config, state_dir
from shoal.core.state import get_session, list_sessions


def generate_status() -> str:
    """Generate the tmux status-right segment string."""
    sessions_dir = state_dir() / "sessions"
    if not sessions_dir.exists():
        return ""

    segments: list[str] = []
    active = 0

    for sid in list_sessions():
        session = get_session(sid)
        if not session:
            continue

        if session.status.value == "stopped":
            continue

        active += 1

        try:
            icon = load_tool_config(session.tool).icon
        except FileNotFoundError:
            icon = "●"

        # Tmux color codes
        color_map = {
            "running": "#[fg=green]",
            "waiting": "#[fg=yellow,bold]",
            "error": "#[fg=red,bold]",
            "idle": "#[fg=white]",
        }
        color = color_map.get(session.status.value, "")
        reset = "#[default]"

        segments.append(f"{color}{icon} {session.name}:{session.status.value}{reset}")

    if active == 0:
        return ""

    output = "  ".join(segments)
    return f"{output}  #[fg=cyan]⚡ {active} active#[default]"


def main() -> None:
    """Entry point for shoal-status console script."""
    print(generate_status())


if __name__ == "__main__":
    main()
