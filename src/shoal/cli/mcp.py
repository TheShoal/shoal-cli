"""MCP server pool commands: ls, start, stop, attach, status."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import data_dir, ensure_dirs
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
    get_transport,
    is_mcp_running,
    mcp_log_file,
    mcp_socket,
    read_pid,
    read_port,
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


def _discover_servers() -> list[str]:
    """Discover running MCP servers by scanning PID files."""
    pid_dir = data_dir() / "mcp-pool" / "pids"
    if not pid_dir.exists():
        return []
    return sorted(p.stem for p in pid_dir.glob("*.pid"))


async def _mcp_ls_impl() -> None:
    ensure_dirs()
    names = _discover_servers()
    if not names:
        console.print("[yellow]No MCP servers in pool[/yellow]")
        return

    table = create_table(padding=(0, 2))
    table.add_column("NAME", width=20)
    table.add_column("PID", width=10, style="dim")
    table.add_column("TRANSPORT", width=12, style="dim")
    table.add_column("STATUS", width=12)
    table.add_column("SESSIONS")

    sessions = await list_sessions()
    for name in names:
        pid = read_pid(name)
        pid_str = str(pid) if pid else "-"

        port = read_port(name)
        transport = f"http:{port}" if port is not None else "socket"

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
        table.add_row(f"[bold]{name}[/bold]", pid_str, transport, mcp_status, sessions_str)

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
    http: Annotated[bool, typer.Option("--http", help="Use HTTP transport")] = False,
    port: Annotated[
        int | None, typer.Option("--port", "-p", help="HTTP port (default: 8390)")
    ] = None,
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

    # Auto-detect HTTP transport if not explicitly set
    use_http = http or get_transport(name) == "http"

    try:
        pid, path, cmd = start_mcp_server(name, command, http=use_http, http_port=port)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"MCP server '{name}' started")
    if use_http:
        effective_port = port or 8390
        console.print(f"  URL: http://localhost:{effective_port}")
    else:
        console.print(f"  Socket: {path}")
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

    total = healthy = dead = 0

    for name in _discover_servers():
        total += 1
        if is_mcp_running(name):
            healthy += 1
        else:
            dead += 1

    from rich.text import Text

    parts = []
    if healthy:
        parts.append(f"[green]{Symbols.BULLET_FILLED} {healthy} healthy[/green]")
    if dead:
        parts.append(f"[red]{Symbols.BULLET_ERROR} {dead} dead[/red]")

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

    if dead:
        console.print("\n[yellow]󰀦 Stale entries detected.[/yellow]")
        console.print("[dim]Run 'shoal mcp doctor --cleanup' to clean up.[/dim]")


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


class _ProbeResult:
    """Result of probing an MCP server via FastMCP Client."""

    __slots__ = ("connected", "error", "latency_ms", "server_name", "server_version", "tool_count")

    def __init__(
        self,
        *,
        connected: bool = False,
        server_name: str = "",
        server_version: str = "",
        tool_count: int = 0,
        latency_ms: float = 0.0,
        error: str = "",
    ) -> None:
        self.connected = connected
        self.server_name = server_name
        self.server_version = server_version
        self.tool_count = tool_count
        self.latency_ms = latency_ms
        self.error = error


async def _probe_server(name: str) -> _ProbeResult:
    """Probe an MCP server using FastMCP Client via shoal-mcp-proxy."""
    import time

    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(command="shoal-mcp-proxy", args=[name])
    client = Client(transport, timeout=10, init_timeout=5)

    start = time.monotonic()
    try:
        async with client:
            elapsed = time.monotonic() - start
            init_result = client.initialize_result
            tools = await client.list_tools()

            server_name = ""
            server_version = ""
            if init_result and init_result.serverInfo:
                server_name = init_result.serverInfo.name
                server_version = init_result.serverInfo.version or ""

            return _ProbeResult(
                connected=True,
                server_name=server_name,
                server_version=server_version,
                tool_count=len(tools),
                latency_ms=elapsed * 1000,
            )
    except TimeoutError:
        return _ProbeResult(error="timeout")
    except (ConnectionRefusedError, OSError) as e:
        return _ProbeResult(error=f"socket unreachable: {e}")
    except Exception as e:
        return _ProbeResult(error=str(e))


async def _probe_http_server(name: str, port: int) -> _ProbeResult:
    """Probe an HTTP-mode MCP server using FastMCP Client + StreamableHttpTransport."""
    import time

    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url = f"http://localhost:{port}/mcp/"
    transport = StreamableHttpTransport(url=url)
    client = Client(transport, timeout=10, init_timeout=5)

    start = time.monotonic()
    try:
        async with client:
            elapsed = time.monotonic() - start
            init_result = client.initialize_result
            tools = await client.list_tools()

            server_name = ""
            server_version = ""
            if init_result and init_result.serverInfo:
                server_name = init_result.serverInfo.name
                server_version = init_result.serverInfo.version or ""

            return _ProbeResult(
                connected=True,
                server_name=server_name,
                server_version=server_version,
                tool_count=len(tools),
                latency_ms=elapsed * 1000,
            )
    except TimeoutError:
        return _ProbeResult(error="timeout")
    except (ConnectionRefusedError, OSError) as e:
        return _ProbeResult(error=f"http unreachable: {e}")
    except Exception as e:
        return _ProbeResult(error=str(e))


@app.command("doctor")
def mcp_doctor(
    cleanup: Annotated[
        bool, typer.Option("--cleanup", help="Remove stale PID/socket files for dead servers")
    ] = False,
) -> None:
    """Deep health check for MCP servers."""
    ensure_dirs()
    names = _discover_servers()

    if not names:
        console.print("[yellow]No MCP servers to check[/yellow]")
        return

    try:
        import fastmcp as _  # noqa: F401

        has_fastmcp = True
    except ImportError:
        has_fastmcp = False

    table = create_table(padding=(0, 1))
    table.add_column("NAME")
    table.add_column("PID")
    table.add_column("TRANSPORT")
    table.add_column("PROTOCOL")
    table.add_column("TOOLS")
    table.add_column("VERSION")
    table.add_column("LATENCY")

    for name in names:
        pid = read_pid(name)
        port = read_port(name)
        transport = f"http:{port}" if port is not None else "socket"

        # PID check
        pid_status = "[red]dead[/red]"
        if pid is not None and is_mcp_running(name):
            pid_status = f"[green]ok ({pid})[/green]"
        elif pid is not None:
            pid_status = f"[red]dead ({pid})[/red]"

        # Protocol probe via FastMCP Client (socket-mode only for now)
        proto_status = "[dim]-[/dim]"
        tools_str = "[dim]-[/dim]"
        version_str = "[dim]-[/dim]"
        latency_str = "[dim]-[/dim]"

        if pid is not None and is_mcp_running(name):
            if port is not None and has_fastmcp:
                result = asyncio.run(_probe_http_server(name, port))
                if result.connected:
                    proto_status = "[green]ok[/green]"
                    tools_str = str(result.tool_count)
                    if result.server_version:
                        version_str = result.server_version
                    latency_str = f"{result.latency_ms:.0f}ms"
                elif result.error:
                    proto_status = f"[red]{result.error}[/red]"
            elif port is not None:
                proto_status = "[yellow]skip (http)[/yellow]"
            elif has_fastmcp:
                result = asyncio.run(_probe_server(name))

                if result.connected:
                    proto_status = "[green]ok[/green]"
                    tools_str = str(result.tool_count)
                    if result.server_version:
                        version_str = result.server_version
                    latency_str = f"{result.latency_ms:.0f}ms"
                elif result.error == "timeout":
                    proto_status = "[red]timeout[/red]"
                else:
                    proto_status = f"[red]{result.error}[/red]"
            else:
                proto_status = "[yellow]skip[/yellow]"

        name_col = f"[bold]{name}[/bold]"
        table.add_row(
            name_col, pid_status, transport, proto_status, tools_str, version_str, latency_str
        )

    console.print()
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.MCP} MCP Doctor[/bold blue]",
            title_align="left",
        )
    )

    if cleanup:
        cleaned = 0
        for name in names:
            pid = read_pid(name)
            if pid is not None and not is_mcp_running(name):
                stop_mcp_server(name)
                cleaned += 1
        if cleaned:
            console.print(f"\n[green]{Symbols.CHECK} Cleaned up {cleaned} stale server(s)[/green]")
        else:
            console.print("\n[dim]No stale servers to clean up.[/dim]")

    if not has_fastmcp:
        console.print()
        console.print(
            "[yellow]Note: Install fastmcp for protocol-level health checks: "
            "pip install shoal\\[mcp][/yellow]"
        )


@app.command("registry")
def mcp_registry() -> None:
    """List all known MCP servers (built-in + user registry)."""
    from shoal.core.config import load_mcp_registry_full
    from shoal.services.mcp_pool import _DEFAULT_SERVERS

    # Build combined registry: defaults + user overrides
    combined: dict[str, dict[str, str]] = {}
    for name, cmd in _DEFAULT_SERVERS.items():
        combined[name] = {"command": cmd, "transport": "socket", "_source": "built-in"}

    user_registry = load_mcp_registry_full()
    for name, entry in user_registry.items():
        if name in combined:
            combined[name].update(entry)
            combined[name]["_source"] = "override"
        else:
            combined[name] = {**entry, "_source": "user"}

    table = create_table(padding=(0, 2))
    table.add_column("NAME", style="bold")
    table.add_column("SOURCE")
    table.add_column("TRANSPORT")
    table.add_column("COMMAND", no_wrap=False)

    for name in sorted(combined):
        entry = combined[name]
        source = entry.pop("_source", "unknown")
        transport = entry.get("transport", "socket")
        command = entry.get("command", "")
        source_style = (
            "[dim]built-in[/dim]"
            if source == "built-in"
            else "[cyan]user[/cyan]"
            if source == "user"
            else "[yellow]override[/yellow]"
        )
        table.add_row(name, source_style, transport, f"[dim]{command}[/dim]")

    console.print()
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.MCP} MCP Server Registry[/bold blue]",
            title_align="left",
        )
    )
