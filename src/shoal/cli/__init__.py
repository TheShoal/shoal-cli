"""Root Typer app with subcommand routing."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer

import shoal

# Sub-group Typer apps — these are lightweight and needed at import time for add_typer.
from shoal.cli.config_cmd import app as config_app
from shoal.cli.demo import app as demo_app
from shoal.cli.fin import app as fin_app
from shoal.cli.incident import app as incident_app
from shoal.cli.mcp import app as mcp_app
from shoal.cli.mode_cmd import app as mode_app
from shoal.cli.nvim import app as nvim_app
from shoal.cli.remote import app as remote_app
from shoal.cli.robo import app as robo_app
from shoal.cli.setup import app as setup_app
from shoal.cli.tag import app as tag_app
from shoal.cli.template import app as template_app
from shoal.cli.watcher import app as watcher_app
from shoal.cli.worktree import app as wt_app

app = typer.Typer(
    name="shoal",
    help="Orchestrate AI coding agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"shoal {shoal.__version__}")
        raise typer.Exit


@app.callback()
def main(
    debug: bool = typer.Option(False, "--debug", help="Enable DEBUG-level logging to stderr."),
    log_level: str = typer.Option(
        "WARNING", "--log-level", help="Log level (DEBUG/INFO/WARNING/ERROR)."
    ),
    log_file: str | None = typer.Option(None, "--log-file", help="Log to file instead of stderr."),
    json_logs: bool = typer.Option(False, "--json-logs", help="Emit logs as JSON lines."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Orchestrate AI coding agents."""
    from shoal.core.logging_config import configure_logging

    effective_level = "DEBUG" if debug else log_level
    os.environ["SHOAL_LOG_LEVEL"] = effective_level
    if debug or effective_level != "WARNING" or json_logs or log_file:
        configure_logging(level=effective_level, json_logs=json_logs, log_file=log_file)


# ---------------------------------------------------------------------------
# Thin wrappers — defer heavy imports until a command is actually invoked.
# ---------------------------------------------------------------------------


@app.command("new")
def _add_cmd(
    path: Annotated[str | None, typer.Argument(help="Project directory")] = None,
    tool: Annotated[
        str | None,
        typer.Option(
            "-t",
            "--tool",
            help="AI tool to use (pi recommended; opencode status is best-effort)",
        ),
    ] = None,
    template: Annotated[
        str | None, typer.Option("--template", help="Session template name")
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Single-session mode defaults: feature-lane, author-review, remote-batch",
        ),
    ] = None,
    worktree: Annotated[
        str | None, typer.Option("-w", "--worktree", help="Create a git worktree")
    ] = None,
    branch: Annotated[bool, typer.Option("-b", "--branch", help="Create a new branch")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without creating session")
    ] = False,
    name: Annotated[str | None, typer.Option("-n", "--name", help="Session name")] = None,
    mcp: Annotated[
        str | None,
        typer.Option("--mcp", help="MCP servers to provision (comma-separated)"),
    ] = None,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Target sub-repo from .shoal/workspace.toml"),
    ] = None,
) -> None:
    """Create a new session."""
    from shoal.cli.session_create import add

    add(path, tool, template, mode, worktree, branch, dry_run, name, mcp, repo)


@app.command("ls")
def _ls_cmd(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (names only for completions)",
        ),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter sessions by tag"),
    ] = None,
    tree: Annotated[
        bool,
        typer.Option("--tree", help="Display fork relationships as a tree"),
    ] = False,
) -> None:
    """List all sessions."""
    from shoal.cli.session_view import ls

    ls(format=format, tag=tag, tree=tree)


@app.command("info")
def _info_cmd(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    color: Annotated[
        str,
        typer.Option(
            "--color",
            help="Color output: auto, always, never",
        ),
    ] = "auto",
) -> None:
    """Show detailed information about a session."""
    from shoal.cli.session_view import info

    info(session=session, color=color)


@app.command("rename")
def _rename_cmd(
    old_name: Annotated[str, typer.Argument(help="Current session name or ID")],
    new_name: Annotated[str, typer.Argument(help="New name for the session")],
) -> None:
    """Rename a session."""
    from shoal.cli.session import rename

    rename(old_name, new_name)


@app.command("logs")
def _logs_cmd(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 20,
    tail: Annotated[bool, typer.Option("--tail", "-f", help="Follow the logs")] = False,
    color: Annotated[
        str,
        typer.Option(
            "--color",
            help="Color output: auto, always, never",
        ),
    ] = "auto",
) -> None:
    """Show recent output from a session."""
    from shoal.cli.session_view import logs

    logs(session=session, lines=lines, tail=tail, color=color)


