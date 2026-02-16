"""Root Typer app with subcommand routing."""

from __future__ import annotations

import typer

import shoal
from shoal.cli.conductor import app as conductor_app
from shoal.cli.mcp import app as mcp_app
from shoal.cli.nvim import app as nvim_app
from shoal.cli.session import (
    add,
    attach,
    detach,
    fork,
    info,
    kill,
    logs,
    ls,
    popup,
    rename,
    status,
)
from shoal.cli.watcher import app as watcher_app
from shoal.cli.worktree import app as wt_app

app = typer.Typer(
    name="shoal",
    help="Orchestrate AI coding agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Session commands — top-level
app.command()(add)
app.command()(ls)
app.command()(info)
app.command()(rename)
app.command()(logs)
app.command()(attach)
app.command()(detach)
app.command()(fork)
app.command()(kill)
app.command()(status)
app.command()(popup)

# Aliases (hidden)
app.command("new", hidden=True)(add)
app.command("i", hidden=True)(info)
app.command("mv", hidden=True)(rename)
app.command("l", hidden=True)(logs)
app.command("a", hidden=True)(attach)
app.command("d", hidden=True)(detach)
app.command("rm", hidden=True)(kill)
app.command("st", hidden=True)(status)
app.command("pop", hidden=True)(popup)

# Sub-groups
app.add_typer(wt_app, name="wt", help="Worktree management.")
app.add_typer(wt_app, name="worktree", hidden=True)
app.add_typer(mcp_app, name="mcp", help="MCP server pool.")
app.add_typer(conductor_app, name="conductor", help="Conductor (supervisory agent).")
app.add_typer(conductor_app, name="cond", hidden=True)
app.add_typer(nvim_app, name="nvim", help="Neovim integration.")
app.add_typer(watcher_app, name="watcher", help="Background status watcher.")


@app.command()
def version() -> None:
    """Print version."""
    print(f"shoal {shoal.__version__}")


@app.command()
def init() -> None:
    """Initialize Shoal configuration and directories."""
    from shoal.core.config import ensure_dirs, config_dir
    import shutil
    from pathlib import Path

    ensure_dirs()
    cfg_dir = config_dir()
    
    if not cfg_dir.exists():
        cfg_dir.mkdir(parents=True)
        typer.echo(f"Created configuration directory: {cfg_dir}")

    # Check for examples in the project root
    # This assumes we are running from the source or examples are bundled
    example_src = Path(__file__).parents[3] / "examples" / "config"
    
    if example_src.exists():
        for item in example_src.iterdir():
            dest = cfg_dir / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy(item, dest)
                typer.echo(f"Copied example: {item.name}")
            else:
                typer.echo(f"Skipping existing: {item.name}")
    else:
        typer.echo("Example configurations not found in expected location.")
        typer.echo(f"Please manually copy examples to {cfg_dir}")

    typer.echo("Shoal initialized successfully!")


@app.command()
def check() -> None:
    """Check dependencies and environment."""
    import shutil
    from rich.table import Table
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    table = Table(
        show_header=True, 
        header_style="bold magenta",
        box=None,
        padding=(0, 2)
    )
    table.add_column("Tool", width=20)
    table.add_column("Status", width=12)
    table.add_column("Notes")

    dependencies = [
        ("tmux", "Required for session management"),
        ("git", "Required for project/worktree management"),
        ("fzf", "Required for interactive picking"),
        ("socat", "Required for MCP pooling"),
        ("gh", "Optional: for 'wt finish --pr'"),
        ("nvr", "Optional: for neovim integration"),
    ]

    for tool, note in dependencies:
        path = shutil.which(tool)
        status = "[green]✔ OK[/green]" if path else "[red]✘ Missing[/red]"
        table.add_row(tool, status, f"[dim]{note}[/dim]")

    console.print(Panel(
        table,
        title="[bold blue]󰒓 Dependency Check[/bold blue]",
        title_align="left",
        border_style="dim"
    ))
    
    # Check dirs
    from shoal.core.config import config_dir, state_dir, runtime_dir
    from rich.text import Text
    
    dir_info = Table.grid(padding=(0, 2))
    dir_info.add_column(style="bold cyan")
    dir_info.add_column()

    for name, path in [("Config", config_dir()), ("State", state_dir()), ("Runtime", runtime_dir())]:
        exists = "[green]exists[/green]" if path.exists() else "[yellow]not created[/yellow]"
        dir_info.add_row(name, f"{path} [dim]({exists})[/dim]")
    
    console.print(Panel(
        dir_info,
        title="[bold blue]󰓗 Directories[/bold blue]",
        title_align="left",
        border_style="dim"
    ))


@app.command("_popup-inner", hidden=True)
def popup_inner() -> None:
    """Internal: run popup dashboard inline (called from tmux popup)."""
    from shoal.dashboard.popup import run_popup

    run_popup()


@app.command("_popup-list", hidden=True)
def popup_list() -> None:
    """Internal: print session list for fzf reload."""
    from shoal.dashboard.popup import print_popup_list

    print_popup_list()


@app.command("session-json", hidden=True)
def session_json(session_id: str) -> None:
    """Internal: print session state as JSON for fzf preview."""
    import asyncio
    from shoal.core.state import get_session, resolve_session
    async def _impl():
        sid = await resolve_session(session_id)
        if not sid:
            return
        s = await get_session(sid)
        if s:
            print(s.model_dump_json(indent=2))
    asyncio.run(_impl())


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8080, "--port"),
) -> None:
    """Start FastAPI server for HTTP API access."""
    from shoal.api.server import app as fastapi_app
    import uvicorn

    typer.echo(f"Starting Shoal API server at http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port)
