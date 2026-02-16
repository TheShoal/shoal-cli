"""Tmux subprocess wrappers.

Note: All functions in this module are synchronous subprocess calls.
For async tmux operations, use the async wrapper functions in state.py.
"""

from __future__ import annotations

import os
import shlex
import subprocess


def _run(
    args: list[str], *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["tmux", *args],
        capture_output=capture,
        text=True,
        check=check,
    )


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


def capture_pane(target: str, lines: int = 20) -> str:
    result = _run(["capture-pane", "-t", target, "-p", "-S", f"-{lines}"], check=False)
    return result.stdout if result.returncode == 0 else ""


def pane_pid(target: str) -> int | None:
    result = _run(["display-message", "-t", target, "-p", "#{pane_pid}"], check=False)
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


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
