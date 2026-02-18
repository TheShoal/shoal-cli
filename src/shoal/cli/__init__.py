"""Root Typer app with subcommand routing."""

from __future__ import annotations

import asyncio
import logging

import typer

import shoal
from shoal.cli.demo import app as demo_app
from shoal.cli.mcp import app as mcp_app
from shoal.cli.nvim import app as nvim_app
from shoal.cli.robo import app as robo_app
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
    prune,
    rename,
    status,
)
from shoal.cli.setup import app as setup_app
from shoal.cli.watcher import app as watcher_app
from shoal.cli.worktree import app as wt_app
from shoal.core.db import with_db
from shoal.core.state import get_session

app = typer.Typer(
    name="shoal",
    help="Orchestrate AI coding agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    debug: bool = typer.Option(False, "--debug", help="Enable DEBUG-level logging to stderr."),
) -> None:
    """Orchestrate AI coding agents."""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")


# Session commands — top-level
app.command("new")(add)  # Primary command
app.command("ls")(ls)
app.command("info")(info)
app.command("rename")(rename)
app.command("logs")(logs)
app.command("attach")(attach)
app.command("detach")(detach)
app.command("fork")(fork)
app.command("kill")(kill)
app.command("prune")(prune)
app.command("status")(status)
app.command("popup")(popup)

# Aliases (hidden)
app.command("add", hidden=True)(add)  # Backward compat
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
app.add_typer(robo_app, name="robo", help="Robo (supervisory agent).")
app.add_typer(robo_app, name="conductor", hidden=True)  # Backward compat
app.add_typer(robo_app, name="cond", hidden=True)  # Backward compat
app.add_typer(nvim_app, name="nvim", help="Neovim integration.")
app.add_typer(watcher_app, name="watcher", help="Background status watcher.")
app.add_typer(demo_app, name="demo", help="Demo environment.")
app.add_typer(setup_app, name="setup", help="Setup shell integrations.")


@app.command()
def version() -> None:
    """Print version."""
    print(f"shoal {shoal.__version__}")


def _check_environment() -> None:
    """Shared helper: display dependency check and directory status."""
    import shutil

    from rich.console import Console
    from rich.table import Table

    from shoal.core.config import config_dir, runtime_dir, state_dir
    from shoal.core.theme import Icons, Symbols, create_panel, create_table

    console = Console()

    # Dependency check
    table = create_table(padding=(0, 2))
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
        marker = f"[green]{Symbols.CHECK}[/green]" if path else f"[red]{Symbols.CROSS}[/red]"
        status = f"{marker} {'OK' if path else 'Missing'}"
        table.add_row(tool, status, f"[dim]{note}[/dim]")

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.DEPENDENCY} Dependency Check[/bold blue]",
            title_align="left",
        )
    )

    # Directory check
    dir_info = Table.grid(padding=(0, 2))
    dir_info.add_column(style="bold cyan")
    dir_info.add_column()

    for name, path in [
        ("Config", config_dir()),
        ("State", state_dir()),
        ("Runtime", runtime_dir()),
    ]:
        exists = "[green]exists[/green]" if path.exists() else "[yellow]not created[/yellow]"
        dir_info.add_row(name, f"{path} [dim]({exists})[/dim]")

    console.print(
        create_panel(
            dir_info,
            title=f"[bold blue]{Icons.DIRECTORY} Directories[/bold blue]",
            title_align="left",
        )
    )


@app.command()
def init() -> None:
    """Initialize Shoal configuration and directories."""
    from rich.console import Console

    from shoal.core.config import ensure_dirs

    ensure_dirs()
    _check_environment()
    Console().print("\n[green]Shoal initialized successfully![/green]")


@app.command()
def check() -> None:
    """Check dependencies and environment."""
    _check_environment()


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
    """Dump session JSON for debugging/preview (used by popup)."""

    async def _impl():
        sid = session_id
        if not sid:
            return
        s = await get_session(sid)
        if s:
            print(s.model_dump_json(indent=2))

    asyncio.run(with_db(_impl()))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
) -> None:
    """Start FastAPI server for HTTP API access."""
    import uvicorn

    from shoal.api.server import app as fastapi_app

    typer.echo(f"Starting Shoal API server at http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port)
