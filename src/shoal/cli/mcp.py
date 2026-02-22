"""MCP server pool commands: ls, start, stop, attach, status."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import ensure_dirs, state_dir
from shoal.core.db import with_db
from shoal.core.state import (
    _resolve_session_interactive_impl,
    add_mcp_to_session,
    get_session,
    list_sessions,
    remove_mcp_from_session,
)
from shoal.core.theme import Icons, Symbols, create_panel, create_table
from shoal.services.mcp_pool import (
    is_mcp_running,
    mcp_log_file,
    mcp_socket,
    read_pid,
    start_mcp_server,
    stop_mcp_server,
    validate_mcp_name,
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


async def _mcp_ls_impl() -> None:
    ensure_dirs()
    socket_dir = state_dir() / "mcp-pool" / "sockets"
    if not socket_dir.exists():
        console.print("[yellow]No MCP servers in pool[/yellow]")
        return

    sockets = list(socket_dir.glob("*.sock"))
    if not sockets:
        console.print("[yellow]No MCP servers in pool[/yellow]")
        return

    table = create_table(padding=(0, 2))
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
                mcp_status = f"[green]{Symbols.BULLET_FILLED} running[/green]"
            else:
                mcp_status = f"[red]{Symbols.BULLET_ERROR} dead[/red]"
        else:
            mcp_status = "[yellow]? orphaned[/yellow]"

        # Find sessions using this MCP
        using = [f"[bold cyan]{s.name}[/bold cyan]" for s in sessions if name in s.mcp_servers]

        sessions_str = ", ".join(using) if using else "[dim]-(none)-[/dim]"
        table.add_row(f"[bold]{name}[/bold]", pid_str, mcp_status, sessions_str)

    console.print()
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.MCP} MCP Server Pool[/bold blue]",
            title_align="left",
        )
    )


@app.command("start")
def mcp_start(
    name: Annotated[str, typer.Argument(help="MCP server name")],
    command: Annotated[str | None, typer.Option("--command", "-c", help="Command to run")] = None,
) -> None:
    """Start an MCP server in the pool."""
    ensure_dirs()

    try:
        validate_mcp_name(name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if is_mcp_running(name):
        pid = read_pid(name)
        console.print(f"[red]Error: MCP server '{name}' is already running (pid: {pid})[/red]")
        console.print()
        console.print("[yellow]Actionable suggestions:[/yellow]")
        console.print(f"  • Use existing server: [bold]shoal mcp attach <session> {name}[/bold]")
        console.print(
            f"  • Restart server:      [bold]shoal mcp stop {name} && shoal mcp start {name}[/bold]"
        )
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


async def _mcp_stop_impl(name: str) -> None:
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


async def _mcp_attach_impl(session: str, mcp_name: str) -> None:
    ensure_dirs()

    try:
        validate_mcp_name(mcp_name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    sid = await _resolve_session_interactive_impl(session)

    socket = mcp_socket(mcp_name)
    if not socket.exists() or not is_mcp_running(mcp_name):
        # Auto-start: look up registry and start if known
        from shoal.core.config import load_mcp_registry

        registry = load_mcp_registry()
        command = registry.get(mcp_name)

        if not command:
            console.print(f"[red]Error: MCP server '{mcp_name}' is not running[/red]")
            console.print()
            console.print("[yellow]Actionable suggestions:[/yellow]")
            console.print(
                f"  • Start with command: [bold]shoal mcp start {mcp_name} -c '<command>'[/bold]"
            )
            console.print("  • Add to registry:   [bold]~/.config/shoal/mcp-servers.toml[/bold]")
            raise typer.Exit(1)

        # Clean up stale socket if needed
        if socket.exists() and not is_mcp_running(mcp_name):
            with suppress(FileNotFoundError):
                stop_mcp_server(mcp_name)

        try:
            pid, socket, _cmd = start_mcp_server(mcp_name, command)
            console.print(f"Auto-started MCP server '{mcp_name}' (pid: {pid})")
        except (ValueError, RuntimeError) as e:
            console.print(f"[red]Error: Failed to auto-start MCP server: {e}[/red]")
            raise typer.Exit(1) from None

    await add_mcp_to_session(sid, mcp_name)

    s = await get_session(sid)
    name = s.name if s else sid
    tool = s.tool if s else "unknown"
    work_dir = (s.worktree or s.path) if s else ""

    console.print(f"Attached MCP '{mcp_name}' to session '{name}'")
    console.print(f"  Socket: {socket}")

    # Auto-configure tool to use this MCP server
    from shoal.services.mcp_configure import McpConfigureError, configure_mcp_for_tool

    try:
        result = configure_mcp_for_tool(tool, mcp_name, work_dir)
        if result:
            console.print(f"  {result}")
        else:
            console.print()
            console.print(f"[yellow]Note: No auto-config available for {tool}.[/yellow]")
            console.print(
                f"  Configure manually: claude mcp add {mcp_name} -- shoal-mcp-proxy {mcp_name}"
            )
    except McpConfigureError as e:
        console.print(f"\n[yellow]Warning: Auto-configure failed: {e}[/yellow]")
        console.print(
            f"  Configure manually: claude mcp add {mcp_name} -- shoal-mcp-proxy {mcp_name}"
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

    from rich.text import Text

    parts = []
    if healthy:
        parts.append(f"[green]{Symbols.BULLET_FILLED} {healthy} healthy[/green]")
    if dead:
        parts.append(f"[red]{Symbols.BULLET_ERROR} {dead} dead[/red]")
    if orphaned:
        parts.append(f"[yellow]? {orphaned} orphaned[/yellow]")

    if not parts:
        summary = Text("No MCP servers in pool", style="yellow")
    else:
        summary = Text.from_markup("  |  ".join(parts))

    console.print()
    console.print(
        create_panel(
            summary,
            title=f"[bold blue]{Icons.MCP} MCP Pool Status ({total} total)[/bold blue]",
            expand=False,
        )
    )

    if total == 0:
        console.print("\n[dim]Start one with: [bold]shoal mcp start <name>[/bold][/dim]")
        console.print("[dim]Configure servers in ~/.config/shoal/mcp-servers.toml[/dim]")

    if dead or orphaned:
        console.print("\n[yellow]󰀦 Stale entries detected.[/yellow]")
        console.print("[dim]Run 'shoal mcp stop <name>' to clean up.[/dim]")


@app.command("logs")
def mcp_logs(
    name: Annotated[str, typer.Argument(help="MCP server name")],
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of lines")] = 50,
) -> None:
    """Show logs for an MCP server."""
    log_path = mcp_log_file(name)
    if not log_path.exists():
        console.print(f"[red]No log file for MCP server '{name}'[/red]")
        raise typer.Exit(1) from None

    lines = log_path.read_text().splitlines()
    for line in lines[-tail:]:
        console.print(line)


@app.command("doctor")
def mcp_doctor() -> None:
    """Deep health check for MCP servers."""
    import json
    import time

    ensure_dirs()
    socket_dir = state_dir() / "mcp-pool" / "sockets"

    if not socket_dir.exists() or not list(socket_dir.glob("*.sock")):
        console.print("[yellow]No MCP servers to check[/yellow]")
        return

    table = create_table(padding=(0, 2))
    table.add_column("NAME", width=16)
    table.add_column("PID", width=12)
    table.add_column("SOCKET", width=12)
    table.add_column("JSON-RPC", width=12)
    table.add_column("LATENCY", width=10)

    for sock_path in sorted(socket_dir.glob("*.sock")):
        name = sock_path.stem
        pid = read_pid(name)

        # PID check
        pid_status = "[red]dead[/red]"
        if pid is not None and is_mcp_running(name):
            pid_status = f"[green]ok ({pid})[/green]"
        elif pid is not None:
            pid_status = f"[red]dead ({pid})[/red]"

        # Socket + JSON-RPC check
        sock_status = "[red]fail[/red]"
        rpc_status = "[dim]-[/dim]"
        latency_str = "[dim]-[/dim]"

        try:
            start = time.monotonic()
            reader, writer = asyncio.run(
                asyncio.wait_for(
                    asyncio.open_unix_connection(str(sock_path)),
                    timeout=5.0,
                )
            )
            sock_status = "[green]ok[/green]"

            # Try JSON-RPC initialize
            rpc_msg = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}})
            writer.write((rpc_msg + "\n").encode())
            try:
                data = asyncio.run(asyncio.wait_for(reader.read(4096), timeout=5.0))
                elapsed = time.monotonic() - start
                latency_str = f"{elapsed * 1000:.0f}ms"
                if data and b"jsonrpc" in data:
                    rpc_status = "[green]ok[/green]"
                else:
                    rpc_status = "[yellow]no response[/yellow]"
            except TimeoutError:
                rpc_status = "[red]timeout[/red]"
            finally:
                writer.close()
        except (TimeoutError, OSError):
            sock_status = "[red]fail[/red]"

        name_col = f"[bold]{name}[/bold]"
        table.add_row(name_col, pid_status, sock_status, rpc_status, latency_str)

    console.print()
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.MCP} MCP Doctor[/bold blue]",
            title_align="left",
        )
    )