@app.command("attach")
def _attach_cmd(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    from shoal.cli.session import attach

    attach(session)


@app.command("detach")
def _detach_cmd() -> None:
    """Detach from current session."""
    from shoal.cli.session import detach

    detach()


@app.command("fork")
def _fork_cmd(
    session: Annotated[str | None, typer.Argument(help="Session to fork")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="New session name")] = None,
    no_worktree: Annotated[
        bool, typer.Option("--no-worktree", help="Fork without creating a worktree")
    ] = False,
    mcp: Annotated[
        str | None,
        typer.Option("--mcp", help="MCP servers to provision (comma-separated)"),
    ] = None,
) -> None:
    """Fork a session into a new worktree (or standalone session with --no-worktree)."""
    from shoal.cli.session_create import fork

    fork(session, name, no_worktree, mcp)


@app.command("kill")
def _kill_cmd(
    session: Annotated[str | None, typer.Argument(help="Session to kill")] = None,
    worktree: Annotated[
        bool, typer.Option("--worktree", help="Also remove the git worktree")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force kill even with dirty worktree")
    ] = False,
) -> None:
    """Kill a session."""
    from shoal.cli.session_create import kill

    kill(session, worktree, force)


@app.command("prune")
def _prune_cmd(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Do not ask for confirmation")
    ] = False,
) -> None:
    """Remove all sessions marked as stopped."""
    from shoal.cli.session import prune

    prune(force)


@app.command("status")
def _status_cmd(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich panel) or plain (simple text for completions)",
        ),
    ] = None,
) -> None:
    """Quick status summary."""
    from shoal.cli.session_view import status

    status(format=format)


@app.command("send", hidden=True)
def _send_cmd(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    keys: Annotated[str, typer.Argument(help="Keys to send (empty string sends Enter)")],
) -> None:
    """Send keys to a session's tmux pane."""
    from shoal.cli.session import send

    send(session, keys)


@app.command("popup")
def _popup_cmd() -> None:
    """Open tmux popup dashboard."""
    from shoal.cli.session import popup

    popup()


