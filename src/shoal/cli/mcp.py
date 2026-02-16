"""MCP server pool commands: ls, start, stop, attach, status."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core.config import ensure_dirs, state_dir
from shoal.core.db import with_db
from shoal.core.state import (
    add_mcp_to_session,
    get_session,
    list_sessions,
    remove_mcp_from_session,
    resolve_session_interactive,
)
from shoal.services.mcp_pool import (
    is_mcp_running,
    mcp_socket,
    read_pid,
    start_mcp_server,
    stop_mcp_server,
)

console = Console()

app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def mcp_default(ctx: typer.Context) -> None:
    """MCP server pool (default: ls)."""
    if ctx.invoked_subcommand is None:
        mcp_ls()


@app.command("ls")
def mcp_ls() -> None:
    """List MCP servers in the pool."""
    asyncio.run(with_db(_mcp_ls_impl()))


async def _mcp_ls_impl():
    ensure_dirs()
    socket_dir = state_dir() / "mcp-pool" / "sockets"
    if not socket_dir.exists():
        console.print("[yellow]No MCP servers in pool[/yellow]")
        return

    sockets = list(socket_dir.glob("*.sock"))
    if not sockets:
        console.print("[yellow]No MCP servers in pool[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
    table.add_column("NAME", width=20)
    table.add_column("PID", width=10, style="dim")
    table.add_column("STATUS", width=12)
    table.add_column("SESSIONS")

    sessions = await list_sessions()
    for sock_path in sorted(sockets):
        name = sock_path.stem
        pid = read_pid(name)
        pid_str = str(pid) if pid else "-"

        if pid is not None:
            if is_mcp_running(name):
                mcp_status = "[green]● running[/green]"
            else:
                mcp_status = "[red]✗ dead[/red]"
        else:
            mcp_status = "[yellow]? orphaned[/yellow]"

        # Find sessions using this MCP
        using = [f"[bold cyan]{s.name}[/bold cyan]" for s in sessions if name in s.mcp_servers]

        sessions_str = ", ".join(using) if using else "[dim]-(none)-[/dim]"
        table.add_row(f"[bold]{name}[/bold]", pid_str, mcp_status, sessions_str)

    from rich.panel import Panel

    console.print(
        Panel(
            table,
            title="[bold blue]󰒓 MCP Server Pool[/bold blue]",
            title_align="left",
            border_style="dim",
        )
    )


@app.command("start")
def mcp_start(
    name: Annotated[str, typer.Argument(help="MCP server name")],
    command: Annotated[str | None, typer.Option("--command", "-c", help="Command to run")] = None,
) -> None:
    """Start an MCP server in the pool."""
    ensure_dirs()

    if is_mcp_running(name):
        pid = read_pid(name)
        console.print(f"[red]MCP server '{name}' is already running (pid: {pid})[/red]")
        raise typer.Exit(1)

    try:
        pid, socket, cmd = start_mcp_server(name, command)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"MCP server '{name}' started")
    console.print(f"  Socket: {socket}")
    console.print(f"  PID: {pid}")
    console.print(f"  Command: {cmd}")


@app.command("stop")
def mcp_stop(
    name: Annotated[str, typer.Argument(help="MCP server to stop")],
) -> None:
    """Stop a pooled MCP server."""
    asyncio.run(with_db(_mcp_stop_impl(name)))


async def _mcp_stop_impl(name):
    ensure_dirs()
    try:
        stop_mcp_server(name)
    except FileNotFoundError:
        console.print(f"[red]MCP server '{name}' is not running[/red]")
        raise typer.Exit(1) from None

    console.print(f"MCP server '{name}' stopped")

    # Remove MCP from any sessions that reference it
    sessions = await list_sessions()
    for s in sessions:
        if name in s.mcp_servers:
            await remove_mcp_from_session(s.id, name)


@app.command("attach")
def mcp_attach(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    mcp_name: Annotated[str, typer.Argument(help="MCP server name")],
) -> None:
    """Attach an MCP server to a session."""
    asyncio.run(with_db(_mcp_attach_impl(session, mcp_name)))


async def _mcp_attach_impl(session, mcp_name):
    ensure_dirs()
    sid = resolve_session_interactive(session)

    socket = mcp_socket(mcp_name)
    if not socket.exists():
        console.print(f"[red]MCP server '{mcp_name}' is not running[/red]")
        console.print(f"Start it with: shoal mcp start {mcp_name}")
        raise typer.Exit(1)

    if not is_mcp_running(mcp_name):
        console.print(f"[red]MCP server '{mcp_name}' has a stale socket (process dead)[/red]")
        raise typer.Exit(1)

    await add_mcp_to_session(sid, mcp_name)

    s = await get_session(sid)
    name = s.name if s else sid
    tool = s.tool if s else "unknown"

    console.print(f"Attached MCP '{mcp_name}' to session '{name}'")
    console.print(f"  Socket: {socket}")
    console.print()
    console.print(f"Note: You may need to configure {tool} to use this socket.")
    console.print(
        f"For Claude Code: claude mcp add {mcp_name} -- socat STDIO UNIX-CONNECT:{socket}"
    )


@app.command("status")
def mcp_status() -> None:
    """MCP pool health check."""
    ensure_dirs()
    socket_dir = state_dir() / "mcp-pool" / "sockets"

    total = healthy = dead = orphaned = 0

    if socket_dir.exists():
        for sock_path in socket_dir.glob("*.sock"):
            total += 1
            name = sock_path.stem
            pid = read_pid(name)
            if pid is not None:
                if is_mcp_running(name):
                    healthy += 1
                else:
                    dead += 1
            else:
                orphaned += 1

    from rich.panel import Panel
    from rich.text import Text

    parts = []
    if healthy:
        parts.append(f"[green]● {healthy} healthy[/green]")
    if dead:
        parts.append(f"[red]✗ {dead} dead[/red]")
    if orphaned:
        parts.append(f"[yellow]? {orphaned} orphaned[/yellow]")

    if not parts:
        summary = Text("No MCP servers in pool", style="yellow")
    else:
        summary = Text.from_markup("  |  ".join(parts))

    console.print(
        Panel(
            summary,
            title=f"[bold blue]󰒓 MCP Pool Status ({total} total)[/bold blue]",
            title_align="left",
            border_style="dim",
            expand=False,
        )
    )

    if total == 0:
        console.print("\n[dim]Start one with: [bold]shoal mcp start <name>[/bold][/dim]")
        console.print("[dim]Known servers: memory, filesystem, github, fetch[/dim]")

    if dead or orphaned:
        console.print("\n[yellow]󰀦 Stale entries detected.[/yellow]")
        console.print("[dim]Run 'shoal mcp stop <name>' to clean up.[/dim]")
