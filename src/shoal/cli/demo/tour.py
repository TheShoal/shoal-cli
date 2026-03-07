"""Demo tour — user-facing feature showcase.

7 steps demonstrating Shoal features from the user's perspective.
Each step is an independent async function returning a TourResult.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from rich.rule import Rule

from shoal.cli.demo import console
from shoal.core.config import config_dir, data_dir, templates_dir
from shoal.core.db import with_db
from shoal.core.state import list_sessions
from shoal.core.theme import (
    STATUS_STYLES,
    Symbols,
    create_table,
    get_status_icon,
    get_status_style,
)
from shoal.models.state import SessionStatus


@dataclass
class TourResult:
    """Result of a single tour step."""

    passed: bool
    label: str
    skipped: bool = False


# ============================================================================
# Step functions — each returns a TourResult
# ============================================================================


async def step_session_lifecycle() -> TourResult:
    """Step 1: Session Lifecycle — list real sessions, explain what they are."""
    console.print("[bold]1. Session Lifecycle[/bold]")
    console.print("[dim]   Sessions are AI agents running in tmux with git context.[/dim]")
    console.print("[dim]   Create: shoal new <name> [--tool claude] [--worktree branch][/dim]")
    console.print()

    sessions = await list_sessions()
    if sessions:
        table = create_table(padding=(0, 1))
        table.add_column("Name", width=16)
        table.add_column("Tool", width=10)
        table.add_column("Status", width=12)
        table.add_column("Branch", width=22)
        table.add_column("Worktree")
        for s in sessions:
            style = get_status_style(s.status.value)
            icon = get_status_icon(s.status.value)
            status_text = f"[{style}]{icon} {s.status.value}[/{style}]"
            wt = Path(s.worktree).name if s.worktree else "(root)"
            table.add_row(s.name, s.tool, status_text, s.branch or "main", wt)
        console.print(table)
        console.print()

        counts: dict[str, int] = {}
        for s in sessions:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        parts = []
        for status_val, count in sorted(counts.items()):
            icon = get_status_icon(status_val)
            parts.append(f"{icon} {count} {status_val}")
        console.print(f"   Total: {len(sessions)} sessions \u2014 {', '.join(parts)}")
    else:
        console.print(
            "   [dim]No sessions found (run 'shoal demo start' for full experience)[/dim]"
        )

    console.print(f"   [green]{Symbols.CHECK} Session state queries work[/green]")
    console.print()
    return TourResult(passed=True, label="Session Lifecycle")


async def step_status_detection() -> TourResult:
    """Step 2: Status Detection — show 4 detection examples, Claude-focused."""
    from shoal.core.detection import detect_status
    from shoal.models.config import DetectionPatterns, ToolConfig

    console.print("[bold]2. Status Detection[/bold]")
    console.print("[dim]   Shoal monitors tmux pane output for tool-specific patterns.[/dim]")
    console.print("[dim]   Each tool has configurable busy/waiting/error/idle regexes.[/dim]")
    console.print()

    claude_tool = ToolConfig(
        name="claude",
        command="claude",
        icon="\U0001f916",
        detection=DetectionPatterns(
            busy_patterns=["\u280b", "thinking"],
            waiting_patterns=["Yes/No", "Allow"],
            error_patterns=["Error:", "ERROR"],
        ),
    )

    test_cases: list[tuple[str, SessionStatus]] = [
        ("thinking about the code...", SessionStatus.running),
        ("Do you Allow this? Yes/No", SessionStatus.waiting),
        ("Error: file not found", SessionStatus.error),
        ("$ ls\nfile.py", SessionStatus.idle),
    ]

    detection_ok = True
    for content, expected in test_cases:
        result = detect_status(content, claude_tool)
        ok = result == expected
        icon = get_status_icon(result.value)
        style = get_status_style(result.value)
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        short = content[:42].replace("\n", "\\n")
        console.print(
            f"   [{color}]{mark}[/{color}] [{style}]{icon} {result.value:8}[/{style}] "
            f'\u2190 "{short}"'
        )
        if not ok:
            detection_ok = False

    if detection_ok:
        console.print(f"   [green]{Symbols.CHECK} All detection tests passed[/green]")
    else:
        console.print(f"   [red]{Symbols.CROSS} Some detection tests failed[/red]")
    console.print()
    return TourResult(passed=detection_ok, label="Status Detection")


async def step_templates_and_inheritance() -> TourResult:
    """Step 3: Templates & Inheritance — load real templates from config dir."""
    from shoal.core.config import _apply_mixin, _merge_templates
    from shoal.models.config import (
        SessionTemplateConfig,
        TemplateMixinConfig,
        TemplatePaneConfig,
        TemplateWindowConfig,
    )

    console.print("[bold]3. Templates & Inheritance[/bold]")
    console.print("[dim]   Declarative session layouts with extends + mixins composition.[/dim]")
    console.print()

    tpl_dir = templates_dir()
    ok = True

    # Show real templates if they exist
    if tpl_dir.exists():
        toml_files = sorted(tpl_dir.glob("*.toml"))
        if toml_files:
            for tf in toml_files:
                try:
                    from shoal.core.config import resolve_template

                    t = resolve_template(tf.stem)
                    extends = f" (extends {t.extends})" if t.extends else ""
                    mixins = f" +{','.join(t.mixins)}" if t.mixins else ""
                    console.print(
                        f"   [green]{Symbols.CHECK}[/green] {t.name:20} "
                        f"tool={t.tool or 'default'}{extends}{mixins}"
                    )
                except Exception as e:
                    console.print(f"   [red]{Symbols.CROSS}[/red] {tf.stem}: {e}")
                    ok = False
        else:
            console.print("   [dim]No templates in config dir (shoal init to scaffold)[/dim]")

    # In-memory inheritance test
    _win = [
        TemplateWindowConfig(
            name="main",
            panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
        )
    ]
    parent = SessionTemplateConfig(
        name="base",
        description="Base layout",
        tool="opencode",
        env={"EDITOR": "nvim"},
        mcp=["memory"],
        windows=_win,
    )
    child = SessionTemplateConfig(
        name="child",
        extends="base",
        tool="claude",
        env={"MODEL": "opus"},
        mcp=["github"],
        windows=[],
    )
    child_raw = {"template": {"tool": "claude"}}

    merged = _merge_templates(parent, child, child_raw)
    inherit_checks = [
        (merged.tool == "claude", "child tool overrides parent"),
        (merged.description == "Base layout", "parent description inherited"),
        ("EDITOR" in merged.env and "MODEL" in merged.env, "env dicts merged"),
        (merged.mcp == ["github", "memory"], "mcp lists unioned and sorted"),
        (len(merged.windows) == 1, "parent windows inherited when child has none"),
    ]
    for check_ok, label in inherit_checks:
        mark = Symbols.CHECK if check_ok else Symbols.CROSS
        color = "green" if check_ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not check_ok:
            ok = False

    # Mixin test
    mixin = TemplateMixinConfig(
        name="with-tests",
        env={"TEST_RUNNER": "pytest"},
        mcp=["filesystem"],
        windows=[
            TemplateWindowConfig(
                name="tests",
                panes=[TemplatePaneConfig(split="root", command="pytest --watch")],
            )
        ],
    )
    mixed = _apply_mixin(merged, mixin)
    if len(mixed.windows) == 2 and mixed.windows[-1].name == "tests":
        console.print(f"   [green]{Symbols.CHECK}[/green] mixin window appended correctly")
    else:
        console.print(f"   [red]{Symbols.CROSS}[/red] mixin application failed")
        ok = False

    if ok:
        console.print(f"   [green]{Symbols.CHECK} Template system works[/green]")
    else:
        console.print(f"   [red]{Symbols.CROSS} Template issues[/red]")
    console.print()
    return TourResult(passed=ok, label="Templates & Inheritance")


async def step_journals() -> TourResult:
    """Step 4: Journals — create temp session, append entry, read back, clean up."""
    from shoal.core.journal import (
        JournalMetadata,
        append_entry,
        delete_journal,
        read_journal,
    )
    from shoal.core.state import create_session, delete_session

    console.print("[bold]4. Journals[/bold]")
    console.print("[dim]   Append-only markdown journals for session notes and handoffs.[/dim]")
    console.print("[dim]   Obsidian-compatible YAML frontmatter on creation.[/dim]")
    console.print()

    ok = True
    session = await create_session("tour-journal-test", "claude", "/tmp/tour-test")

    try:
        meta = JournalMetadata(
            session_id=session.id,
            session_name=session.name,
            tool=session.tool,
        )
        append_entry(
            session.id,
            "Tour test entry: verifying journal write + read cycle.",
            source="tour",
            metadata=meta,
        )
        console.print(f"   [green]{Symbols.CHECK}[/green] Journal entry written with frontmatter")

        entries = read_journal(session.id)
        if entries and "Tour test entry" in entries[-1].content:
            console.print(
                f"   [green]{Symbols.CHECK}[/green] "
                f"Read back {len(entries)} entry — source={entries[-1].source}"
            )
        else:
            console.print(f"   [red]{Symbols.CROSS}[/red] Failed to read journal entry")
            ok = False

        # Verify frontmatter
        from shoal.core.journal import read_frontmatter

        fm = read_frontmatter(session.id)
        if fm and fm.get("session_id") == session.id:
            console.print(f"   [green]{Symbols.CHECK}[/green] Frontmatter has session_id")
        else:
            console.print(f"   [red]{Symbols.CROSS}[/red] Frontmatter missing or incorrect")
            ok = False

        # Clean up
        delete_journal(session.id)
        await delete_session(session.id)
        console.print(f"   [green]{Symbols.CHECK}[/green] Cleaned up temp session and journal")
    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS}[/red] Journal test failed: {e}")
        ok = False
        # Best-effort cleanup
        delete_journal(session.id)
        await delete_session(session.id)

    if ok:
        console.print(f"   [green]{Symbols.CHECK} Journal system works[/green]")
    else:
        console.print(f"   [red]{Symbols.CROSS} Journal issues[/red]")
    console.print()
    return TourResult(passed=ok, label="Journals")


async def step_diagnostics() -> TourResult:
    """Step 5: Diagnostics — run DB/tmux/MCP checks inline."""
    console.print("[bold]5. Diagnostics[/bold]")
    console.print("[dim]   Component health checks (same as 'shoal diag').[/dim]")
    console.print()

    ok = True
    checks: list[tuple[str, bool, str]] = []

    # DB check
    db_path = data_dir() / "shoal.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        checks.append(("database", True, f"{size_kb:.1f} KB"))
    else:
        checks.append(("database", False, "not found"))

    # tmux check
    tmux_found = shutil.which("tmux") is not None
    checks.append(("tmux", tmux_found, "installed" if tmux_found else "not found"))

    # MCP socket check
    socket_dir = data_dir() / "mcp-pool" / "sockets"
    if socket_dir.exists():
        sockets = list(socket_dir.glob("*.sock"))
        checks.append(("mcp sockets", True, f"{len(sockets)} active"))
    else:
        checks.append(("mcp sockets", True, "0 sockets"))

    # Config dir check
    cfg_dir = config_dir()
    checks.append(("config dir", cfg_dir.exists(), str(cfg_dir)))

    for name, healthy, detail in checks:
        mark = Symbols.CHECK if healthy else Symbols.CROSS
        color = "green" if healthy else "red"
        console.print(f"   [{color}]{mark}[/{color}] {name:16} {detail}")
        if not healthy:
            ok = False

    if ok:
        console.print(f"   [green]{Symbols.CHECK} All components healthy[/green]")
    else:
        console.print(f"   [yellow]{Symbols.BULLET_WAITING} Some components unavailable[/yellow]")
    console.print()
    return TourResult(passed=True, label="Diagnostics")


async def step_mcp_orchestration() -> TourResult:
    """Step 6: MCP Orchestration — list FastMCP tools or skip if not installed."""
    console.print("[bold]6. MCP Orchestration[/bold]")
    console.print("[dim]   Shoal exposes itself as MCP tools for agent-to-agent control.[/dim]")
    console.print()

    try:
        from shoal.services.mcp_shoal_server import mcp as shoal_mcp

        tools = await shoal_mcp.list_tools()
        tool_names = sorted(t.name for t in tools)
        expected_tools = [
            "append_journal",
            "capture_pane",
            "create_session",
            "kill_session",
            "list_sessions",
            "read_history",
            "read_journal",
            "send_keys",
            "session_info",
            "session_status",
        ]
        ok = tool_names == expected_tools
        if ok:
            console.print(f"   [green]{Symbols.CHECK}[/green] {len(tools)} MCP tools registered")
        else:
            console.print(
                f"   [red]{Symbols.CROSS}[/red] Expected {expected_tools}, got {tool_names}"
            )

        for tool_obj in sorted(tools, key=lambda t: t.name):
            annotations = tool_obj.annotations
            read_only = getattr(annotations, "readOnlyHint", False) if annotations else False
            destructive = getattr(annotations, "destructiveHint", False) if annotations else False
            if read_only:
                badge = "[dim cyan]read-only[/dim cyan]"
            elif destructive:
                badge = "[dim red]destructive[/dim red]"
            else:
                badge = "[dim]mutating[/dim]"
            console.print(f"   [green]{Symbols.CHECK}[/green] {tool_obj.name:20} {badge}")

        if ok:
            console.print(f"   [green]{Symbols.CHECK} MCP orchestration works[/green]")
        else:
            console.print(f"   [red]{Symbols.CROSS} MCP orchestration issues[/red]")
        console.print()
        return TourResult(passed=ok, label="MCP Orchestration")

    except ImportError:
        console.print(
            f"   [yellow]{Symbols.BULLET_FILLED}[/yellow] "
            "fastmcp not installed (pip install shoal[mcp])"
        )
        console.print(
            f"   [yellow]{Symbols.BULLET_WAITING} MCP orchestration skipped "
            "(optional dependency)[/yellow]"
        )
        console.print()
        return TourResult(passed=True, label="MCP Orchestration", skipped=True)

    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS}[/red] MCP introspection failed: {e}")
        console.print()
        return TourResult(passed=False, label="MCP Orchestration")


async def step_theme_and_status() -> TourResult:
    """Step 7: Theme & Status — show 5 status styles with icons."""
    console.print("[bold]7. Theme & Status[/bold]")
    console.print("[dim]   Centralized icons, colors, and Nerd Font glyphs for the CLI.[/dim]")
    console.print()

    for status_name, status_style in STATUS_STYLES.items():
        console.print(
            f"   [{status_style.rich}]{status_style.icon} {status_name:10}[/{status_style.rich}] "
            f"nerd: {status_style.nerd}"
        )

    console.print(f"   [green]{Symbols.CHECK} Theme system works[/green]")
    console.print()
    return TourResult(passed=True, label="Theme & Status")


# ============================================================================
# Tour runner
# ============================================================================

TOUR_STEPS = [
    step_session_lifecycle,
    step_status_detection,
    step_templates_and_inheritance,
    step_journals,
    step_diagnostics,
    step_mcp_orchestration,
    step_theme_and_status,
]


def demo_tour() -> None:
    """Guided tour demonstrating Shoal features with live examples."""
    asyncio.run(with_db(_demo_tour_impl()))


async def _demo_tour_impl() -> None:
    console.print()
    console.print(Rule("[bold cyan]SHOAL FEATURE TOUR[/bold cyan]", style="cyan"))
    console.print("[dim]Showcasing what Shoal can do \u2014 7 feature areas.[/dim]")
    console.print()

    results: list[TourResult] = []
    for step_fn in TOUR_STEPS:
        result = await step_fn()
        results.append(result)

    passed = sum(1 for r in results if r.passed and not r.skipped)
    failed = sum(1 for r in results if not r.passed)
    skipped = sum(1 for r in results if r.skipped)
    total = passed + failed + skipped

    console.print(Rule(style="cyan"))
    if failed == 0 and skipped == 0:
        console.print(f"[bold green]{Symbols.CHECK} All {total} feature areas passed![/bold green]")
    elif failed == 0 and skipped > 0:
        console.print(
            f"[bold green]{Symbols.CHECK} {passed} feature areas passed, "
            f"{skipped} skipped[/bold green]"
        )
    else:
        console.print(
            f"[bold yellow]{passed}/{total} feature areas passed, {failed} failed[/bold yellow]"
        )
    console.print()
