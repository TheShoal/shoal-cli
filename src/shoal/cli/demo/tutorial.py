"""Interactive tutorial — guided hands-on walkthrough of Shoal features.

Creates real sessions in /tmp/shoal-tutorial/ and walks the user through
each feature step by step with typer.confirm() between steps.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.rule import Rule

from shoal.cli.demo import console, create_demo_project, tutorial_dir
from shoal.core import git, tmux
from shoal.core.db import with_db
from shoal.core.state import create_session, delete_session, list_sessions
from shoal.core.theme import (
    Symbols,
    create_panel,
    create_table,
    get_status_icon,
    get_status_style,
)


@dataclass
class TutorialContext:
    """Mutable state carried across tutorial steps."""

    tutorial_path: Path
    session_ids: list[str] = field(default_factory=list)
    session_names: list[str] = field(default_factory=list)
    step: int = 0


MARKER_FILE = ".shoal-tutorial"
TOTAL_STEPS = 7


def demo_tutorial(
    cleanup: bool = typer.Option(False, "--cleanup", help="Clean up stale tutorial resources."),
    step: int = typer.Option(0, "--step", help="Resume from step N (1-indexed)."),
) -> None:
    """Interactive hands-on tutorial with guided steps."""
    asyncio.run(with_db(_demo_tutorial_impl(cleanup=cleanup, start_step=step)))


async def _demo_tutorial_impl(*, cleanup: bool = False, start_step: int = 0) -> None:
    tut_dir = tutorial_dir()

    if cleanup:
        await _cleanup(tut_dir)
        return

    # Check prerequisites
    if not shutil.which("tmux"):
        console.print("[red]Error: tmux is required for the tutorial.[/red]")
        console.print("[dim]Install tmux and try again.[/dim]")
        raise typer.Exit(1)

    # Check for stale tutorial
    marker = tut_dir / MARKER_FILE
    if marker.exists():
        console.print("[yellow]A previous tutorial session was found.[/yellow]")
        console.print("Run 'shoal demo tutorial --cleanup' to remove it first.")
        raise typer.Exit(1)

    console.print()
    console.print(Rule("[bold cyan]SHOAL INTERACTIVE TUTORIAL[/bold cyan]", style="cyan"))
    console.print("[dim]Hands-on walkthrough using real Shoal commands.[/dim]")
    console.print(f"[dim]Working directory: {tut_dir}[/dim]")
    console.print()

    ctx = TutorialContext(tutorial_path=tut_dir)

    try:
        # Create tutorial project
        create_demo_project(tut_dir)
        marker.write_text("")
        console.print(f"  [green]{Symbols.CHECK}[/green] Created tutorial project at {tut_dir}")
        console.print()

        steps = [
            _step_create_session,
            _step_check_status,
            _step_fork_session,
            _step_write_journal,
            _step_run_diagnostics,
            _step_explore_templates,
            _step_cleanup,
        ]

        for i, step_fn in enumerate(steps, 1):
            if start_step > 0 and i < start_step:
                continue
            ctx.step = i

            if i < len(steps):
                await step_fn(ctx)
                if not typer.confirm(f"\nContinue to step {i + 1}/{TOTAL_STEPS}?", default=True):
                    console.print("\n[dim]Tutorial paused. Resume with --step flag.[/dim]")
                    _write_marker(ctx)
                    return
                console.print()
            else:
                # Last step (cleanup) — no confirm needed
                await step_fn(ctx)

    except (KeyboardInterrupt, typer.Abort):
        console.print("\n[yellow]Tutorial interrupted.[/yellow]")
        console.print("[dim]Run 'shoal demo tutorial --cleanup' to remove resources.[/dim]")
        _write_marker(ctx)
        return


def _write_marker(ctx: TutorialContext) -> None:
    """Write marker file with session IDs for crash recovery."""
    marker = ctx.tutorial_path / MARKER_FILE
    lines = ctx.session_ids
    marker.write_text("\n".join(lines))


# ============================================================================
# Tutorial steps
# ============================================================================


async def _step_create_session(ctx: TutorialContext) -> None:
    """Step 1: Create a session."""
    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Create a Session[/bold]"))
    console.print("[dim]Sessions are the core unit — an AI agent in a tmux window.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print("  [cyan]shoal new tutorial-main[/cyan]")
    console.print()

    s = await create_session(
        name="tutorial-main",
        tool="claude",
        git_root=str(ctx.tutorial_path),
        branch=git.current_branch(str(ctx.tutorial_path)),
    )
    ctx.session_ids.append(s.id)
    ctx.session_names.append(s.name)

    console.print(f"  [green]{Symbols.CHECK}[/green] Created session: [bold]{s.name}[/bold]")
    console.print(f"     ID: {s.id}")
    console.print(f"     Tool: {s.tool}")
    console.print(f"     Branch: {s.branch}")


async def _step_check_status(ctx: TutorialContext) -> None:
    """Step 2: Check status."""
    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Check Status[/bold]"))
    console.print("[dim]Shoal monitors each session's tmux pane for status patterns.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print("  [cyan]shoal ls[/cyan]")
    console.print()

    sessions = await list_sessions()
    if sessions:
        table = create_table(padding=(0, 1))
        table.add_column("Name", width=20)
        table.add_column("Tool", width=10)
        table.add_column("Status", width=12)
        table.add_column("Branch")
        for s in sessions:
            style = get_status_style(s.status.value)
            icon = get_status_icon(s.status.value)
            status_text = f"[{style}]{icon} {s.status.value}[/{style}]"
            table.add_row(s.name, s.tool, status_text, s.branch or "main")
        console.print(table)
    console.print()
    console.print(f"  [green]{Symbols.CHECK}[/green] {len(sessions)} session(s) found")


async def _step_fork_session(ctx: TutorialContext) -> None:
    """Step 3: Fork a session with worktree."""
    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Fork a Session[/bold]"))
    console.print("[dim]Forking creates an isolated git worktree for parallel work.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print("  [cyan]shoal fork tutorial-main --name tutorial-fork[/cyan]")
    console.print()

    wt_path = ctx.tutorial_path / ".worktrees" / "tutorial-fork"
    (ctx.tutorial_path / ".worktrees").mkdir(parents=True, exist_ok=True)
    git.worktree_add(str(ctx.tutorial_path), str(wt_path), branch="tutorial-fork")

    s = await create_session(
        name="tutorial-fork",
        tool="claude",
        git_root=str(ctx.tutorial_path),
        worktree=str(wt_path),
        branch="tutorial-fork",
    )
    ctx.session_ids.append(s.id)
    ctx.session_names.append(s.name)

    console.print(f"  [green]{Symbols.CHECK}[/green] Forked: [bold]{s.name}[/bold]")
    console.print(f"     Worktree: {wt_path}")
    console.print(f"     Branch: {s.branch}")
    console.print("     [dim]Files here are isolated from the main session.[/dim]")


async def _step_write_journal(ctx: TutorialContext) -> None:
    """Step 4: Write a journal entry."""
    from shoal.core.journal import (
        JournalMetadata,
        append_entry,
        read_journal,
    )

    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Write a Journal[/bold]"))
    console.print("[dim]Journals are append-only markdown logs per session.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print('  [cyan]shoal journal tutorial-main --append "Session notes here"[/cyan]')
    console.print()

    sid = ctx.session_ids[0]
    meta = JournalMetadata(
        session_id=sid,
        session_name="tutorial-main",
        tool="claude",
    )
    append_entry(
        sid,
        "Tutorial journal entry: learning how Shoal journals work!",
        source="tutorial",
        metadata=meta,
    )
    console.print(f"  [green]{Symbols.CHECK}[/green] Wrote journal entry for tutorial-main")

    entries = read_journal(sid)
    if entries:
        e = entries[-1]
        console.print(f"     Timestamp: {e.timestamp.isoformat()}")
        console.print(f"     Source: {e.source}")
        console.print(f'     Content: "{e.content[:60]}"')


async def _step_run_diagnostics(ctx: TutorialContext) -> None:
    """Step 5: Run diagnostics."""
    from shoal.core.config import config_dir, state_dir

    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Run Diagnostics[/bold]"))
    console.print("[dim]Health checks for all Shoal components.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print("  [cyan]shoal diag[/cyan]")
    console.print()

    checks: list[tuple[str, bool, str]] = []

    db_path = state_dir() / "shoal.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        checks.append(("database", True, f"{size_kb:.1f} KB"))
    else:
        checks.append(("database", False, "not found"))

    tmux_found = shutil.which("tmux") is not None
    checks.append(("tmux", tmux_found, "installed" if tmux_found else "not found"))

    cfg_dir = config_dir()
    checks.append(("config dir", cfg_dir.exists(), str(cfg_dir)))

    for name, healthy, detail in checks:
        mark = Symbols.CHECK if healthy else Symbols.CROSS
        color = "green" if healthy else "red"
        console.print(f"  [{color}]{mark}[/{color}] {name:16} {detail}")


async def _step_explore_templates(ctx: TutorialContext) -> None:
    """Step 6: Explore templates."""
    from shoal.core.config import templates_dir

    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Explore Templates[/bold]"))
    console.print("[dim]Templates define reusable session layouts with inheritance.[/dim]")
    console.print()
    console.print("[bold yellow]Equivalent CLI:[/bold yellow]")
    console.print("  [cyan]shoal template ls[/cyan]")
    console.print()

    tpl_dir = templates_dir()
    if tpl_dir.exists():
        toml_files = sorted(tpl_dir.glob("*.toml"))
        if toml_files:
            for tf in toml_files:
                try:
                    from shoal.core.config import resolve_template

                    t = resolve_template(tf.stem)
                    extends = f" extends {t.extends}" if t.extends else ""
                    console.print(
                        f"  [green]{Symbols.CHECK}[/green] {t.name:20} "
                        f"tool={t.tool or 'default'}{extends}"
                    )
                except Exception as e:
                    console.print(f"  [red]{Symbols.CROSS}[/red] {tf.stem}: {e}")
        else:
            console.print("  [dim]No templates found. Run 'shoal init' to scaffold defaults.[/dim]")
    else:
        console.print("  [dim]Templates dir doesn't exist. Run 'shoal init' first.[/dim]")


async def _step_cleanup(ctx: TutorialContext) -> None:
    """Step 7: Clean up."""
    console.print(Rule(f"[bold]Step {ctx.step}/{TOTAL_STEPS}: Clean Up[/bold]"))
    console.print()

    await _cleanup(ctx.tutorial_path)

    console.print()
    console.print(
        create_panel(
            """[bold green]Tutorial complete![/bold green]

