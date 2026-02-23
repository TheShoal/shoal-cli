"""Remote session management via SSH tunnel."""

from __future__ import annotations

import contextlib
import os
import subprocess
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import load_config
from shoal.core.remote import (
    RemoteConnectionError,
    is_tunnel_active,
    read_tunnel_port,
    remote_api_get,
    remote_api_post,
    resolve_host,
    start_tunnel,
    stop_tunnel,
)
from shoal.core.theme import (
    Icons,
    Symbols,
    create_panel,
    create_table,
    get_status_icon,
    get_status_style,
)

console = Console()

app = typer.Typer(
    name="remote",
    help="Remote session management via SSH tunnel.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def remote_default(ctx: typer.Context) -> None:
    """Remote session management (default: ls)."""
    if ctx.invoked_subcommand is None:
        remote_ls()


@app.command("ls")
def remote_ls(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (host names only)",
        ),
    ] = None,
) -> None:
    """List configured remote hosts and connection status."""
    cfg = load_config()

    if format == "plain":
        for name in sorted(cfg.remote):
            console.print(name)
        return

    if not cfg.remote:
        console.print("[yellow]No remote hosts configured[/yellow]")
        console.print(
            "Add hosts to [bold]~/.config/shoal/config.toml[/bold]:\n"
            '\n[dim][remote.myhost]\nhost = "myhost.example.com"\n[/dim]'
        )
        return

    table = create_table(padding=(0, 1))
    table.add_column("NAME", width=20)
    table.add_column("HOST", width=30)
    table.add_column("SSH PORT", width=10, justify="right")
    table.add_column("API PORT", width=10, justify="right")
    table.add_column("STATUS", width=20)

    for name, host_cfg in sorted(cfg.remote.items()):
        active = is_tunnel_active(name)
        if active:
            port = read_tunnel_port(name)
            status_text = f"[green]{Symbols.CHECK} connected[/green] [dim](:{port})[/dim]"
        else:
            status_text = f"[dim]{Symbols.BULLET_STOPPED} disconnected[/dim]"

        user_host = f"{host_cfg.user}@{host_cfg.host}" if host_cfg.user else host_cfg.host

        table.add_row(
            f"[bold]{name}[/bold]",
            user_host,
            str(host_cfg.port),
            str(host_cfg.api_port),
            status_text,
        )

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.MCP} Remote Hosts[/bold blue]",
            primary=True,
            title_align="left",
            padding=(0, 1),
        )
    )


@app.command("connect")
def remote_connect(
    host: Annotated[str, typer.Argument(help="Remote host name from config")],
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Override local port (default: auto)"),
    ] = None,
) -> None:
    """Connect to a remote host via SSH tunnel."""
    try:
        host_cfg = resolve_host(host)
    except KeyError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if is_tunnel_active(host):
        local_port = read_tunnel_port(host)
        console.print(f"[yellow]Already connected to '{host}' on port {local_port}[/yellow]")
        return

    try:
        local_port = start_tunnel(
            host=host,
            ssh_host=host_cfg["host"],
            remote_port=host_cfg["api_port"],
            local_port=port,
            user=host_cfg["user"],
            identity_file=host_cfg["identity_file"],
            ssh_port=host_cfg["port"],
        )
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(
        f"[green]{Symbols.CHECK}[/green] Connected to [bold]{host}[/bold] "
        f"(localhost:{local_port} → {host_cfg['host']}:{host_cfg['api_port']})"
    )


@app.command("disconnect")
def remote_disconnect(
    host: Annotated[str, typer.Argument(help="Remote host name")],
) -> None:
    """Disconnect from a remote host."""
    if not is_tunnel_active(host):
        console.print(f"[yellow]Not connected to '{host}'[/yellow]")
        return

    stopped = stop_tunnel(host)
    if stopped:
        console.print(f"[green]{Symbols.CHECK}[/green] Disconnected from [bold]{host}[/bold]")
    else:
        console.print(f"[red]Failed to disconnect from '{host}'[/red]")


@app.command("status")
def remote_status(
    host: Annotated[str, typer.Argument(help="Remote host name")],
) -> None:
    """Show status summary of remote sessions."""
    _ensure_connected(host)

    try:
        data = remote_api_get(host, "/status")
    except RemoteConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    table = create_table(padding=(0, 2))
    table.add_column("Metric", width=15)
    table.add_column("Value", width=10, justify="right")

    table.add_row("Total", str(data.get("total", 0)))
    for status_name in ("running", "waiting", "error", "idle", "stopped"):
        count = data.get(status_name, 0)
        style = get_status_style(status_name)
        icon = get_status_icon(status_name)
        table.add_row(
            f"[{style}]{icon} {status_name}[/{style}]",
            f"[{style}]{count}[/{style}]",
        )

    version = data.get("version", "unknown")
    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.STATUS} {host} (v{version})[/bold blue]",
            primary=True,
            title_align="left",
            padding=(0, 1),
        )
    )


