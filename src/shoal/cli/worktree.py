"""Worktree management commands: ls, finish, cleanup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import git, tmux
from shoal.core.config import ensure_dirs
from shoal.core.state import (
    delete_session,
    get_session,
    list_sessions,
    resolve_session_interactive,
    update_session,
)
from shoal.models.state import SessionStatus

console = Console()

app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def wt_default(ctx: typer.Context) -> None:
    """Worktree management (default: ls)."""
    if ctx.invoked_subcommand is None:
        wt_ls()


@app.command("ls")
def wt_ls() -> None:
    """List managed worktrees."""
    asyncio.run(_wt_ls_impl())


async def _wt_ls_impl():
    ensure_dirs()
    sessions = await list_sessions()

    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
    table.add_column("SESSION", width=20)
    table.add_column("ID", style="dim", width=8)
    table.add_column("BRANCH", width=30)
    table.add_column("WORKTREE", width=40)
    table.add_column("STATUS")

    worktree_sessions = [s for s in sessions if s.worktree]
    for s in worktree_sessions:
        wt_exists = "[green]✔[/green]"
        status_val = s.status.value

        status_style = {
            "running": "green",
            "waiting": "bold yellow",
            "error": "bold red",
            "stopped": "dim",
        }.get(status_val, "")

        if not Path(s.worktree).is_dir():
            wt_exists = "[red]✘[/red]"
            status_text = "[red]missing[/red]"
        else:
            status_text = (
                f"[{status_style}]{status_val}[/{status_style}]" if status_style else status_val
            )

        short_wt = s.worktree.replace(str(Path.home()), "~")
        table.add_row(
            f"[bold]{s.name}[/bold]",
            s.id,
            f"[magenta]{s.branch}[/magenta]",
            short_wt,
            f"{wt_exists} {status_text}",
        )

    if worktree_sessions:
        from rich.panel import Panel

        console.print(
            Panel(
                table,
                title="[bold blue]󱉭 Managed Worktrees[/bold blue]",
                title_align="left",
                border_style="dim",
            )
        )
    else:
        console.print("[yellow]No worktrees managed by shoal[/yellow]")


@app.command("finish")
def wt_finish(
    session: Annotated[str | None, typer.Argument(help="Session to finish")] = None,
    pr: Annotated[bool, typer.Option("--pr", help="Open a PR via gh")] = False,
    no_merge: Annotated[bool, typer.Option("--no-merge", help="Just clean up")] = False,
) -> None:
    """Merge and cleanup a worktree session."""
    asyncio.run(_wt_finish_impl(session, pr, no_merge))


async def _wt_finish_impl(session, pr, no_merge):
    ensure_dirs()
    sid = resolve_session_interactive(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not s.worktree:
        console.print(f"[red]Session '{s.name}' has no worktree to finish[/red]")
        raise typer.Exit(1)

    console.print(f"Finishing session: {s.name}")
    console.print(f"  Branch: {s.branch}")
    console.print(f"  Worktree: {s.worktree}")
    console.print()

    # Kill tmux session
    if tmux.has_session(s.tmux_session):
        tmux.kill_session(s.tmux_session)
        console.print("  Killed tmux session")

    # Handle merge/PR
    if not no_merge:
        if pr:
            console.print(f"  Opening PR for branch: {s.branch}")
            git.push(s.worktree, s.branch, set_upstream=True)
            import subprocess

            subprocess.run(
                ["gh", "pr", "create", "--head", s.branch, "--fill", "--web"],
                cwd=s.worktree,
                check=False,
            )
        else:
            console.print(f"  Merging {s.branch} into main...")
            main = git.main_branch(s.path)
            git.checkout(s.path, main)
            if not git.merge(s.path, s.branch):
                console.print("  [red]Merge failed — resolve conflicts manually[/red]")
                console.print(f"  Worktree preserved at: {s.worktree}")
                raise typer.Exit(1)
            console.print("  Merged successfully")

    # Remove worktree
    if Path(s.worktree).is_dir():
        if git.worktree_remove(s.path, s.worktree, force=True):
            console.print("  Removed worktree")
        else:
            console.print(
                f"  [yellow]Warning: Failed to remove worktree"
                f" (try: git worktree remove {s.worktree} --force)[/yellow]"
            )

    # Delete branch (if not main/master and not using PR)
    if (
        not pr
        and s.branch
        and s.branch not in ("main", "master")
        and git.branch_delete(s.path, s.branch)
    ):
        console.print(f"  Deleted branch: {s.branch}")

    await delete_session(sid)
    console.print()
    console.print(f"Session '{s.name}' finished and cleaned up")


@app.command("cleanup")
def wt_cleanup() -> None:
    """Remove orphaned worktrees."""
    asyncio.run(_wt_cleanup_impl())


async def _wt_cleanup_impl():
    ensure_dirs()

    # Collect tracked worktrees
    tracked: set[str] = set()
    stale: list[str] = []

    sessions = await list_sessions()
    for s in sessions:
        if s.worktree:
            tracked.add(s.worktree)

        # Find stale sessions (tmux session gone but not marked stopped)
        if s.status.value != "stopped" and not tmux.has_session(s.tmux_session):
            stale.append(s.id)

    # Report stale sessions
    if stale:
        console.print("Stale sessions (tmux session gone):")
        for sid in stale:
            s = await get_session(sid)
            if s:
                console.print(f"  {s.name} ({sid}) — marking as stopped")
                await update_session(sid, status=SessionStatus.stopped)
        console.print()

    # Find orphaned worktrees
    checked_repos: set[str] = set()
    orphans: list[str] = []

    for s in sessions:
        if s.path in checked_repos:
            continue
        checked_repos.add(s.path)

        wt_base = Path(s.path) / ".worktrees"
        if wt_base.is_dir():
            for wt_dir in wt_base.iterdir():
                if wt_dir.is_dir() and str(wt_dir) not in tracked:
                    orphans.append(str(wt_dir))

    if not orphans:
        console.print("No orphaned worktrees found")
        return

    console.print("Orphaned worktrees (not tracked by any session):")
    for wt in orphans:
        console.print(f"  {wt.replace(str(Path.home()), '~')}")
    console.print()

    confirm = typer.confirm("Remove these worktrees?", default=False)
    if not confirm:
        console.print("Aborted")
        return

    for wt in orphans:
        try:
            repo = git.git_root(wt)
        except Exception:
            repo = str(Path(wt).parent.parent)
        if git.worktree_remove(repo, wt, force=True):
            console.print(f"  Removed: {wt}")
        else:
            console.print(f"  [red]Failed: {wt}[/red]")

    console.print("Cleanup complete")