@app.command("diag")
def _diag_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Check Shoal component health."""
    from shoal.cli.diag import diag

    diag(json_output=json_output)


@app.command("history")
def _history_cmd(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max transitions to show")] = 50,
) -> None:
    """Show status transition history for a session."""
    from shoal.cli.history import history

    history(session=session, limit=limit)


@app.command("journal")
def _journal_cmd(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    append: Annotated[str | None, typer.Option("--append", "-a", help="Append entry text")] = None,
    source: Annotated[str, typer.Option("--source", "-s", help="Entry source tag")] = "cli",
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Show last N entries")] = None,
    archived: Annotated[
        bool, typer.Option("--archived", help="Read from archived journal")
    ] = False,
    search: Annotated[
        str | None, typer.Option("--search", help="Search across all journals")
    ] = None,
    handoff: Annotated[
        bool,
        typer.Option(
            "--handoff",
            help="Generate a structured handoff summary for the session",
        ),
    ] = False,
) -> None:
    """View or append to a session journal."""
    from shoal.cli.journal import journal_view

    journal_view(
        session=session,
        append=append,
        source=source,
        limit=limit,
        archived=archived,
        search=search,
        handoff=handoff,
    )


@app.command("handoff")
def _handoff_cmd(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    save: Annotated[bool, typer.Option("--save", help="Save artifact to disk")] = False,
) -> None:
    """Generate and display a handoff summary for a session."""
    from shoal.cli.handoff import handoff_show

    handoff_show(session=session, as_json=as_json, save=save)


@app.command("handoff-ls", hidden=True)
def _handoff_ls_cmd() -> None:
    """List saved handoff artifacts."""
    from shoal.cli.handoff import handoff_ls

    handoff_ls()


@app.command("done")
def _done_cmd(
    name: str = typer.Argument(..., help="Session name."),
    summary: str = typer.Option(
        "", "--summary", "-s", help="Completion summary written to journal."
    ),
) -> None:
    """Mark a session as complete."""
    from shoal.cli.session import session_done

    session_done(name=name, summary=summary)


# Aliases (hidden)
@app.command("i", hidden=True)
def _info_alias(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """Show detailed information about a session."""
    from shoal.cli.session_view import info

    info(session=session, color=color)


@app.command("mv", hidden=True)
def _rename_alias(
    old_name: Annotated[str, typer.Argument(help="Current session name or ID")],
    new_name: Annotated[str, typer.Argument(help="New name for the session")],
) -> None:
    """Rename a session."""
    from shoal.cli.session import rename

    rename(old_name, new_name)


@app.command("l", hidden=True)
def _logs_alias(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 20,
    tail: Annotated[bool, typer.Option("--tail", "-f", help="Follow the logs")] = False,
    color: Annotated[
        str, typer.Option("--color", help="Color output: auto, always, never")
    ] = "auto",
) -> None:
    """Show recent output from a session."""
    from shoal.cli.session_view import logs

    logs(session=session, lines=lines, tail=tail, color=color)


@app.command("a", hidden=True)
def _attach_alias(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    from shoal.cli.session import attach

    attach(session)


@app.command("d", hidden=True)
def _detach_alias() -> None:
    """Detach from current session."""
    from shoal.cli.session import detach

    detach()


@app.command("rm", hidden=True)
def _kill_alias(
    session: Annotated[str | None, typer.Argument(help="Session to kill")] = None,
    worktree: Annotated[
        bool, typer.Option("--worktree", help="Also remove the git worktree")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force kill even with dirty worktree")
    ] = False,
) -> None:
    """Kill a session."""
    from shoal.cli.session_create import kill

    kill(session, worktree, force)


@app.command("st", hidden=True)
def _status_alias(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich panel) or plain (simple text for completions)",
        ),
    ] = None,
) -> None:
    """Quick status summary."""
    from shoal.cli.session_view import status

    status(format=format)


@app.command("pop", hidden=True)
def _popup_alias() -> None:
    """Open tmux popup dashboard."""
    from shoal.cli.session import popup

    popup()


# Sub-groups
app.add_typer(wt_app, name="wt", help="Worktree management.")
app.add_typer(wt_app, name="worktree", hidden=True)
app.add_typer(mcp_app, name="mcp", help="MCP server pool.")
app.add_typer(robo_app, name="robo", help="Robo (supervisory agent).")
app.add_typer(nvim_app, name="nvim", help="Neovim integration.")
app.add_typer(watcher_app, name="watcher", help="Background status watcher.")
app.add_typer(demo_app, name="demo", help="Demo environment.")
app.add_typer(remote_app, name="remote", help="Remote session management.")
app.add_typer(setup_app, name="setup", help="Setup shell integrations.")
app.add_typer(tag_app, name="tag", help="Session tags.")
app.add_typer(template_app, name="template", help="Session templates.")
app.add_typer(config_app, name="config", help="Configuration inspection.")
app.add_typer(incident_app, name="incident", help="Incident supervision workflow.")
app.add_typer(fin_app, name="fin", help="Fin extension lifecycle.")
app.add_typer(mode_app, name="mode", help="Operating modes.")


@app.command()
def version() -> None:
    """Print version."""
    print(f"shoal {shoal.__version__}")


def _check_environment() -> None:
    """Shared helper: display dependency check and directory status."""
    import shutil

    from rich.console import Console
    from rich.table import Table

    from shoal.core.config import config_dir, data_dir, state_dir
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

    for dir_name, dir_path in [
        ("Config", config_dir()),
        ("Data", data_dir()),
        ("State", state_dir()),
    ]:
        exists = "[green]exists[/green]" if dir_path.exists() else "[yellow]not created[/yellow]"
        dir_info.add_row(dir_name, f"{dir_path} [dim]({exists})[/dim]")

    console.print(
        create_panel(
            dir_info,
            title=f"[bold blue]{Icons.DIRECTORY} Directories[/bold blue]",
            title_align="left",
        )
    )


@app.command()
def init(
    bare: bool = typer.Option(False, "--bare", help="Skip scaffolding default config files."),
    refresh_tools_flag: bool = typer.Option(
        False,
        "--refresh-tools",
        help="Re-copy bundled tool profiles, overwriting any existing ones.",
    ),
) -> None:
    """Initialize Shoal configuration and directories."""
    from rich.console import Console

    from shoal.core.config import ensure_dirs, refresh_tools, scaffold_defaults
    from shoal.services.lifecycle import reconcile_mcp_pool

    console = Console()
    ensure_dirs()

    # Scaffold default configs (tools, templates, config.toml)
    if not bare:
        created = scaffold_defaults()
        if created:
            console.print(f"[green]Scaffolded {len(created)} config file(s):[/green]")
            for path in created:
                console.print(f"  [dim]{path}[/dim]")
        else:
            console.print("[dim]Config files already exist, nothing to scaffold.[/dim]")

    # Clean stale MCP sockets/PIDs from reboots or crashes
    cleaned = reconcile_mcp_pool()
    if cleaned:
        console.print(
            f"[yellow]Cleaned {len(cleaned)} stale MCP socket(s): {', '.join(cleaned)}[/yellow]"
        )

    _check_environment()
    console.print("\n[green]Shoal initialized successfully![/green]")

    if refresh_tools_flag:
        refreshed = refresh_tools()
        if refreshed:
            console.print(f"[green]Refreshed {len(refreshed)} tool profile(s):[/green]")
            for name in refreshed:
                console.print(f"  [dim]{name}[/dim]")
        else:
            console.print("[yellow]No bundled tool profiles found.[/yellow]")

    from shoal.core.theme import create_panel

    console.print(
        create_panel(
            """[bold]Next steps:[/bold]
  1. [yellow]shoal setup fish[/yellow]        Install fish shell integration
  2. [yellow]shoal demo tutorial[/yellow]     Hands-on guided walkthrough
  3. [yellow]shoal demo start[/yellow]        Launch demo environment
  4. [yellow]shoal new[/yellow]               Create your first real session""",
            title="[bold cyan]Get Started[/bold cyan]",
            title_align="left",
        )
    )


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

    async def _impl() -> None:
        from shoal.core.state import get_session

        sid = session_id
        if not sid:
            return
        s = await get_session(sid)
        if s:
            print(s.model_dump_json(indent=2))

    from shoal.core.db import with_db

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