@app.command("sessions")
def remote_sessions(
    host: Annotated[str, typer.Argument(help="Remote host name")],
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (session names only)",
        ),
    ] = None,
) -> None:
    """List sessions on a remote host."""
    _ensure_connected(host)

    try:
        sessions = remote_api_get(host, "/sessions")
    except RemoteConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if format == "plain":
        for s in sorted(sessions, key=lambda x: x.get("name", "")):
            console.print(s.get("name", ""))
        return

    if not sessions:
        console.print(f"[yellow]No sessions on '{host}'[/yellow]")
        return

    table = create_table(padding=(0, 1))
    table.add_column("ID", style="dim", width=8)
    table.add_column("NAME", width=25)
    table.add_column("TOOL", width=12)
    table.add_column("STATUS", width=15)
    table.add_column("BRANCH", width=25)

    for s in sorted(sessions, key=lambda x: x.get("name", "")):
        status_val = s.get("status", "unknown")
        style = get_status_style(status_val)
        status_text = f"[{style}]{status_val}[/{style}]"
        sid = s.get("id", "")[:8]
        branch = s.get("branch", "") or "-"

        table.add_row(
            sid,
            f"[bold]{s.get('name', '')}[/bold]",
            s.get("tool", ""),
            status_text,
            f"[cyan]{branch}[/cyan]",
        )

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.SESSION} {host} sessions[/bold blue]",
            primary=True,
            title_align="left",
            padding=(0, 1),
        )
    )


@app.command("send")
def remote_send(
    host: Annotated[str, typer.Argument(help="Remote host name")],
    session: Annotated[str, typer.Argument(help="Session name or ID on remote")],
    keys: Annotated[str, typer.Argument(help="Keystrokes to send")],
) -> None:
    """Send keystrokes to a remote session."""
    _ensure_connected(host)

    # Resolve session name to ID
    session_id = _resolve_remote_session(host, session)

    try:
        remote_api_post(host, f"/sessions/{session_id}/send", {"keys": keys})
    except RemoteConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]{Symbols.CHECK}[/green] Sent keys to [bold]{session}[/bold] on {host}")


@app.command("attach")
def remote_attach(
    host: Annotated[str, typer.Argument(help="Remote host name")],
    session: Annotated[str, typer.Argument(help="Session name on remote")],
) -> None:
    """Attach to a remote tmux session via SSH."""
    try:
        host_cfg = resolve_host(host)
    except KeyError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    # Build SSH command to attach to remote tmux
    cfg = load_config()
    prefix = cfg.tmux.session_prefix

    cmd: list[str] = ["ssh", "-t"]
    if host_cfg["port"] != 22:
        cmd.extend(["-p", str(host_cfg["port"])])
    if host_cfg["identity_file"]:
        cmd.extend(["-i", os.path.expanduser(host_cfg["identity_file"])])

    target = f"{host_cfg['user']}@{host_cfg['host']}" if host_cfg["user"] else host_cfg["host"]
    cmd.append(target)
    cmd.append(f"tmux attach-session -t {prefix}{session}")

    console.print(f"[dim]Attaching to {host}:{session}...[/dim]")
    with contextlib.suppress(KeyboardInterrupt):
        subprocess.run(cmd, check=False)


# --- Helpers ---


def _ensure_connected(host: str) -> None:
    """Ensure a tunnel is active to the given host, or exit."""
    if not is_tunnel_active(host):
        console.print(
            f"[red]Not connected to '{host}'.[/red] Run: [bold]shoal remote connect {host}[/bold]"
        )
        raise typer.Exit(1)


def _resolve_remote_session(host: str, name_or_id: str) -> str:
    """Resolve a session name to its ID on the remote host."""
    try:
        sessions = remote_api_get(host, "/sessions")
    except RemoteConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    # Try exact ID match
    for s in sessions:
        if s.get("id", "") == name_or_id:
            return name_or_id

    # Try name match
    for s in sessions:
        if s.get("name", "") == name_or_id:
            sid: str = s["id"]
            return sid

    console.print(f"[red]Session '{name_or_id}' not found on '{host}'[/red]")
    raise typer.Exit(1)
