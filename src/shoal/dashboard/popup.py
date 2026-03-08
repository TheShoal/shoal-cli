"""fzf-based tmux popup dashboard."""

from __future__ import annotations

import asyncio
import subprocess

from shoal.core import tmux
from shoal.core.state import _get_tool_icon, list_sessions
from shoal.core.theme import Symbols


async def _build_entries() -> tuple[list[str], dict[str, str]]:
    """Build session list entries for fzf and a lookup for tmux session names."""
    entries: list[str] = []
    lookup: dict[str, str] = {}
    sessions = await list_sessions()
    for session in sessions:
        icon = _get_tool_icon(session.tool)
        lookup[session.id] = session.tmux_session

        branch = session.branch or "-"
        last = session.last_activity.strftime("%H:%M") if session.last_activity else "-"
        status = session.status.value
        entries.append(
            f"{session.id}\t{icon} {session.name}\t{session.tool}\t{status}\t{branch}\t{last}"
        )
    return entries, lookup


def _build_fzf_args() -> list[str]:
    """Build the fzf argument list for the dashboard popup."""
    header = (
        "SHOAL DASHBOARD \u2014 Enter:attach ctrl-x:kill ctrl-a:approve"
        " ctrl-f:fork ctrl-w:waiting ctrl-r:reload esc:close"
    )
    return [
        "fzf",
        "--delimiter=\t",
        "--with-nth=2,3,4,5,6",
        f"--header={header}",
        "--preview=shoal session-json {1}",
        "--preview-window=right:50%:wrap",
        "--bind=ctrl-x:execute-silent(shoal kill {1})+reload(shoal _popup-list)",
        '--bind=ctrl-a:execute-silent(shoal send {1} "")+reload(shoal _popup-list)',
        "--bind=ctrl-f:execute-silent(shoal fork {1})+reload(shoal _popup-list)",
        "--bind=ctrl-r:reload(shoal _popup-list)",
        "--bind=ctrl-w:reload(shoal _popup-list | awk -F'\\t' '$4==\"waiting\"')",
        "--ansi",
        "--no-sort",
        "--layout=reverse",
        "--border=rounded",
        "--prompt=shoal> ",
        f"--pointer={Symbols.POINTER}",
        f"--marker={Symbols.MARKER}",
    ]


def run_popup() -> None:
    """Run the interactive fzf dashboard."""
    from shoal.core.db import with_db

    entries, lookup = asyncio.run(with_db(_build_entries()))

    if not entries:
        print("No sessions. Create one with: shoal new")
        input("Press Enter to close...")
        return

    fzf_args = _build_fzf_args()

    result = subprocess.run(
        fzf_args,
        input="\n".join(entries),
        capture_output=True,
        text=True,
    )

    if result.returncode == 0 and result.stdout.strip():
        selected_id = result.stdout.strip().split("\t")[0]
        tmux_session = lookup.get(selected_id)
        if tmux_session and tmux.has_session(tmux_session):
            tmux.switch_client(tmux_session)


def print_popup_list() -> None:
    """Print session list for fzf reload."""
    from shoal.core.db import with_db

    entries, _ = asyncio.run(with_db(_build_entries()))
    for line in entries:
        print(line)
