"""CLI commands for Linear ticket workflow."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Annotated

import typer
from rich.table import Table

from shoal.cli._console import get_console
from shoal.cli._helpers import init_bridge, resolve_team_config
from shoal.core import git
from shoal.core.config import load_workspace_config
from shoal.core.db import with_db

if TYPE_CHECKING:
    from shoal.models.config.workspace import TeamConfig

app = typer.Typer(no_args_is_help=True)


def _session_context_from_team_config(team_cfg: TeamConfig | None) -> str:
    """Return session context prefix for team-backed sessions."""
    if team_cfg and team_cfg.worktree_dir.strip():
        candidate = team_cfg.worktree_dir.strip().strip("/").split("/")[0]
        if candidate:
            return candidate
    return "work"


async def _emit_binding_change(
    session_id: str, *, binding_type: str, action: str, identifier: str, name: str
) -> None:
    """Best-effort bridge to Arachne binding-change hooks if installed."""
    try:
        try:
            from arachne.hooks import on_session_binding_changed
        except ImportError:
            from ploom.hooks import on_session_binding_changed
    except ImportError:
        return
    await on_session_binding_changed(
        session_id,
        binding_type=binding_type,
        action=action,
        identifier=identifier,
        name=name,
    )


async def _attach_issue_tag(
    session_id: str,
    session_name: str,
    issue,
    *,
    source: str = "ticket",
    replaced_note: bool = True,
) -> bool:
    from shoal.core.journal import append_entry
    from shoal.core.state import get_session, replace_tag_prefix

    new_tag = f"linear:{issue.identifier}"
    before = await get_session(session_id)
    if before is None:
        return False
    had_tag = new_tag in before.tags
    removed = await replace_tag_prefix(session_id, "linear:", new_tag)
    changed = bool(removed) or not had_tag
    if not changed:
        return False

    if removed and replaced_note:
        old = ", ".join(tag.removeprefix("linear:") for tag in removed)
        append_entry(
            session_id,
            f"Ticket binding replaced: {old} → {issue.identifier}",
            source=source,
        )
    append_entry(
        session_id,
        f"Ticket attached: [{issue.identifier}]({issue.url}) — {issue.title}",
        source=source,
    )
    await _emit_binding_change(
        session_id,
        binding_type="linear",
        action="attach",
        identifier=issue.identifier,
        name=session_name,
    )
    return True


async def _detach_issue_tags(session_id: str, session_name: str) -> list[str]:
    from shoal.core.journal import append_entry
    from shoal.core.state import remove_tags_with_prefix

    removed = await remove_tags_with_prefix(session_id, "linear:")
    if not removed:
        return []
    identifiers = [tag.removeprefix("linear:") for tag in removed]
    append_entry(
        session_id,
        f"Ticket detached: {', '.join(identifiers)}",
        source="ticket",
    )
    for identifier in identifiers:
        await _emit_binding_change(
            session_id,
            binding_type="linear",
            action="detach",
            identifier=identifier,
            name=session_name,
        )
    return removed


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
    _root, team_cfg = resolve_team_config(team_slug)

    bridge = init_bridge(get_linear_bridge)
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
    from shoal.core.state import resolve_session
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()

    bridge = init_bridge(get_linear_bridge)
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

    # Derive worktree name: build a canonical feat/{id}-{slug} name from the
    # issue identifier and title. Linear's branchName is user-scoped and uses
    # a non-standard category prefix (e.g. "ricardoroche/aia-469-...") that
    # fails Shoal's category/slug validation — so we always construct our own.
    _id_slug = issue.identifier.lower()
    _title_slug = re.sub(r"[^a-z0-9]+", "-", issue.title.lower()).strip("-")[:40].rstrip("-")
    worktree_name = f"feat/{_id_slug}-{_title_slug}" if _title_slug else f"feat/{_id_slug}"

    # Derive session name from issue identifier with context prefix for Arachne linking
    session_context = _session_context_from_team_config(team_cfg)
    session_name = f"{session_context}/{issue.identifier.lower()}"

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
        await _attach_issue_tag(
            sid,
            session_name,
            issue,
            source="ticket",
            replaced_note=False,
        )

    # Update Linear status to In Progress
    bridge2 = init_bridge(get_linear_bridge)
    try:
        await bridge2.update_issue_state(issue.id, "In Progress")
        console.print(f"[green]Linear {issue.identifier} -> In Progress[/green]")
    except RuntimeError as exc:
        console.print(f"[yellow]Warning: Could not update Linear status: {exc}[/yellow]")
    finally:
        await bridge2.close()


@app.command("attach")
def ticket_attach(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
    issue_id: Annotated[str, typer.Argument(help="Linear issue identifier (e.g. BE-1234)")],
) -> None:
    """Attach a Linear ticket to an existing session."""
    asyncio.run(with_db(_ticket_attach_impl(session, issue_id)))


async def _ticket_attach_impl(session: str, issue_id: str) -> None:
    from shoal.core.state import get_session, resolve_session
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    state = await get_session(sid)
    if not state:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    bridge = init_bridge(get_linear_bridge)
    try:
        issue = await bridge.get_issue(issue_id)
    finally:
        await bridge.close()

    if not issue:
        console.print(f"[red]Issue not found: {issue_id}[/red]")
        raise typer.Exit(1)

    changed = await _attach_issue_tag(sid, state.name, issue)
    if not changed:
        console.print(f"[yellow]Session already attached to {issue.identifier}[/yellow]")
        return

    console.print(f"[green]Attached {issue.identifier} to {state.name}[/green]")


@app.command("detach")
def ticket_detach(
    session: Annotated[str, typer.Argument(help="Session name or ID")],
) -> None:
    """Detach Linear ticket bindings from a session."""
    asyncio.run(with_db(_ticket_detach_impl(session)))


async def _ticket_detach_impl(session: str) -> None:
    from shoal.core.state import get_session, resolve_session

    console = get_console()
    sid = await resolve_session(session)
    if not sid:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)
    state = await get_session(sid)
    if not state:
        console.print(f"[red]Session not found: {session}[/red]")
        raise typer.Exit(1)

    removed = await _detach_issue_tags(sid, state.name)
    if not removed:
        console.print(f"[yellow]No Linear ticket binding found for {state.name}[/yellow]")
        return

    detached = ", ".join(tag.removeprefix("linear:") for tag in removed)
    console.print(f"[green]Detached {detached} from {state.name}[/green]")


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
    bridge = init_bridge(get_linear_bridge)
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


@app.command("sync")
def ticket_sync(
    team: Annotated[
        str | None, typer.Option("--team", "-t", help="Team slug to sync (e.g. be, fe)")
    ] = None,
    all_teams: bool = typer.Option(False, "--all", help="Sync all configured teams"),
) -> None:
    """Sync Linear issues to local cache for fast queries."""
    asyncio.run(with_db(_ticket_sync_impl(team=team, all_teams=all_teams)))


async def _ticket_sync_impl(*, team: str | None, all_teams: bool) -> None:
    from shoal.services.linear_cache import get_linear_cache

    console = get_console()
    cache = get_linear_cache()

    # Resolve teams to sync
    teams_to_sync: list[str] = []
    if all_teams:
        root = git.git_root(".")
        ws_cfg = load_workspace_config(root)
        if ws_cfg and ws_cfg.teams:
            teams_to_sync = [t.linear_slug for t in ws_cfg.teams.values()]
    elif team:
        _root, team_cfg = resolve_team_config(team)
        teams_to_sync = [team_cfg.linear_slug]
    else:
        console.print("[red]Specify --team <slug> or --all[/red]")
        raise typer.Exit(1)

    if not teams_to_sync:
        console.print("[yellow]No teams to sync.[/yellow]")
        return

    for team_slug in teams_to_sync:
        console.print(f"[dim]Syncing {team_slug}...[/dim]")
        count = await cache.sync_team_issues(team_slug)
        console.print(f"[green]Synced {count} issues for {team_slug}[/green]")


@app.command("pick")
def ticket_pick(
    team: Annotated[
        list[str] | None, typer.Option("--team", "-t", help="Team slug (can specify multiple)")
    ] = None,
    mine: bool = typer.Option(False, "--mine", help="Only my assigned issues"),
    ready: bool = typer.Option(False, "--ready", help="Only unstarted issues"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Interactively pick a ticket from one or more teams.

    Uses cached issues - run 'shoal ticket sync' first if cache is empty.
    """
    teams = team or []
    asyncio.run(
        with_db(_ticket_pick_impl(teams=teams, mine=mine, ready=ready, json_output=json_output))
    )


