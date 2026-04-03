"""CLI commands for Linear ticket workflow."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from shoal.cli._console import get_console
from shoal.core import git
from shoal.core.config import load_workspace_config
from shoal.core.db import with_db
from shoal.models.config.workspace import TeamConfig

app = typer.Typer(no_args_is_help=True)


def _resolve_team_config(team_slug: str) -> tuple[str, TeamConfig]:
    """Look up a team by slug from workspace config.

    Returns:
        Tuple of (git_root, TeamConfig).

    Raises:
        typer.Exit: If workspace config or team is not found.
    """
    console = get_console()
    root = git.git_root(".")
    ws_cfg = load_workspace_config(root)
    if not ws_cfg or not ws_cfg.teams:
        console.print("[red]No teams configured in .shoal/workspace.toml[/red]")
        raise typer.Exit(1)

    team = ws_cfg.teams.get(team_slug)
    if not team:
        available = ", ".join(sorted(ws_cfg.teams.keys()))
        console.print(f"[red]Unknown team '{team_slug}'. Available: {available}[/red]")
        raise typer.Exit(1)

    return root, team


def _priority_label(p: int) -> str:
    """Format a Linear priority integer as a short label."""
    return {1: "P1", 2: "P2", 3: "P3", 4: "P4"}.get(p, "--")


@app.command("ls")
def ticket_ls(
    team: Annotated[str, typer.Option("--team", help="Team slug (e.g. be, fe)")],
    mine: bool = typer.Option(False, "--mine", help="Only my assigned issues"),
    ready: bool = typer.Option(False, "--ready", help="Only unstarted issues"),
) -> None:
    """List Linear issues for a team."""
    asyncio.run(with_db(_ticket_ls_impl(team, mine=mine, ready=ready)))


async def _ticket_ls_impl(team_slug: str, *, mine: bool, ready: bool) -> None:
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()
    _root, team_cfg = _resolve_team_config(team_slug)

    try:
        bridge = get_linear_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        issues = await bridge.list_team_issues(
            team_cfg.linear_slug, ready_only=ready, mine_only=mine
        )
    finally:
        await bridge.close()

    if not issues:
        console.print("[dim]No issues found.[/dim]")
        return

    table = Table(title=f"{team_cfg.name or team_slug} Issues")
    table.add_column("ID", style="bold")
    table.add_column("Pri")
    table.add_column("Title", max_width=60)
    table.add_column("State")
    table.add_column("Assignee")

    for issue in issues:
        table.add_row(
            issue.identifier,
            _priority_label(issue.priority),
            issue.title,
            issue.state_name,
            issue.assignee_name or "[dim]--[/dim]",
        )

    console.print(table)


@app.command("start")
def ticket_start(
    issue_id: Annotated[str, typer.Argument(help="Linear issue identifier (e.g. BE-1234)")],
    tool: str | None = typer.Option(None, "--tool", "-t", help="Override AI tool"),
    template: str | None = typer.Option(None, "--template", help="Override session template"),
) -> None:
    """Create a shoal session from a Linear issue."""
    asyncio.run(with_db(_ticket_start_impl(issue_id, tool=tool, template=template)))


async def _ticket_start_impl(issue_id: str, *, tool: str | None, template: str | None) -> None:
    from shoal.cli.session_create import _add_impl
    from shoal.core.journal import append_entry
    from shoal.core.state import add_tag, resolve_session
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()

    try:
        bridge = get_linear_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        issue = await bridge.get_issue(issue_id)
    finally:
        await bridge.close()

    if not issue:
        console.print(f"[red]Issue not found: {issue_id}[/red]")
        raise typer.Exit(1)

    # Resolve team config from the issue identifier prefix (e.g. "BE" from "BE-1234")
    prefix = issue.identifier.split("-")[0].upper()
    root = git.git_root(".")
    ws_cfg = load_workspace_config(root)
    team_cfg: TeamConfig | None = None
    if ws_cfg:
        for cfg in ws_cfg.teams.values():
            if cfg.linear_slug.upper() == prefix:
                team_cfg = cfg
                break

    # Resolve template: flag > team config > None (let add_impl use defaults)
    resolved_template = template or (team_cfg.default_template if team_cfg else None)

    # Derive worktree name from Linear branch suggestion or issue identifier
    worktree_name = issue.branch_name or f"{prefix.lower()}/{issue.identifier.lower()}"

    # Derive session name from issue identifier
    session_name = issue.identifier.lower()

    # Resolve repo for workspace routing
    repo = team_cfg.worktree_dir if team_cfg else None

    console.print(f"[bold]Starting session for {issue.identifier}:[/bold] {issue.title}")
    console.print(
        f"[dim]Branch: {worktree_name} | Template: {resolved_template or 'default'}[/dim]"
    )

    # Delegate to the standard session creation path
    await _add_impl(
        path=None,
        tool=tool,
        template=resolved_template,
        mode=None,
        worktree=worktree_name,
        branch=True,
        dry_run=False,
        name=session_name,
        mcp_servers=None,
        repo=repo,
    )

    # Tag session with the Linear issue
    sid = await resolve_session(session_name)
    if sid:
        await add_tag(sid, f"linear:{issue.identifier}")
        append_entry(
            sid,
            f"Ticket started: [{issue.identifier}]({issue.url}) — {issue.title}",
            source="ticket",
        )

    # Update Linear status to In Progress
    bridge2 = get_linear_bridge()
    try:
        await bridge2.update_issue_state(issue.id, "In Progress")
        console.print(f"[green]Linear {issue.identifier} -> In Progress[/green]")
    except RuntimeError as exc:
        console.print(f"[yellow]Warning: Could not update Linear status: {exc}[/yellow]")
    finally:
        await bridge2.close()


@app.command("done")
def ticket_done(
    issue_id: Annotated[str | None, typer.Argument(help="Linear issue identifier")] = None,
) -> None:
    """Mark a ticket complete and update Linear."""
    asyncio.run(with_db(_ticket_done_impl(issue_id)))


async def _ticket_done_impl(issue_id: str | None) -> None:
    from shoal.core.journal import append_entry, generate_handoff, read_journal
    from shoal.core.state import list_sessions
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()

    # Resolve issue ID: if not provided, find from current session tags
    resolved_id = issue_id
    if not resolved_id:
        sessions = await list_sessions()
        for s in sessions:
            for tag in s.tags:
                if tag.startswith("linear:"):
                    resolved_id = tag.removeprefix("linear:")
                    console.print(f"[dim]Resolved ticket from session tag: {resolved_id}[/dim]")
                    break
            if resolved_id:
                break

    if not resolved_id:
        console.print("[red]No issue ID provided and no active session has a linear: tag.[/red]")
        raise typer.Exit(1)

    # Find the session tagged with this issue
    sessions = await list_sessions()
    target_session = None
    for s in sessions:
        if f"linear:{resolved_id}" in s.tags:
            target_session = s
            break

    if not target_session:
        console.print(f"[red]No session found tagged with linear:{resolved_id}[/red]")
        raise typer.Exit(1)

    # Generate handoff
    entries = read_journal(target_session.id)
    handoff = generate_handoff(target_session, entries, [])

    # Post handoff as Linear comment
    try:
        bridge = get_linear_bridge()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    try:
        issue = await bridge.get_issue(resolved_id)
        if issue:
            comment_body = f"## Session Handoff: {target_session.name}\n\n{handoff.to_markdown()}"
            await bridge.add_issue_comment(issue.id, comment_body)
            console.print(f"[green]Posted handoff to {resolved_id}[/green]")

            await bridge.update_issue_state(issue.id, "Done")
            console.print(f"[green]Linear {resolved_id} -> Done[/green]")
        else:
            console.print(f"[yellow]Warning: Could not find issue {resolved_id} in Linear[/yellow]")
    except RuntimeError as exc:
        console.print(f"[yellow]Warning: Linear update failed: {exc}[/yellow]")
    finally:
        await bridge.close()

    # Journal the completion
    append_entry(
        target_session.id,
        f"Ticket completed: {resolved_id}",
        source="ticket",
    )

    console.print(f"[bold green]Ticket {resolved_id} marked done.[/bold green]")


@app.command("status")
def ticket_status() -> None:
    """Show active ticket-to-session bindings."""
    asyncio.run(with_db(_ticket_status_impl()))


async def _ticket_status_impl() -> None:
    from shoal.core.state import list_sessions

    console = get_console()
    sessions = await list_sessions()

    table = Table(title="Ticket Bindings")
    table.add_column("Issue", style="bold")
    table.add_column("Session")
    table.add_column("Status")
    table.add_column("Created")

    has_bindings = False
    for s in sessions:
        for tag in s.tags:
            if tag.startswith("linear:"):
                issue_id = tag.removeprefix("linear:")
                table.add_row(
                    issue_id,
                    s.name,
                    s.status.value,
                    s.created_at.strftime("%Y-%m-%d %H:%M"),
                )
                has_bindings = True

    if not has_bindings:
        console.print("[dim]No active ticket bindings.[/dim]")
        console.print("[dim]Use 'shoal ticket start <issue-id>' to create one.[/dim]")
        return

    console.print(table)
