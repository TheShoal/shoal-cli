"""Centralized styling, icons, and colors for shoal UI.

This module provides a single source of truth for all visual elements:
- Status colors and icons (for both Rich CLI and tmux status bar)
- Label icons (Nerd Font glyphs used in info/status views)
- UI symbols (checkmarks, arrows, etc.)
- Layout constants (table/panel styling)
- Factory helpers for consistent UI construction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.panel import Panel
from rich.table import Table

# ============================================================================
# Status Definitions
# ============================================================================


@dataclass(frozen=True)
class StatusStyle:
    """Style definition for a session status across different contexts."""

    rich: str  # Rich markup style (e.g., "bold green")
    tmux: str  # Tmux color name (e.g., "green")
    icon: str  # Unicode symbol (renders universally)
    nerd: str  # Nerd Font glyph (optional, may not render everywhere)


# Single source of truth for status → icon + color mapping
STATUS_STYLES = {
    "running": StatusStyle(rich="green", tmux="green", icon="●", nerd=""),
    "idle": StatusStyle(rich="white", tmux="white", icon="○", nerd=""),
    "waiting": StatusStyle(rich="bold yellow", tmux="yellow", icon="◉", nerd=""),
    "error": StatusStyle(rich="bold red", tmux="red", icon="✗", nerd=""),
    "stopped": StatusStyle(rich="dim", tmux="grey", icon="◌", nerd=""),
}


def get_status_style(status: str) -> str:
    """Get Rich markup style for a session status.

    Args:
        status: Session status value (running, idle, waiting, error, stopped)

    Returns:
        Rich style string (e.g., "bold yellow")
    """
    return STATUS_STYLES.get(status, STATUS_STYLES["stopped"]).rich


def get_status_icon(status: str, use_nerd: bool = False) -> str:
    """Get icon for a session status.

    Args:
        status: Session status value
        use_nerd: If True, use Nerd Font glyph; otherwise use Unicode symbol

    Returns:
        Icon string
    """
    style = STATUS_STYLES.get(status, STATUS_STYLES["stopped"])
    return style.nerd if use_nerd else style.icon


def get_status_tmux_color(status: str) -> str:
    """Get tmux color name for a session status.

    Args:
        status: Session status value

    Returns:
        Tmux color name (e.g., "green")
    """
    return STATUS_STYLES.get(status, STATUS_STYLES["stopped"]).tmux


# ============================================================================
# Label Icons (Nerd Font glyphs for section headers)
# ============================================================================


class Icons:
    """Nerd Font icons used in info/status views."""

    # Session/project icons
    SESSION = "󰚝"  # nf-md-shark
    GHOST = "󱄽"  # nf-md-ghost (for missing sessions)

    # Metadata icons
    TOOL = "󰏗"  # nf-md-android
    DATE = "󰃭"  # nf-md-calendar_clock
    ACTIVITY = "󰥔"  # nf-md-timer_sand

    # Git/worktree icons
    GIT_ROOT = "󱂵"  # nf-md-source_branch
    WORKTREE = "󱉭"  # nf-md-file_tree
    BRANCH = "󰘬"  # nf-md-source_branch_sync

    # Technical icons
    TMUX = "󰒋"  # nf-md-window_restore
    PID = "󰆍"  # nf-md-identifier
    MCP = "󰒔"  # nf-md-server
    OUTPUT = "󰆍"  # nf-md-identifier (reused for output)

    # UI icons
    STATUS = "󰀦"  # nf-md-alert_circle
    ERROR_ICON = "󰅚"  # nf-md-close_circle

    # Dashboard/navigation
    DASHBOARD = "󰚩"  # nf-md-view_dashboard
    DEPENDENCY = "󰒓"  # nf-md-package_variant
    DIRECTORY = "󰓗"  # nf-md-folder
    FISH = "󰈺"  # nf-md-fish

    # Information/help
    INFO = "󰋽"  # nf-md-information
    ERROR = "󰅙"  # nf-md-alert_octagon


# ============================================================================
# UI Symbols (universal Unicode characters)
# ============================================================================


class Symbols:
    """Unicode symbols that render universally (no special font required)."""

    # Status indicators
    CHECK = "✔"
    CROSS = "✘"
    ARROW = "→"
    INFO = "ℹ"

    # fzf/picker markers
    POINTER = "▶"
    MARKER = "●"

    # Bullets
    BULLET_FILLED = "●"
    BULLET_EMPTY = "○"
    BULLET_WAITING = "◉"
    BULLET_ERROR = "✗"
    BULLET_STOPPED = "◌"
    BULLET_OFF = ""


# ============================================================================
# Color Constants
# ============================================================================


class Colors:
    """Named color constants for consistency."""

    # Status colors (aligned with STATUS_STYLES)
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    INFO = "cyan"
    DIM = "dim"

    # Section headers
    HEADER_PRIMARY = "bold cyan"
    HEADER_SECONDARY = "bold green"
    HEADER_WARNING = "bold yellow"

    # UI elements
    PANEL_BORDER = "dim"
    PANEL_BORDER_PRIMARY = "blue"
    TABLE_HEADER = "bold magenta"


# ============================================================================
# Layout Constants
# ============================================================================


class Layout:
    """Layout and spacing constants."""

    # Table defaults
    TABLE_PADDING = (0, 1)
    TABLE_PADDING_WIDE = (0, 2)
    TABLE_BOX = None  # No box borders

    # Panel defaults
    PANEL_PADDING = (1, 2)
    PANEL_PADDING_COMPACT = (0, 1)


# ============================================================================
# Factory Helpers
# ============================================================================


def create_table(**overrides: Any) -> Table:
    """Create a standard table with consistent styling.

    Default settings:
    - Header style: bold magenta
    - No box borders
    - Padding: (0, 1)
    - Header shown

    Args:
        **overrides: Any Table constructor arguments to override defaults

    Returns:
        Configured Rich Table instance

    Example:
        table = create_table(padding=(0, 2))
        table.add_column("Name", width=20)
    """
    defaults = {
        "show_header": True,
        "header_style": Colors.TABLE_HEADER,
        "box": Layout.TABLE_BOX,
        "padding": Layout.TABLE_PADDING,
    }
    defaults.update(overrides)
    return Table(**defaults)  # type: ignore[arg-type]


def create_panel(
    content: Any,
    title: str | None = None,
    primary: bool = False,
    **overrides: Any,
) -> Panel:
    """Create a standard panel with consistent styling.

    Default settings:
    - Border style: dim (or blue if primary=True)
    - Standard Rich panel construction

    Args:
        content: Panel content (Text, Table, string, etc.)
        title: Optional panel title
        primary: If True, use primary border style (blue)
        **overrides: Any Panel constructor arguments to override defaults

    Returns:
        Configured Rich Panel instance

    Example:
        panel = create_panel(table, title="Sessions", primary=True)
    """
    defaults = {
        "border_style": Colors.PANEL_BORDER_PRIMARY if primary else Colors.PANEL_BORDER,
    }
    if title:
        defaults["title"] = title
    defaults.update(overrides)
    return Panel(content, **defaults)  # type: ignore[arg-type]


# ============================================================================
# Tmux Formatting Helpers
# ============================================================================


def tmux_fg(text: str, color: str) -> str:
    """Wrap text in tmux foreground color formatting.

    Args:
        text: Text to colorize
        color: Tmux color name (green, red, yellow, etc.)

    Returns:
        Formatted string: #[fg=color]text#[default]

    Example:
        tmux_fg("Running", "green") -> "#[fg=green]Running#[default]"
    """
    return f"#[fg={color}]{text}#[default]"


def tmux_status_segment(icon: str, count: int, color: str, empty_width: int = 3) -> str:
    """Format a tmux status bar segment.

    Args:
        icon: Icon to display when count > 0
        count: Count to display
        color: Tmux color name
        empty_width: Width to reserve when count is 0 (default: 3 chars)

    Returns:
        Formatted segment string

    Example:
        tmux_status_segment("●", 5, "green") -> "#[fg=green]● 5"
        tmux_status_segment("●", 0, "green") -> "#[fg=green]  "
    """
    if count == 0:
        return f"#[fg={color}] {Symbols.BULLET_OFF}{' ' * (empty_width - 1)}"
    return f"#[fg={color}]{icon} {count}"
