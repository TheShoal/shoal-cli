"""Diagnostics command — check Shoal component health."""

from __future__ import annotations

import json
import os

import typer
from rich.console import Console

from shoal.core.config import data_dir, state_dir
from shoal.core.theme import Icons, Symbols, create_panel, create_table


def _check_db() -> tuple[bool, str]:
    """Check if the SQLite database file exists and return its size."""
    db_path = data_dir() / "shoal.db"
    if not db_path.exists():
        return False, "not found"
    size_kb = db_path.stat().st_size / 1024
    return True, f"{size_kb:.1f} KB"


def _check_watcher() -> tuple[bool, str]:
    """Check if the watcher PID file exists and the process is alive."""
    pid_file = state_dir() / "watcher.pid"
    if not pid_file.exists():
        return False, "not running"
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True, f"pid {pid}"
    except (ValueError, ProcessLookupError):
        return False, "stale PID file"
    except PermissionError:
        return True, "pid (permission denied)"


def _check_tmux() -> tuple[bool, str]:
    """Check if tmux is reachable."""
    import subprocess

    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            count = len(result.stdout.strip().splitlines())
            return True, f"{count} session(s)"
        return True, "reachable (no sessions)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not reachable"


def _check_mcp_sockets() -> tuple[bool, str]:
    """Count active MCP sockets."""
    socket_dir = data_dir() / "mcp-pool" / "sockets"
    if not socket_dir.exists():
        return True, "0 sockets"
    sockets = list(socket_dir.glob("*.sock"))
    return True, f"{len(sockets)} socket(s)"


def diag(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Check Shoal component health."""
    checks = {
        "database": _check_db(),
        "watcher": _check_watcher(),
        "tmux": _check_tmux(),
        "mcp_sockets": _check_mcp_sockets(),
    }

    if json_output:
        data = {
            name: {"healthy": healthy, "detail": detail}
            for name, (healthy, detail) in checks.items()
        }
        all_healthy = all(h for h, _ in checks.values())
        print(json.dumps({"status": "healthy" if all_healthy else "degraded", **data}))
        return

    console = Console()
    table = create_table(padding=(0, 2))
    table.add_column("Component", width=16)
    table.add_column("Status", width=12)
    table.add_column("Detail")

    for name, (healthy, detail) in checks.items():
        marker = f"[green]{Symbols.CHECK}[/green]" if healthy else f"[red]{Symbols.CROSS}[/red]"
        status = f"{marker} {'OK' if healthy else 'FAIL'}"
        table.add_row(name, status, f"[dim]{detail}[/dim]")

    all_healthy = all(h for h, _ in checks.values())
    title_color = "green" if all_healthy else "yellow"
    console.print(
        create_panel(
            table,
            title=f"[bold {title_color}]{Icons.INFO} Diagnostics[/bold {title_color}]",
            title_align="left",
        )
    )