@app.command("decompose")
def ticket_decompose(
    issue_id: Annotated[str, typer.Argument(help="Parent issue identifier (e.g. AIA-123)")],
    count: Annotated[int, typer.Option("--count", "-n", help="Number of sub-issues")] = 3,
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
) -> None:
    """Break a parent Linear issue into child sub-issues.

    In dry-run mode (default), displays proposed child issues.
    Use --no-dry-run to create the child issues in Linear.
    """
    asyncio.run(with_db(_ticket_decompose_impl(issue_id, count=count, dry_run=dry_run)))


async def _ticket_pick_impl(
    *, teams: list[str], mine: bool, ready: bool, json_output: bool
) -> None:
    import subprocess

    from shoal.services.linear_bridge import LinearIssue
    from shoal.services.linear_cache import get_linear_cache

    console = get_console()
    cache = get_linear_cache()

    # Default to all configured teams if none specified
    team_keys: list[str] = teams
    if not team_keys:
        root = git.git_root(".")
        ws_cfg = load_workspace_config(root)
        if ws_cfg and ws_cfg.teams:
            team_keys = [t.linear_slug for t in ws_cfg.teams.values()]

    if not team_keys:
        console.print("[red]No teams configured. Add teams to .shoal/workspace.toml[/red]")
        raise typer.Exit(1)

    # Collect issues from all teams
    all_issues: list[tuple[str, LinearIssue]] = []  # (team_key, issue)
    for team_key in team_keys:
        issues = await cache.get_cached_issues(team_key, ready_only=ready)
        all_issues.extend((team_key, issue) for issue in issues)

    if not all_issues:
        console.print("[yellow]No cached issues. Run 'shoal ticket sync' first.[/yellow]")
        raise typer.Exit(1)

    if json_output:
        import json

        data = [
            {
                "id": issue.id,
                "identifier": issue.identifier,
                "title": issue.title,
                "team": team_key,
                "state": issue.state_name,
                "priority": issue.priority,
                "url": issue.url,
            }
            for team_key, issue in all_issues
        ]
        console.print(json.dumps(data, indent=2))
        return

    # Build fzf input
    lines = []
    for team_key, issue in all_issues:
        lines.append(f"{issue.identifier}\t{issue.title}\t{team_key}\t{issue.state_name}")

    # Use fzf for selection
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["fzf", "--tac", "--header=ID\tTitle\tTeam\tState", "--with-nth=1..4"],
            input="\n".join(lines),
            capture_output=True,
            text=True,
            check=True,
        )
        selected = result.stdout.strip().split("\t")
        if selected:
            selected_id = selected[0]
            console.print(f"[green]Selected: {selected_id}[/green]")
            # Could auto-call ticket start here if desired
            console.print(f"[dim]Run: shoal ticket start {selected_id}[/dim]")
    except FileNotFoundError:
        console.print("[red]fzf not found. Install with: brew install fzf[/red]")
        raise typer.Exit(1) from None
    except subprocess.CalledProcessError:
        # User cancelled fzf
        pass


