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
    kill,
    ls,
    popup,
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
app.command()(attach)
app.command()(detach)
app.command()(fork)
app.command()(kill)
app.command()(status)
app.command()(popup)

# Aliases (hidden)
app.command("new", hidden=True)(add)
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
