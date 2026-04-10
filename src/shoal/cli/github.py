"""CLI commands for GitHub PR and issue workflow."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from shoal.cli._console import get_console
from shoal.core.state import add_tag, resolve_session
from shoal.services.github_bridge import get_github_bridge

app = typer.Typer(no_args_is_help=True)


@app.command("ls-prs")
def prs_ls(
    repo: Annotated[str, typer.Option("--repo", help="GitHub repository (owner/repo)")],
    state: str = typer.Option("open", "--state", help="PR state (open/closed/all)"),
) -> None:
    """List pull requests for a GitHub repository."""
    asyncio.run(_prs_ls_impl(repo, state=state))


async def _prs_ls_impl(repo: str, *, state: str) -> None:
    console = get_console()
    try:
        bridge = get_github_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        prs = await bridge.list_prs(repo, state=state)
    finally:
        await bridge.close()

    if not prs:
        console.print("[dim]No pull requests found.[/dim]")
        return

    table = Table(title=f"PRs for {repo}")
    table.add_column("Number", style="bold")
    table.add_column("Title", max_width=60)
    table.add_column("State")
    table.add_column("User")

    for pr in prs:
        table.add_row(
            str(pr.number),
            pr.title,
            pr.state,
            pr.user,
        )

    console.print(table)


@app.command("start-pr")
def pr_start(
    repo: Annotated[str, typer.Argument(help="GitHub repository (owner/repo)")],
    number: Annotated[int, typer.Argument(help="PR number")],
    tool: str | None = typer.Option(None, "--tool", "-t", help="Override AI tool"),
    template: str | None = typer.Option(None, "--template", help="Override session template"),
) -> None:
    """Create a shoal session from a GitHub PR."""
    asyncio.run(_pr_start_impl(repo, number, tool=tool, template=template))


async def _pr_start_impl(repo: str, number: int, *, tool: str | None, template: str | None) -> None:
    from shoal.cli.session_create import _add_impl

    console = get_console()
    try:
        bridge = get_github_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        pr = await bridge.get_pr(repo, number)
    finally:
        await bridge.close()

    # Derive session name from PR number
    session_name = f"gh-{repo.replace('/', '-')}-{number}"

    console.print(f"[bold]Starting session for PR #{number}:[/bold] {pr.title}")
    console.print(f"[dim]Session: {session_name} | Template: {template or 'default'}[/dim]")

    await _add_impl(
        path=None,
        tool=tool,
        template=template,
        mode=None,
        worktree=None,
        branch=False,
        dry_run=False,
        name=session_name,
        mcp_servers=None,
        repo=None,
    )

    # Tag session with the GitHub PR
    sid = await resolve_session(session_name)
    if sid:
        await add_tag(sid, f"github:{repo}#{number}")


@app.command("done-pr")
def pr_done(
    repo: Annotated[str, typer.Argument(help="GitHub repository (owner/repo)")],
    number: Annotated[int, typer.Argument(help="PR number")],
) -> None:
    """Post session handoff and close GitHub PR."""
    asyncio.run(_pr_done_impl(repo, number))


async def _pr_done_impl(repo: str, number: int) -> None:
    from shoal.core.journal import generate_handoff, read_journal
    from shoal.core.state import list_sessions

    console = get_console()

    # Find the session tagged with this PR
    sessions = await list_sessions()
    target_session = None
    for s in sessions:
        if f"github:{repo}#{number}" in s.tags:
            target_session = s
            break

    if not target_session:
        console.print(f"[red]No session found tagged with github:{repo}#{number}[/red]")
        raise typer.Exit(1)

    # Generate handoff
    entries = read_journal(target_session.id)
    handoff = generate_handoff(target_session, entries, [])

    try:
        bridge = get_github_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        comment_body = f"## Session Handoff: {target_session.name}\n\n{handoff.to_markdown()}"
        await bridge.add_comment(repo, number, comment_body)
        console.print(f"[green]Posted handoff to PR #{number}[/green]")

        await bridge.close_pr(repo, number)
        console.print(f"[green]GitHub PR #{number} -> closed[/green]")
    finally:
        await bridge.close()

    console.print(f"[bold green]PR {number} marked done.[/bold green]")
