"""Watcher daemon commands: start, stop, status."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import ensure_dirs, state_dir

console = Console()

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

    existing = _read_pid()
    if existing:
        console.print(f"[red]Error: Watcher already running (pid: {existing})[/red]")
        console.print()
        console.print("[yellow]Actionable suggestions:[/yellow]")
        console.print("  • Check status: [bold]shoal watcher status[/bold]")
        console.print("  • Stop watcher: [bold]shoal watcher stop[/bold]")
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
        console.print(f"Watcher started (pid: {proc.pid})")


@app.command("stop")
def watcher_stop() -> None:
    """Stop the background watcher."""
    pid = _read_pid()
    if not pid:
        console.print("[red]Error: Watcher is not running[/red]")
        console.print()
        console.print("[yellow]Actionable suggestions:[/yellow]")
        console.print("  • Start watcher: [bold]shoal watcher start[/bold]")
        raise typer.Exit(1)

    os.kill(pid, signal.SIGTERM)
    _pid_file().unlink(missing_ok=True)
    console.print(f"Watcher stopped (pid: {pid})")


@app.command("status")
def watcher_status() -> None:
    """Check watcher status."""
    pid = _read_pid()
    if pid:
        console.print(f"[green]Watcher is running (pid: {pid})[/green]")
    else:
        console.print("Watcher is not running")
