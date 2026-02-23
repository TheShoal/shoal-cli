"""Demo tour — guided walkthrough proving features work."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.rule import Rule

from shoal.cli.demo import console
from shoal.core.db import with_db
from shoal.core.state import list_sessions
from shoal.core.theme import (
    Symbols,
    create_table,
    get_status_icon,
    get_status_style,
)


def demo_tour() -> None:
    """Guided tour demonstrating Shoal features with live examples."""
    asyncio.run(with_db(_demo_tour_impl()))


async def _demo_tour_impl() -> None:
    from pydantic import ValidationError

    from shoal.core.config import _apply_mixin, _merge_templates
    from shoal.core.detection import detect_status
    from shoal.core.state import validate_session_name
    from shoal.core.theme import STATUS_STYLES
    from shoal.models.config import (
        DetectionPatterns,
        SessionTemplateConfig,
        TemplateMixinConfig,
        TemplatePaneConfig,
        TemplateWindowConfig,
        ToolConfig,
    )
    from shoal.services.mcp_pool import validate_mcp_name

    console.print()
    console.print(Rule("[bold cyan]SHOAL FEATURE TOUR[/bold cyan]", style="cyan"))
    console.print("[dim]Live tests proving each feature area works correctly.[/dim]")
    console.print()

    passed = 0
    failed = 0
    skipped = 0

    # ── 1. Session State ──────────────────────────────────────────────────
    console.print("[bold]1. Session Management[/bold]")
    console.print("[dim]   Sessions track AI agents in tmux with git context.[/dim]")
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

        # Status breakdown
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
    passed += 1
    console.print()

    # ── 2. Status Detection Engine ─────────────────────────────────────────
    console.print("[bold]2. Status Detection Engine[/bold]")
    console.print("[dim]   Pane content matched against tool-specific patterns.[/dim]")
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
    pi_tool = ToolConfig(
        name="pi",
        command="pi",
        icon="\U0001f967",
        detection=DetectionPatterns(
            busy_patterns=["thinking", "generating", "executing"],
            waiting_patterns=["permission", "approve", "y/n"],
            error_patterns=["Error:", "FAILED"],
        ),
    )

    test_cases = [
        ("thinking about the code...", claude_tool, SessionStatus.running),
        ("Do you Allow this? Yes/No", claude_tool, SessionStatus.waiting),
        ("Error: file not found", claude_tool, SessionStatus.error),
        ("$ ls\nfile.py", claude_tool, SessionStatus.idle),
        ("generating response...", pi_tool, SessionStatus.running),
        ("Please approve the edit", pi_tool, SessionStatus.waiting),
        ("Build FAILED with 3 errors", pi_tool, SessionStatus.error),
    ]

    detection_ok = True
    for content, tool, expected in test_cases:
        result = detect_status(content, tool)
        ok = result == expected
        icon = get_status_icon(result.value)
        style = get_status_style(result.value)
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        short = content[:42].replace("\n", "\\n")
        console.print(
            f"   [{color}]{mark}[/{color}] [{style}]{icon} {result.value:8}[/{style}] "
            f'\u2190 {tool.name}: "{short}"'
        )
        if not ok:
            detection_ok = False

    if detection_ok:
        console.print(f"   [green]{Symbols.CHECK} All detection tests passed[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Some detection tests failed[/red]")
        failed += 1
    console.print()

    # ── 3. Template Validation ─────────────────────────────────────────────
    console.print("[bold]3. Template Validation[/bold]")
    console.print("[dim]   Schema-validated session layouts with pane configuration.[/dim]")
    console.print()

    template_ok = True

    # Valid template
    try:
        t = SessionTemplateConfig(
            name="pi-dev",
            description="Pi agent with terminal pane",
            tool="pi",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[
                        TemplatePaneConfig(split="root", size="65%", command="{tool_command}"),
                        TemplatePaneConfig(split="right", size="35%", command="echo terminal"),
                    ],
                ),
            ],
        )
        console.print(
            f"   [green]{Symbols.CHECK}[/green] Valid: {t.name} "
            f"({len(t.windows)} window, "
            f"{sum(len(w.panes) for w in t.windows)} panes)"
        )
    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS} Valid template rejected: {e}[/red]")
        template_ok = False

    # Invalid: bad name
    try:
        SessionTemplateConfig(
            name="bad name!",
            windows=[
                TemplateWindowConfig(
                    name="w", panes=[TemplatePaneConfig(split="root", command="echo")]
                )
            ],
        )
        console.print(f"   [red]{Symbols.CROSS} Should have rejected invalid name[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f'   [green]{Symbols.CHECK}[/green] Rejected invalid name: "bad name!"')

    # Invalid: no windows
    try:
        SessionTemplateConfig(name="empty", windows=[])
        console.print(f"   [red]{Symbols.CROSS} Should have rejected empty windows[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f"   [green]{Symbols.CHECK}[/green] Rejected template with no windows")

    # Invalid: bad pane size
    try:
        TemplatePaneConfig(split="root", size="150%", command="echo")
        console.print(f"   [red]{Symbols.CROSS} Should have rejected invalid size[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f'   [green]{Symbols.CHECK}[/green] Rejected invalid pane size: "150%"')

    # Invalid: first pane not root
    try:
        TemplateWindowConfig(name="bad", panes=[TemplatePaneConfig(split="right", command="echo")])
        console.print(f"   [red]{Symbols.CROSS} Should have rejected non-root first pane[/red]")
        template_ok = False
    except (ValidationError, ValueError):
        console.print(f"   [green]{Symbols.CHECK}[/green] Rejected non-root first pane")

    if template_ok:
        console.print(f"   [green]{Symbols.CHECK} Template validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Template validation issues[/red]")
        failed += 1
    console.print()

    # ── 4. MCP Name Validation ─────────────────────────────────────────────
    console.print("[bold]4. MCP Server Name Validation[/bold]")
    console.print("[dim]   Names validated for file paths and environment variables.[/dim]")
    console.print()

    mcp_ok = True
    valid_mcp = ["memory", "filesystem", "my-server", "test_123"]
    invalid_mcp = [
        ("bad/name", "bad/name"),
        ("$(whoami)", "$(whoami)"),
        ("", "(empty)"),
        ("-leading", "-leading"),
        ("a" * 65, "a" * 20 + "..."),
    ]

    for name in valid_mcp:
        try:
            validate_mcp_name(name)
            console.print(f'   [green]{Symbols.CHECK}[/green] Accepted: "{name}"')
        except ValueError:
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have accepted: "{name}"')
            mcp_ok = False

    for name, display in invalid_mcp:
        try:
            validate_mcp_name(name)
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have rejected: "{display}"')
            mcp_ok = False
        except ValueError:
            console.print(f'   [green]{Symbols.CHECK}[/green] Rejected: "{display}"')

    if mcp_ok:
        console.print(f"   [green]{Symbols.CHECK} MCP name validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} MCP validation issues[/red]")
        failed += 1
    console.print()

    # ── 5. Session Name Validation ─────────────────────────────────────────
    console.print("[bold]5. Session Name Validation[/bold]")
    console.print("[dim]   Names validated for tmux compatibility and security.[/dim]")
    console.print()

    name_ok = True
    valid_names = ["my-session", "project/feature", "test.v2", "a_b-c"]
    invalid_names = [
        ("", "(empty)"),
        ("a" * 101, "a" * 20 + "..."),
        ("$(whoami)", "$(whoami)"),
        ("..", ".."),
        ("bad name", "bad name"),
    ]

    for name in valid_names:
        try:
            validate_session_name(name)
            console.print(f'   [green]{Symbols.CHECK}[/green] Accepted: "{name}"')
        except ValueError:
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have accepted: "{name}"')
            name_ok = False

    for name, display in invalid_names:
        try:
            validate_session_name(name)
            console.print(f'   [red]{Symbols.CROSS}[/red] Should have rejected: "{display}"')
            name_ok = False
        except ValueError:
            console.print(f'   [green]{Symbols.CHECK}[/green] Rejected: "{display}"')

    if name_ok:
        console.print(f"   [green]{Symbols.CHECK} Session name validation works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Name validation issues[/red]")
        failed += 1
    console.print()

    # ── 6. Template Inheritance ────────────────────────────────────────────
    console.print("[bold]6. Template Inheritance[/bold]")
    console.print("[dim]   Single inheritance (extends) + additive mixins for DRY templates.[/dim]")
    console.print()

    inherit_ok = True

    # Build a parent and child template in-memory
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
        env={"EDITOR": "nvim", "LANG": "en_US.UTF-8"},
        mcp=["memory"],
        windows=_win,
    )
    child = SessionTemplateConfig(
        name="child",
        extends="base",
        tool="claude",
        env={"CLAUDE_MODEL": "opus"},
        mcp=["github"],
        windows=[],
    )
    # Simulate child_raw TOML presence (tool explicitly set, no windows)
    child_raw = {"template": {"tool": "claude"}}

    merged = _merge_templates(parent, child, child_raw)
    checks = [
        (merged.tool == "claude", "child tool wins", f"tool={merged.tool}"),
        (merged.description == "Base layout", "parent description inherited", ""),
        (
            merged.env == {"EDITOR": "nvim", "LANG": "en_US.UTF-8", "CLAUDE_MODEL": "opus"},
            "env dicts merged (child wins conflicts)",
            "",
        ),
        (
            merged.mcp == ["github", "memory"],
            "mcp lists unioned and sorted",
            f"mcp={merged.mcp}",
        ),
        (len(merged.windows) == 1, "parent windows inherited (child had none)", ""),
    ]
    for ok, label, detail in checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        extra = f" ({detail})" if detail and not ok else ""
        console.print(f"   [{color}]{mark}[/{color}] {label}{extra}")
        if not ok:
            inherit_ok = False

    # Test mixin application
    mixin = TemplateMixinConfig(
        name="with-tests",
        env={"TEST_RUNNER": "pytest"},
        mcp=["memory", "filesystem"],
        windows=[
            TemplateWindowConfig(
                name="tests",
                panes=[TemplatePaneConfig(split="root", command="pytest --watch")],
            )
        ],
    )
    mixed = _apply_mixin(merged, mixin)
    mixin_checks = [
        ("TEST_RUNNER" in mixed.env, "mixin env merged in"),
        (sorted(mixed.mcp) == ["filesystem", "github", "memory"], "mixin mcp unioned"),
        (len(mixed.windows) == 2, "mixin window appended"),
        (mixed.windows[-1].name == "tests", "appended window is from mixin"),
    ]
    for ok, label in mixin_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            inherit_ok = False

    if inherit_ok:
        console.print(f"   [green]{Symbols.CHECK} Template inheritance works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Template inheritance issues[/red]")
        failed += 1
    console.print()

    # ── 7. Lifecycle Error Handling ────────────────────────────────────────
    console.print("[bold]7. Lifecycle Error Handling[/bold]")
    console.print("[dim]   Structured exceptions with session context for rollback safety.[/dim]")
    console.print()

    from shoal.services.lifecycle import (
        DirtyWorktreeError,
        LifecycleError,
        SessionExistsError,
        StartupCommandError,
        TmuxSetupError,
    )

    lifecycle_ok = True

    # Verify exception hierarchy
    hierarchy_checks = [
        (issubclass(TmuxSetupError, LifecycleError), "TmuxSetupError extends LifecycleError"),
        (
            issubclass(StartupCommandError, LifecycleError),
            "StartupCommandError extends LifecycleError",
        ),
        (
            issubclass(SessionExistsError, LifecycleError),
            "SessionExistsError extends LifecycleError",
        ),
        (
            issubclass(DirtyWorktreeError, LifecycleError),
            "DirtyWorktreeError extends LifecycleError",
        ),
    ]
    for ok, label in hierarchy_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            lifecycle_ok = False

    # Verify structured context on exceptions
    err = DirtyWorktreeError(
        "uncommitted changes",
        session_id="abc123",
        dirty_files="M src/main.py\n?? new_file.txt",
    )
    ctx_checks = [
        (err.session_id == "abc123", "session_id preserved on exception"),
        (err.operation == "kill", "operation auto-set to 'kill'"),
        (err.dirty_files == "M src/main.py\n?? new_file.txt", "dirty_files attached"),
    ]
    for ok, label in ctx_checks:
        mark = Symbols.CHECK if ok else Symbols.CROSS
        color = "green" if ok else "red"
        console.print(f"   [{color}]{mark}[/{color}] {label}")
        if not ok:
            lifecycle_ok = False

    if lifecycle_ok:
        console.print(f"   [green]{Symbols.CHECK} Lifecycle error handling works[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} Lifecycle error handling issues[/red]")
        failed += 1
    console.print()

    # ── 8. MCP Orchestration Tools ─────────────────────────────────────────
    console.print("[bold]8. MCP Orchestration Tools[/bold]")
    console.print("[dim]   FastMCP server exposes Shoal as MCP tools for agent control.[/dim]")
    console.print()

    mcp_tools_ok = True
    mcp_skipped = False
    try:
        from shoal.services.mcp_shoal_server import mcp as shoal_mcp

        tools = await shoal_mcp.list_tools()
        tool_names = sorted(t.name for t in tools)
        expected_tools = [
            "append_journal",
            "create_session",
            "kill_session",
            "list_sessions",
            "read_journal",
            "send_keys",
            "session_info",
            "session_status",
        ]
        if tool_names == expected_tools:
            console.print(f"   [green]{Symbols.CHECK}[/green] 8 MCP tools registered")
        else:
            console.print(
                f"   [red]{Symbols.CROSS}[/red] Expected {expected_tools}, got {tool_names}"
            )
            mcp_tools_ok = False

        # Show each tool with its annotation
        for tool_obj in sorted(tools, key=lambda t: t.name):
            annotations = tool_obj.annotations
            read_only = getattr(annotations, "readOnlyHint", False) if annotations else False
            destructive = getattr(annotations, "destructiveHint", False) if annotations else False
            if read_only:
                badge = "[dim cyan]read-only[/dim cyan]"
            elif destructive:
                badge = "[dim red]destructive[/dim red]"
            else:
                badge = "[dim]unknown[/dim]"
            console.print(f"   [green]{Symbols.CHECK}[/green] {tool_obj.name:20} {badge}")

    except ImportError:
        console.print(
            f"   [yellow]{Symbols.BULLET_FILLED}[/yellow] "
            "fastmcp not installed (pip install shoal[mcp])"
        )
        mcp_skipped = True
    except Exception as e:
        console.print(f"   [red]{Symbols.CROSS}[/red] MCP server introspection failed: {e}")
        mcp_tools_ok = False

    if mcp_skipped:
        console.print(
            f"   [yellow]{Symbols.BULLET_WAITING} MCP orchestration skipped "
            "(optional dependency)[/yellow]"
        )
        skipped += 1
    elif mcp_tools_ok:
        console.print(f"   [green]{Symbols.CHECK} MCP orchestration tools work[/green]")
        passed += 1
    else:
        console.print(f"   [red]{Symbols.CROSS} MCP orchestration issues[/red]")
        failed += 1
    console.print()

    # ── 9. Theme System ────────────────────────────────────────────────────
    console.print("[bold]9. Theme & UI System[/bold]")
    console.print("[dim]   Centralized status icons and colors for CLI.[/dim]")
    console.print()

    for status_name, status_style in STATUS_STYLES.items():
        console.print(
            f"   [{status_style.rich}]{status_style.icon} {status_name:10}[/{status_style.rich}] "
            f"nerd: {status_style.nerd}"
        )

    console.print(f"   [green]{Symbols.CHECK} Theme system works[/green]")
    passed += 1
    console.print()

    # ── Summary ────────────────────────────────────────────────────────────
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


# SessionStatus import needed for detection test cases
from shoal.models.state import SessionStatus  # noqa: E402