async def _ticket_decompose_impl(issue_id: str, *, count: int, dry_run: bool) -> None:
    from shoal.services.linear_bridge import get_linear_bridge

    console = get_console()

    # Fetch parent issue
    bridge = init_bridge(get_linear_bridge)
    try:
        issue = await bridge.get_issue(issue_id)
        if not issue:
            console.print(f"[red]Issue not found: {issue_id}[/red]")
            raise typer.Exit(1)

        # Generate child issue proposals from description
        proposals = _parse_child_proposals(issue.description, count=count, parent_title=issue.title)

        if not proposals:
            console.print("[yellow]No child issues could be generated from description.[/yellow]")
            console.print(
                "[dim]Try adding bullet points or numbered items to the description.[/dim]"
            )
            raise typer.Exit(0)

        # Display proposals
        console.print(f"[bold]Parent Issue:[/bold] {issue.identifier} — {issue.title}")
        console.print()

        table = Table(title="Proposed Child Issues")
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="bold")
        table.add_column("Description Preview", max_width=50)
        table.add_column("Priority")

        for idx, proposal in enumerate(proposals, start=1):
            desc = proposal["description"]
            if not isinstance(desc, str):
                desc = str(desc)
            preview = desc[:80] + "..." if len(desc) > 80 else desc
            title = proposal["title"]
            if not isinstance(title, str):
                title = str(title)
            priority = proposal["priority"]
            if not isinstance(priority, int):
                priority = 3
            table.add_row(
                str(idx),
                title,
                preview,
                _priority_label(priority),
            )

        console.print(table)

        # Create issues if not dry-run
        if dry_run:
            console.print()
            console.print("[dim]Dry-run mode: use --no-dry-run to create these issues.[/dim]")
        else:
            console.print()
            console.print("[bold]Creating child issues...[/bold]")
            created: list[dict[str, str]] = []

            for proposal in proposals:
                try:
                    title_obj = proposal["title"]
                    title_str = title_obj if isinstance(title_obj, str) else str(title_obj)
                    desc_obj = proposal["description"]
                    desc_str = desc_obj if isinstance(desc_obj, str) else str(desc_obj)
                    priority_obj = proposal["priority"]
                    priority_int = priority_obj if isinstance(priority_obj, int) else 3

                    result = await bridge.create_issue(
                        team_id=issue.team_id,
                        title=title_str,
                        description=desc_str,
                        parent_id=issue.id,
                        priority=priority_int,
                    )
                    created.append(result)
                    ident = result["identifier"]
                    title = result["title"]
                    console.print(f"[green]✓[/green] Created {ident}: {title}")
                except RuntimeError as exc:
                    prop_title = proposal["title"]
                    console.print(f"[yellow]✗ Failed to create '{prop_title}': {exc}[/yellow]")

            if created:
                console.print()
                console.print(f"[bold green]Created {len(created)} child issues.[/bold green]")
                for child in created:
                    console.print(f"  • {child['identifier']}: {child['url']}")

    finally:
        await bridge.close()


