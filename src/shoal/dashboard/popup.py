"""fzf-based tmux popup dashboard."""

from __future__ import annotations

import asyncio
import subprocess

from shoal.core import tmux
from shoal.core.config import load_tool_config
from shoal.core.state import get_session, list_sessions, _get_tool_icon


async def _build_entries() -> list[str]:
    """Build session list entries for fzf."""
    entries: list[str] = []
    sessions = await list_sessions()
    for session in sessions:
        icon = _get_tool_icon(session.tool)

        branch = session.branch or "-"
        if session.last_activity:
            last = session.last_activity.strftime("%H:%M")
        else:
            last = "-"
        status = session.status.value
        entries.append(
            f"{session.id}\t{icon} {session.name}\t{session.tool}\t{status}\t{branch}\t{last}"
        )
    return entries


def run_popup() -> None:
    """Run the interactive fzf dashboard."""
    from shoal.core.db import with_db

    entries = asyncio.run(with_db(_build_entries()))

    if not entries:
        print("No sessions. Create one with: shoal new")
        input("Press Enter to close...")
        return

    header = "SHOAL DASHBOARD — Enter: attach | ctrl-x: kill | esc: close"

    # We use 'shoal session-json' as a helper for previewing since we don't have .json files anymore
    fzf_args = [
        "fzf",
        "--delimiter=\t",
        "--with-nth=2,3,4,5,6",
        f"--header={header}",
        "--preview=shoal session-json {1}",
        "--preview-window=right:50%:wrap",
        "--bind=ctrl-x:execute-silent(shoal kill {1})+reload(shoal _popup-list)",
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
        from shoal.core.db import with_db

        selected_id = result.stdout.strip().split("\t")[0]
        s = asyncio.run(with_db(get_session(selected_id)))
        if s and tmux.has_session(s.tmux_session):
            tmux.switch_client(s.tmux_session)


def print_popup_list() -> None:
    """Print session list for fzf reload."""
    from shoal.core.db import with_db

    entries = asyncio.run(with_db(_build_entries()))
    for line in entries:
        print(line)
