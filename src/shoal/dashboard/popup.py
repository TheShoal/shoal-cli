"""fzf-based tmux popup dashboard."""

from __future__ import annotations

import subprocess

from shoal.core import tmux
from shoal.core.config import load_tool_config, state_dir
from shoal.core.state import get_session, list_sessions


def _build_entries() -> list[str]:
    """Build session list entries for fzf."""
    entries: list[str] = []
    for sid in list_sessions():
        session = get_session(sid)
        if not session:
            continue

        try:
            icon = load_tool_config(session.tool).icon
        except FileNotFoundError:
            icon = "●"

        branch = session.branch or "-"
        if session.last_activity:
            last = session.last_activity.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            last = "-"
        status = session.status.value
        entries.append(
            f"{sid}\t{icon} {session.name}\t{session.tool}\t{status}\t{branch}\t{last}"
        )
    return entries


def run_popup() -> None:
    """Run the interactive fzf dashboard."""
    entries = _build_entries()

    if not entries:
        print("No sessions. Create one with: shoal add")
        input("Press Enter to close...")
        return

    sessions_dir = state_dir() / "sessions"

    header = "SHOAL DASHBOARD — Enter: attach | ctrl-k: kill | esc: close"

    fzf_args = [
        "fzf",
        "--delimiter=\t",
        "--with-nth=2,3,4,5,6",
        f"--header={header}",
        f"--preview=cat {sessions_dir}/{{1}}.json 2>/dev/null",
        "--preview-window=right:50%:wrap",
        "--bind=ctrl-k:execute-silent(shoal kill {1})+reload(shoal _popup-list)",
        "--ansi",
        "--no-sort",
        "--layout=reverse",
        "--border=rounded",
        "--prompt=shoal> ",
        "--pointer=▶",
        "--marker=●",
    ]

    result = subprocess.run(
        fzf_args,
        input="\n".join(entries),
        capture_output=True,
        text=True,
    )

    if result.returncode == 0 and result.stdout.strip():
        selected_id = result.stdout.strip().split("\t")[0]
        session = get_session(selected_id)
        if session and tmux.has_session(session.tmux_session):
            tmux.switch_client(session.tmux_session)


def print_popup_list() -> None:
    """Print session list for fzf reload."""
    for line in _build_entries():
        print(line)