def _parse_child_proposals(
    description: str, *, count: int, parent_title: str
) -> list[dict[str, object]]:
    """Extract child issue proposals from parent description.

    Simple heuristic-based parser that looks for:
    - Numbered lists (1. 2. 3.)
    - Bullet points (- * •)
    - Headings (## ###)

    Returns a list of dicts with keys: title, description, priority.
    """
    if not description or not description.strip():
        return []

    lines = description.strip().split("\n")
    proposals: list[dict[str, object]] = []

    # Pattern 1: Numbered lists
    import re

    numbered_pattern = re.compile(r"^\s*\d+\.\s+(.+)$")
    for line in lines:
        match = numbered_pattern.match(line)
        if match and len(proposals) < count:
            title_text = match.group(1).strip()
            proposals.append(
                {
                    "title": title_text,
                    "description": f"Sub-task of {parent_title}\n\n{title_text}",
                    "priority": 3,  # Medium priority by default
                }
            )

    # Pattern 2: Bullet points (if numbered didn't yield enough)
    if len(proposals) < count:
        bullet_pattern = re.compile(r"^\s*[-*•]\s+(.+)$")
        for line in lines:
            match = bullet_pattern.match(line)
            if match and len(proposals) < count:
                title_text = match.group(1).strip()
                # Skip if already added from numbered list
                if not any(p["title"] == title_text for p in proposals):
                    proposals.append(
                        {
                            "title": title_text,
                            "description": f"Sub-task of {parent_title}\n\n{title_text}",
                            "priority": 3,
                        }
                    )

    # Pattern 3: Headings (if still not enough)
    if len(proposals) < count:
        heading_pattern = re.compile(r"^\s*#{2,3}\s+(.+)$")
        for line in lines:
            match = heading_pattern.match(line)
            if match and len(proposals) < count:
                title_text = match.group(1).strip()
                if not any(p["title"] == title_text for p in proposals):
                    proposals.append(
                        {
                            "title": title_text,
                            "description": f"Sub-task of {parent_title}\n\n{title_text}",
                            "priority": 3,
                        }
                    )

    return proposals[:count]
