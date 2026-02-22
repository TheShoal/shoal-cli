"""Tmux subprocess wrappers.

All core functions are synchronous (used by CLI directly).
``async_*`` variants wrap the sync functions via ``asyncio.to_thread()``
for use in async contexts (FastAPI routes, watcher, lifecycle service).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess


def _run(
    args: list[str], *, check: bool = True, capture: bool = True, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["tmux", *args],
            capture_output=capture,
            text=True,
            check=check,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        cmd_name = args[0] if args else "unknown"
        raise TimeoutError(f"tmux {cmd_name} timed out after {timeout}s") from None


def has_session(name: str) -> bool:
    result = _run(["has-session", "-t", name], check=False)
    return result.returncode == 0


def new_session(name: str, *, cwd: str | None = None) -> None:
    args = ["new-session", "-d", "-s", name]
    if cwd:
        args.extend(["-c", cwd])
    _run(args)


def kill_session(name: str) -> None:
    _run(["kill-session", "-t", name], check=False)


def rename_session(old_name: str, new_name: str) -> None:
    _run(["rename-session", "-t", old_name, new_name])


def set_environment(session: str, key: str, value: str) -> None:
    _run(["set-environment", "-t", session, key, value])


def send_keys(target: str, keys: str, *, enter: bool = True) -> None:
    args = ["send-keys", "-t", target, keys]
    if enter:
        args.append("Enter")
    _run(args)


def capture_pane(target: str, lines: int = 20, include_ansi: bool = False) -> str:
    args = ["capture-pane", "-t", target, "-p", "-S", f"-{lines}"]
    if include_ansi:
        args.append("-e")
    result = _run(args, check=False)
    return result.stdout if result.returncode == 0 else ""


def list_panes(target: str) -> list[dict[str, str]]:
    result = _run(
        [
            "list-panes",
            "-t",
            target,
            "-F",
            "#{pane_id}\t#{pane_title}\t#{pane_current_command}\t#{pane_active}",
        ],
        check=False,
    )
    if result.returncode != 0:
        return []
    panes: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        pane_id, title, command, active = parts
        panes.append(
            {
                "id": pane_id,
                "title": title,
                "command": command,
                "active": active,
            }
        )
    return panes


def preferred_pane(session: str, title: str | None = None) -> str:
    panes = list_panes(session)
    if title:
        for pane in panes:
            if pane["title"] == title:
                return pane["id"]
    for pane in panes:
        if pane["active"] == "1":
            return pane["id"]
    return session


def set_pane_title(target: str, title: str) -> None:
    _run(["select-pane", "-t", target, "-T", title], check=False)


def pane_pid(target: str) -> int | None:
    result = _run(["display-message", "-t", target, "-p", "#{pane_pid}"], check=False)
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


def pane_coordinates(target: str) -> tuple[str, str] | None:
    """Return tmux (session_id, window_id) for a pane/window target."""
    result = _run(
        ["display-message", "-t", target, "-p", "#{session_id}\t#{window_id}"],
        check=False,
    )
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split("\t")
    if len(parts) != 2:
        return None
    session_id, window_id = parts
    if not session_id or not window_id:
        return None
    return session_id, window_id


def switch_client(target: str) -> None:
    _run(["switch-client", "-t", target])


def attach_session(target: str) -> None:
    # attach needs the terminal, so don't capture output
    subprocess.run(["tmux", "attach-session", "-t", target], check=True)


def current_session_name() -> str | None:
    result = _run(["display-message", "-p", "#{session_name}"], check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def is_inside_tmux() -> bool:
    return "TMUX" in os.environ


def popup(command: str, *, width: str = "90%", height: str = "80%") -> None:
    _run(["popup", "-E", "-w", width, "-h", height, command], capture=False)


def detach_client() -> None:
    _run(["detach-client"])


def run_command(command: str) -> None:
    """Run a raw tmux command (e.g. 'new-window -n editor')."""
    _run(shlex.split(command))


# ---------------------------------------------------------------------------
# Async wrappers — for use in async contexts (lifecycle, watcher, API)
# ---------------------------------------------------------------------------


async def async_has_session(name: str) -> bool:
    return await asyncio.to_thread(has_session, name)


async def async_new_session(name: str, *, cwd: str | None = None) -> None:
    await asyncio.to_thread(new_session, name, cwd=cwd)


async def async_kill_session(name: str) -> None:
    await asyncio.to_thread(kill_session, name)


async def async_set_environment(session: str, key: str, value: str) -> None:
    await asyncio.to_thread(set_environment, session, key, value)


async def async_send_keys(target: str, keys: str, *, enter: bool = True) -> None:
    await asyncio.to_thread(send_keys, target, keys, enter=enter)


async def async_capture_pane(target: str, lines: int = 20, include_ansi: bool = False) -> str:
    return await asyncio.to_thread(capture_pane, target, lines, include_ansi)


async def async_list_panes(target: str) -> list[dict[str, str]]:
    return await asyncio.to_thread(list_panes, target)


async def async_preferred_pane(session: str, title: str | None = None) -> str:
    return await asyncio.to_thread(preferred_pane, session, title)


async def async_set_pane_title(target: str, title: str) -> None:
    await asyncio.to_thread(set_pane_title, target, title)


async def async_pane_pid(target: str) -> int | None:
    return await asyncio.to_thread(pane_pid, target)


async def async_pane_coordinates(target: str) -> tuple[str, str] | None:
    return await asyncio.to_thread(pane_coordinates, target)


async def async_run_command(command: str) -> None:
    await asyncio.to_thread(run_command, command)
