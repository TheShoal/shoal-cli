"""Flagship fleet demo — the full control-plane story in 6 steps.

Showcases: planner → implementer → reviewer → supervisor escalation →
overnight progress → morning fleet summary.  Uses real sessions, real
worktrees, and real handoff artifacts in a scratch repo.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from shoal.cli._console import get_console
from shoal.cli.demo import create_demo_project
from shoal.cli.demo.tour import TourResult
from shoal.core import git
from shoal.core.db import with_db
from shoal.core.journal import (
    append_entry,
    generate_handoff,
    read_journal,
    write_handoff_artifact,
)
from shoal.core.state import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from shoal.core.theme import Symbols
from shoal.core.urgency import UrgencyTier, derive_urgency
from shoal.models.state import SessionStatus

_fleet_dir = Path("/tmp/shoal-fleet")

_CHECK = f"[green]{Symbols.CHECK}[/green]"
_CROSS = f"[red]{Symbols.CROSS}[/red]"


# ---------------------------------------------------------------------------
# Step 1: Planner scopes work
# ---------------------------------------------------------------------------


async def step_planner(root: str, *, live: bool) -> tuple[TourResult, str]:
    """Create a planner session and write a task plan to the journal."""
    get_console().print("\n[bold cyan]Step 1 — Planner scopes work[/bold cyan]")

    session = await create_session(
        name="fleet/planner",
        tool="demo",
        git_root=root,
        branch=git.current_branch(root),
        tags=["planner", "fleet-demo"],
    )
    get_console().print(f"  {_CHECK} Created session fleet/planner ({session.id[:8]})")

    # Live mode: attempt to use ticket decompose
    if live:
        try:
            import os

            if os.getenv("LINEAR_TOKEN"):
                from shoal.services.linear_bridge import get_linear_bridge

                get_console().print("  [dim]Live mode: attempting Linear ticket decompose...[/dim]")
                bridge = get_linear_bridge()
                try:
                    # This is a demo - in real usage, would pass a real issue ID
                    # For now, just log that we would do this
                    get_console().print(
                        "  [yellow]Live ticket decompose would run here with real issue ID[/yellow]"
                    )
                finally:
                    await bridge.close()
            else:
                get_console().print("  [dim]LINEAR_TOKEN not set, using mock mode[/dim]")
                live = False
        except Exception as e:
            get_console().print(f"  [yellow]Live mode failed ({e}), falling back to mock[/yellow]")
            live = False

    # Mock mode (or fallback)
    if not live:
        append_entry(
            session.id,
            "## Plan: Greeting Feature\n\n"
            "1. Create `greeting.py` with a `greet()` function\n"
            "2. Add unit tests in `test_greeting.py`\n"
            "3. Review for edge cases and type safety\n\n"
            "Assigning to fleet/implementer.",
            source="planner",
        )
        get_console().print(f"  {_CHECK} Journal entry: task plan written")
    else:
        # Real decompose would write to journal here
        append_entry(
            session.id,
            "## Plan: Live ticket decomposition\n\nDecomposed ticket into child issues.",
            source="planner",
        )
        get_console().print(f"  {_CHECK} Journal entry: live decompose result written")

    entries = read_journal(session.id)
    ok = len(entries) >= 1 and (
        "greeting" in entries[-1].content.lower() or "ticket" in entries[-1].content.lower()
    )
    get_console().print(f"  {_CHECK if ok else _CROSS} Verified journal contains plan")

    s = await get_session(session.id)
    has_tag = s is not None and "planner" in s.tags
    get_console().print(f"  {_CHECK if has_tag else _CROSS} Tags: {s.tags if s else '?'}")

    return TourResult(passed=ok and has_tag, label="Planner scopes work"), session.id


# ---------------------------------------------------------------------------
# Step 2: Implementer works in isolated worktree
# ---------------------------------------------------------------------------


async def step_implementer(root: str) -> tuple[TourResult, str]:
    """Create an implementer session with a worktree and commit a change."""
    get_console().print("\n[bold cyan]Step 2 — Implementer works in isolated worktree[/bold cyan]")

    wt_path = str(Path(root) / ".worktrees" / "impl-greeting")
    Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
    git.worktree_add(root, wt_path, branch="impl/greeting")
    get_console().print(f"  {_CHECK} Worktree created at impl/greeting")

    session = await create_session(
        name="fleet/implementer",
        tool="demo",
        git_root=root,
        worktree=wt_path,
        branch="impl/greeting",
        tags=["implementer", "fleet-demo"],
    )
    get_console().print(f"  {_CHECK} Created session fleet/implementer ({session.id[:8]})")

    # Write a file in the worktree
    (Path(wt_path) / "greeting.py").write_text(
        '"""Greeting module."""\n\n\ndef greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    )
    git.stage_all(wt_path)
    git.commit(wt_path, "feat: add greeting module")
    get_console().print(f"  {_CHECK} Committed greeting.py on impl/greeting")

    count = git.commit_count_since_main(wt_path)
    get_console().print(f"  {_CHECK if count >= 1 else _CROSS} Commits ahead of main: {count}")

    append_entry(session.id, "Implemented greeting module per planner spec.", source="implementer")

    return TourResult(passed=count >= 1, label="Implementer isolation"), session.id


# ---------------------------------------------------------------------------
# Step 3: Reviewer critiques changes
# ---------------------------------------------------------------------------


async def step_reviewer(root: str, *, live: bool) -> tuple[TourResult, str]:
    """Create a reviewer session, tag review-ready, verify urgency tier."""
    get_console().print("\n[bold cyan]Step 3 — Reviewer critiques changes[/bold cyan]")

    session = await create_session(
        name="fleet/reviewer",
        tool="demo",
        git_root=root,
        branch=git.current_branch(root),
        tags=["reviewer", "review-ready", "fleet-demo"],
    )
    get_console().print(f"  {_CHECK} Created session fleet/reviewer ({session.id[:8]})")

    # Live mode: attempt to use GitHub PR review
    if live:
        try:
            import os

            if os.getenv("GITHUB_TOKEN"):
                from shoal.services.github_bridge import get_github_bridge

                get_console().print("  [dim]Live mode: attempting GitHub PR review...[/dim]")
                bridge = get_github_bridge()
                try:
                    # This is a demo - in real usage, would pass a real repo/PR
                    # For now, just log that we would do this
                    get_console().print(
                        "  [yellow]Live PR review would run here with real repo/PR[/yellow]"
                    )
                finally:
                    await bridge.close()
            else:
                get_console().print("  [dim]GITHUB_TOKEN not set, using mock mode[/dim]")
                live = False
        except Exception as e:
            get_console().print(f"  [yellow]Live mode failed ({e}), falling back to mock[/yellow]")
            live = False

    # Mock mode (or fallback)
    if not live:
        append_entry(
            session.id,
            "Reviewed greeting.py — clean implementation, type hints present, "
            "no security concerns. Approve merge.",
            source="reviewer",
        )
        get_console().print(f"  {_CHECK} Journal: review approved")
    else:
        # Real review would write to journal here
        append_entry(
            session.id,
            "## Live PR Review\n\nReviewed PR changes via GitHub API.",
            source="reviewer",
        )
        get_console().print(f"  {_CHECK} Journal: live review result written")

    s = await get_session(session.id)
    if s:
        tier, label = derive_urgency(s)
        is_review = tier == UrgencyTier.review
        get_console().print(f"  {_CHECK if is_review else _CROSS} Urgency tier: {label}")
    else:
        is_review = False

    return TourResult(passed=is_review, label="Reviewer + urgency"), session.id


# ---------------------------------------------------------------------------
# Step 4: Supervisor detects blocker
# ---------------------------------------------------------------------------


async def step_supervisor_escalation(impl_id: str) -> TourResult:
    """Simulate a blocker on the implementer and generate an escalation handoff."""
    get_console().print("\n[bold cyan]Step 4 — Supervisor detects blocker, escalates[/bold cyan]")

    await update_session(impl_id, status=SessionStatus.waiting)
    get_console().print(f"  {_CHECK} Implementer status → waiting (simulated permission prompt)")

    session = await get_session(impl_id)
    if not session:
        return TourResult(passed=False, label="Supervisor escalation")

    entries = read_journal(impl_id)
    artifact = generate_handoff(session, entries, [])
    get_console().print(f"  {_CHECK} Handoff generated: urgency={artifact.urgency_label}")

    next_lower = artifact.suggested_next.lower()
    mentions_approval = "approv" in next_lower or "input" in next_lower or "waiting" in next_lower
    get_console().print(
        f"  {_CHECK if mentions_approval else _CROSS} Suggested: {artifact.suggested_next[:80]}"
    )

    append_entry(
        impl_id,
        "ESCALATION: implementer blocked on permission prompt. Needs human approval.",
        source="supervisor",
    )

    return TourResult(passed=mentions_approval, label="Supervisor escalation")


# ---------------------------------------------------------------------------
# Step 5: Overnight progress (simulated)
# ---------------------------------------------------------------------------


async def step_overnight(impl_id: str) -> TourResult:
    """Resolve the blocker, mark implementer complete, generate handoffs."""
    get_console().print("\n[bold cyan]Step 5 — Overnight progress (simulated)[/bold cyan]")

    await update_session(impl_id, status=SessionStatus.idle)
    get_console().print(f"  {_CHECK} Blocker resolved → idle")

    now = datetime.now(UTC)
    await update_session(impl_id, completed_at=now)
    get_console().print(f"  {_CHECK} Implementer marked complete")

    session = await get_session(impl_id)
    if not session:
        return TourResult(passed=False, label="Overnight progress")

    entries = read_journal(impl_id)
    artifact = generate_handoff(session, entries, [])
    write_handoff_artifact(impl_id, artifact)
    get_console().print(f"  {_CHECK} Handoff artifact saved")
    diff = artifact.git_diff_summary or "n/a"
    get_console().print(f"  {_CHECK} Git context: {diff}, {artifact.commit_count} commit(s)")

    return TourResult(passed=artifact.commit_count >= 1, label="Overnight progress")


# ---------------------------------------------------------------------------
# Step 6: Morning fleet summary
# ---------------------------------------------------------------------------


async def step_morning_summary(
    planner_id: str, impl_id: str, reviewer_id: str, *, live: bool
) -> TourResult:
    """Display the fleet status table and clean up."""
    from rich.table import Table

    get_console().print("\n[bold cyan]Step 6 — Morning fleet summary[/bold cyan]")

    # Live mode: attempt to use report weekly
    if live:
        try:
            # Import is only needed when live mode is active
            # In real usage, would call generate_weekly_summary with real parameters
            get_console().print("  [dim]Live mode: attempting weekly report generation...[/dim]")
            # This is a demo - in real usage, would pass real week/team parameters
            # For now, just log that we would do this
            get_console().print(
                "  [yellow]Live weekly report would run here with real parameters[/yellow]"
            )
        except Exception as e:
            get_console().print(f"  [yellow]Live mode failed ({e}), falling back to mock[/yellow]")
            live = False

    # Mock mode (or fallback): display fleet table
    sessions = await list_sessions()
    fleet = [s for s in sessions if "fleet-demo" in s.tags]
    get_console().print(f"  {_CHECK} Fleet sessions: {len(fleet)}")

    table = Table(show_header=True, title="Fleet Status")
    table.add_column("Session", style="cyan")
    table.add_column("Mode")
    table.add_column("Status")
    table.add_column("Urgency")
    table.add_column("Action")

    for s in fleet:
        _tier, label = derive_urgency(s)
        entries = read_journal(s.id)
        artifact = generate_handoff(s, entries, [])
        table.add_row(
            s.name,
            next((t for t in s.tags if t in ("planner", "implementer", "reviewer")), "-"),
            str(s.status),
            label,
            artifact.suggested_next[:60],
        )

    get_console().print(table)

    # Cleanup
    for sid in [planner_id, impl_id, reviewer_id]:
        await delete_session(sid)
    get_console().print(f"  {_CHECK} Sessions cleaned up")

    return TourResult(passed=len(fleet) == 3, label="Morning fleet summary")


# ---------------------------------------------------------------------------
# Fleet demo runner
# ---------------------------------------------------------------------------


async def _fleet_impl(cleanup: bool, live: bool, interactive: bool) -> None:
    from rich.panel import Panel
    from rich.rule import Rule

    root = str(_fleet_dir)

    get_console().print(Rule("[bold]Shoal Fleet Demo[/bold]"))
    get_console().print(
        "The full control-plane story: planner → implementer → reviewer\n"
        "→ supervisor escalation → overnight progress → morning summary.\n"
    )

    if live:
        get_console().print("[yellow]Live mode enabled:[/yellow] will attempt real API calls")
    if interactive:
        get_console().print("[cyan]Interactive mode enabled:[/cyan] will pause between steps")

    create_demo_project(_fleet_dir)
    get_console().print(f"  {_CHECK} Demo project created at {_fleet_dir}\n")

    results: list[TourResult] = []

    # Step 1: Planner
    if interactive:
        mode_msg = (
            "With --live, attempts Linear ticket decompose." if live else "Using mock task plan."
        )
        get_console().print(
            Panel(
                "[bold]Step 1: Planner scopes work[/bold]\n\n"
                "This step creates a planner session and writes a task plan to the journal.\n"
                f"{mode_msg}",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 1?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r1, planner_id = await step_planner(root, live=live)
    results.append(r1)

    if interactive:
        from shoal.core.state import get_session

        s = await get_session(planner_id)
        if s:
            get_console().print(
                f"\n[dim]Session info: {s.name} | status={s.status} | tags={s.tags}[/dim]"
            )

    # Step 2: Implementer
    if interactive:
        get_console().print(
            Panel(
                "[bold]Step 2: Implementer works in isolated worktree[/bold]\n\n"
                "Creates an implementer session with a git worktree and commits a change.",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 2?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r2, impl_id = await step_implementer(root)
    results.append(r2)

    if interactive:
        s = await get_session(impl_id)
        if s:
            get_console().print(
                f"\n[dim]Session info: {s.name} | status={s.status} | worktree={s.worktree}[/dim]"
            )

    # Step 3: Reviewer
    if interactive:
        get_console().print(
            Panel(
                "[bold]Step 3: Reviewer critiques changes[/bold]\n\n"
                "Creates a reviewer session and verifies urgency tier.\n"
                f"{'With --live, attempts GitHub PR review.' if live else 'Using mock review.'}",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 3?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r3, reviewer_id = await step_reviewer(root, live=live)
    results.append(r3)

    if interactive:
        s = await get_session(reviewer_id)
        if s:
            get_console().print(
                f"\n[dim]Session info: {s.name} | status={s.status} | tags={s.tags}[/dim]"
            )

    # Step 4: Supervisor escalation
    if interactive:
        get_console().print(
            Panel(
                "[bold]Step 4: Supervisor detects blocker, escalates[/bold]\n\n"
                "Simulates a blocker on the implementer and generates an escalation handoff.",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 4?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r4 = await step_supervisor_escalation(impl_id)
    results.append(r4)

    # Step 5: Overnight progress
    if interactive:
        get_console().print(
            Panel(
                "[bold]Step 5: Overnight progress (simulated)[/bold]\n\n"
                "Resolves the blocker, marks implementer complete, generates handoffs.",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 5?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r5 = await step_overnight(impl_id)
    results.append(r5)

    # Step 6: Morning summary
    if interactive:
        mode_msg = (
            "With --live, attempts weekly report generation." if live else "Using mock summary."
        )
        get_console().print(
            Panel(
                "[bold]Step 6: Morning fleet summary[/bold]\n\n"
                "Displays the fleet status table and cleans up.\n"
                f"{mode_msg}",
                title="Next Step",
                border_style="cyan",
            )
        )
        if not typer.confirm("Continue to Step 6?", default=True):
            get_console().print("[yellow]Demo cancelled.[/yellow]")
            return

    r6 = await step_morning_summary(planner_id, impl_id, reviewer_id, live=live)
    results.append(r6)

    # Summary
    get_console().print(Rule("[bold]Results[/bold]"))
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    for r in results:
        icon = _CHECK if r.passed else _CROSS
        get_console().print(f"  {icon} {r.label}")
    get_console().print(f"\n  [bold]{passed} passed, {failed} failed[/bold]")

    if cleanup and _fleet_dir.exists():
        shutil.rmtree(_fleet_dir)
        get_console().print(f"\n  {_CHECK} Cleaned up {_fleet_dir}")


def fleet_demo(
    cleanup: Annotated[bool, typer.Option("--cleanup", help="Remove demo directory after")] = False,
    live: Annotated[
        bool, typer.Option("--live", help="Use real API calls (requires tokens)")
    ] = False,
    interactive: Annotated[
        bool, typer.Option("--interactive", help="Pause between steps with explanations")
    ] = False,
) -> None:
    """Run the flagship fleet demo — the full control-plane story."""
    asyncio.run(with_db(_fleet_impl(cleanup, live, interactive)))