[bold]What you learned:[/bold]
  1. Creating sessions with [yellow]shoal new[/yellow]
  2. Checking status with [yellow]shoal ls[/yellow]
  3. Forking with worktrees for isolation
  4. Writing session journals
  5. Running diagnostics
  6. Exploring templates

[bold]Next steps:[/bold]
  [yellow]shoal new my-session[/yellow]     Create your first real session
  [yellow]shoal demo start[/yellow]          Launch the full demo environment
  [yellow]shoal demo tour[/yellow]           Feature showcase (no setup needed)
""",
            title="[bold cyan]Tutorial Complete[/bold cyan]",
            title_align="left",
            primary=True,
        )
    )


# ============================================================================
# Cleanup
# ============================================================================


async def _cleanup(tut_dir: Path) -> None:
    """Remove all tutorial resources. Idempotent."""
    marker = tut_dir / MARKER_FILE
    cleaned = 0

    # Kill tutorial sessions from DB
    sessions = await list_sessions()
    for s in sessions:
        if s.name.startswith("tutorial-"):
            if tmux.has_session(s.tmux_session):
                tmux.kill_session(s.tmux_session)
            await delete_session(s.id)
            console.print(f"  [green]{Symbols.CHECK}[/green] Removed session: {s.name}")
            cleaned += 1

    # Also try marker file session IDs (crash recovery)
    if marker.exists():
        from shoal.core.state import get_session

        for sid in marker.read_text().strip().split("\n"):
            if not sid:
                continue
            stale = await get_session(sid)
            if stale:
                if tmux.has_session(stale.tmux_session):
                    tmux.kill_session(stale.tmux_session)
                await delete_session(stale.id)
                console.print(f"  [green]{Symbols.CHECK}[/green] Removed session: {stale.name}")
                cleaned += 1

    # Clean up journal files for tutorial sessions
    from shoal.core.journal import delete_journal

    for sid_line in marker.read_text().strip().split("\n") if marker.exists() else []:
        if sid_line:
            delete_journal(sid_line)

    # Remove tutorial directory
    if tut_dir.exists():
        shutil.rmtree(tut_dir)
        console.print(f"  [green]{Symbols.CHECK}[/green] Removed tutorial directory")
        cleaned += 1

    if cleaned:
        console.print(f"\n[bold green]Cleaned up {cleaned} resource(s).[/bold green]")
    else:
        console.print("[dim]Nothing to clean up.[/dim]")
