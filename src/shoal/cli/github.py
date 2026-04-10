"""CLI commands for GitHub PR and issue workflow."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from shoal.cli._console import get_console
from shoal.cli._helpers import init_bridge
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
    bridge = init_bridge(get_github_bridge)
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
    bridge = init_bridge(get_github_bridge)

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

    bridge = init_bridge(get_github_bridge)

    try:
        comment_body = f"## Session Handoff: {target_session.name}\n\n{handoff.to_markdown()}"
        await bridge.add_comment(repo, number, comment_body)
        console.print(f"[green]Posted handoff to PR #{number}[/green]")

        await bridge.close_pr(repo, number)
        console.print(f"[green]GitHub PR #{number} -> closed[/green]")
    finally:
        await bridge.close()

    console.print(f"[bold green]PR {number} marked done.[/bold green]")


@app.command("review-pr")
def pr_review(
    repo: Annotated[str, typer.Argument(help="GitHub repository (owner/repo)")],
    number: Annotated[int, typer.Argument(help="PR number")],
    template: str = typer.Option("pantheon-review", "--template", help="Session template"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show review prompt without creating session"
    ),
) -> None:
    """Create a review session for a GitHub PR with full context."""
    asyncio.run(_pr_review_impl(repo, number, template=template, dry_run=dry_run))


async def _pr_review_impl(repo: str, number: int, *, template: str, dry_run: bool) -> None:
    from shoal.cli.session_create import _add_impl

    console = get_console()
    bridge = init_bridge(get_github_bridge)

    try:
        # Fetch PR metadata, diff, and comments
        console.print(f"[dim]Fetching PR #{number} from {repo}...[/dim]")
        pr = await bridge.get_pr(repo, number)
        diff = await bridge.get_pr_diff(repo, number)
        comments = await bridge.get_pr_comments(repo, number)
        reviews = await bridge.get_pr_reviews(repo, number)
    finally:
        await bridge.close()

    # Truncate diff if too large (keep first 5000 chars)
    diff_truncated = diff[:5000]
    if len(diff) > 5000:
        diff_truncated += f"\n\n... (truncated {len(diff) - 5000} chars)"

    # Build structured review prompt
    review_prompt = f"""# PR Review: {pr.title}

**Repository**: {repo}
**PR Number**: #{number}
**Author**: {pr.user}
**Base Branch**: {pr.base}
**Head Branch**: {pr.head}
**State**: {pr.state}

## Description

{pr.body or "(No description provided)"}

## Diff

```diff
{diff_truncated}
```

## Existing Comments ({len(comments)})

"""

    if comments:
        for comment in comments[:10]:  # Show first 10 comments
            user = comment.get("user", {}).get("login", "unknown")
            body = comment.get("body", "")
            review_prompt += f"- **{user}**: {body}\n"
        if len(comments) > 10:
            review_prompt += f"\n... and {len(comments) - 10} more comments\n"
    else:
        review_prompt += "(No comments yet)\n"

    review_prompt += f"\n## Reviews ({len(reviews)})\n\n"
    if reviews:
        for review in reviews[:5]:
            user = review.get("user", {}).get("login", "unknown")
            state = review.get("state", "unknown")
            body = review.get("body", "")
            review_prompt += f"- **{user}** ({state}): {body}\n"
        if len(reviews) > 5:
            review_prompt += f"\n... and {len(reviews) - 5} more reviews\n"
    else:
        review_prompt += "(No reviews yet)\n"

    review_prompt += """

---

Please review this PR focusing on:
1. Code quality and correctness
2. Potential bugs or edge cases
3. Security concerns
4. Performance implications
5. Test coverage
6. Documentation completeness

Provide actionable feedback in your review.
"""

    if dry_run:
        console.print("\n[bold]Review Prompt (dry-run):[/bold]")
        console.print(review_prompt)
        return

    # Create session
    session_name = f"gh-review-{repo.replace('/', '-')}-{number}"
    console.print(f"[bold]Creating review session:[/bold] {session_name}")
    console.print(f"[dim]Template: {template}[/dim]")

    await _add_impl(
        path=None,
        tool=None,
        template=template,
        mode=None,
        worktree=None,
        branch=False,
        dry_run=False,
        name=session_name,
        mcp_servers=None,
        repo=None,
    )

    # Tag session
    sid = await resolve_session(session_name)
    if sid:
        await add_tag(sid, f"github:{repo}#{number}")

    # Write prompt to a file in temp directory
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(review_prompt)
        prompt_file = Path(f.name)

    console.print(f"[green]Review session created: {session_name}[/green]")
    console.print(f"[dim]Review context written to: {prompt_file}[/dim]")
    console.print(f"[dim]Attach to the session and read the context with: cat {prompt_file}[/dim]")


@app.command("post-review")
def pr_post_review(
    repo: Annotated[str, typer.Argument(help="GitHub repository (owner/repo)")],
    number: Annotated[int, typer.Argument(help="PR number")],
    session: str | None = typer.Option(
        None, "--session", help="Session name (auto-detect if omitted)"
    ),
) -> None:
    """Post review session journal to GitHub PR as a comment."""
    asyncio.run(_pr_post_review_impl(repo, number, session=session))


async def _pr_post_review_impl(repo: str, number: int, *, session: str | None) -> None:
    from shoal.core.journal import read_journal
    from shoal.core.state import list_sessions

    console = get_console()

    # Find the review session
    if session:
        sid = await resolve_session(session)
        if not sid:
            console.print(f"[red]Session '{session}' not found[/red]")
            raise typer.Exit(1)
        from shoal.core.state import get_session

        target_session = await get_session(sid)
    else:
        # Auto-detect by tag
        sessions = await list_sessions()
        target_session = None
        for s in sessions:
            if f"github:{repo}#{number}" in s.tags:
                target_session = s
                break

        if not target_session:
            console.print(f"[red]No session found tagged with github:{repo}#{number}[/red]")
            raise typer.Exit(1)

    if not target_session:
        console.print("[red]Session not found[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Reading journal from session: {target_session.name}[/dim]")

    # Read journal entries
    entries = read_journal(target_session.id)
    if not entries:
        console.print("[yellow]No journal entries found for this session[/yellow]")
        raise typer.Exit(1)

    # Format as structured review comment
    review_body = f"## Code Review from Shoal Session: {target_session.name}\n\n"
    review_body += f"**Session ID**: {target_session.id}\n"
    review_body += f"**Tool**: {target_session.tool}\n\n"
    review_body += "### Review Summary\n\n"

    for entry in entries:
        review_body += f"**{entry.timestamp.isoformat()}** (`{entry.source}`)\n\n"
        review_body += f"{entry.content}\n\n---\n\n"

    # Post to GitHub
    bridge = init_bridge(get_github_bridge)

    try:
        await bridge.add_comment(repo, number, review_body)
        console.print(f"[green]Review posted to PR #{number}[/green]")
        console.print(f"[dim]Session: {target_session.name}[/dim]")
    finally:
        await bridge.close()
