"""Watcher daemon commands: start, stop, status."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from shoal.cli._console import get_console
from shoal.core.config import ensure_dirs, state_dir

app = typer.Typer(no_args_is_help=True)


def _pid_file() -> Path:
    return state_dir() / "watcher.pid"


def _read_pid() -> int | None:
    pf = _pid_file()
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)  # check if alive
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pf.unlink(missing_ok=True)
        return None


@app.command("start")
def watcher_start(
    foreground: Annotated[
        bool, typer.Option("--foreground", "-f", help="Run in foreground")
    ] = False,
) -> None:
    """Start the background status watcher."""
    ensure_dirs()

    import fcntl
    import os
    try:
        # Use O_CREAT | O_EXCL to atomically check and create
        lock_fd = os.open(_pid_file(), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        os.close(lock_fd)
    except FileExistsError:
        # File exists, maybe stale, so we can try flock.
        try:
            lock_fd = os.open(_pid_file(), os.O_RDWR)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # We got the lock, meaning the pidfile is stale.
            os.close(lock_fd)
        except (BlockingIOError, FileNotFoundError):
            existing = _read_pid()
            get_console().print(f"[red]Error: Watcher already running (pid: {existing})[/red]")
            get_console().print()
            get_console().print("[yellow]Actionable suggestions:[/yellow]")
            get_console().print("  • Check status: [bold]shoal watcher status[/bold]")
            get_console().print("  • Stop watcher: [bold]shoal watcher stop[/bold]")
            raise typer.Exit(1)

    if foreground:
        import asyncio
        import contextlib

        from shoal.core.db import with_db
        from shoal.services.watcher import Watcher

        watcher = Watcher()
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(with_db(watcher.run()))
    else:
        # Fork a background process
        proc = subprocess.Popen(
            [sys.executable, "-m", "shoal.services.watcher"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        get_console().print(f"Watcher started (pid: {proc.pid})")


@app.command("stop")
def watcher_stop() -> None:
    """Stop the background watcher."""
    pid = _read_pid()
    if not pid:
        get_console().print("[red]Error: Watcher is not running[/red]")
        get_console().print()
        get_console().print("[yellow]Actionable suggestions:[/yellow]")
        get_console().print("  • Start watcher: [bold]shoal watcher start[/bold]")
        raise typer.Exit(1)

    os.kill(pid, signal.SIGTERM)
    _pid_file().unlink(missing_ok=True)
    get_console().print(f"Watcher stopped (pid: {pid})")


@app.command("status")
def watcher_status() -> None:
    """Check watcher status."""
    pid = _read_pid()
    if pid:
        get_console().print(f"[green]Watcher is running (pid: {pid})[/green]")
    else:
        get_console().print("Watcher is not running")
