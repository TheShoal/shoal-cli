"""Tests for core/theme.py."""

from rich.panel import Panel
from rich.table import Table
from shoal.core.theme import (
    STATUS_STYLES,
    get_status_style,
    get_status_icon,
    get_status_tmux_color,
    Icons,
    Symbols,
    Colors,
    Layout,
    create_table,
    create_panel,
    tmux_fg,
    tmux_status_segment,
)


def test_status_styles_completeness():
    """Ensure all expected statuses have styles defined."""
    expected_statuses = {"running", "idle", "waiting", "error", "stopped"}
    for status in expected_statuses:
        assert status in STATUS_STYLES
        style = STATUS_STYLES[status]
        assert hasattr(style, "rich")
        assert hasattr(style, "tmux")
        assert hasattr(style, "icon")


def test_get_status_helpers():
    """Test helpers for getting status-specific styles/icons."""
    assert get_status_style("running") == "green"
    assert get_status_style("waiting") == "bold yellow"
    assert get_status_style("unknown") == "dim"  # Default

    assert get_status_icon("running") == "●"
    assert get_status_icon("error") == "✗"
    assert get_status_icon("unknown") == "◌"

    assert get_status_tmux_color("running") == "green"
    assert get_status_tmux_color("stopped") == "grey"


def test_icons_and_symbols():
    """Verify icon and symbol constants."""
    assert Icons.SESSION == "󰚝"
    assert Icons.GIT_ROOT == "󱂵"
    assert Symbols.CHECK == "✔"
    assert Symbols.CROSS == "✘"
    assert Symbols.BULLET_FILLED == "●"


def test_colors_and_layout():
    """Verify color and layout constants."""
    assert Colors.SUCCESS == "green"
    assert Colors.PANEL_BORDER == "dim"
    assert Layout.TABLE_PADDING == (0, 1)


def test_create_table():
    """Test table factory."""
    table = create_table()
    assert isinstance(table, Table)
    assert table.show_header is True
    assert table.header_style == Colors.TABLE_HEADER
    # Rich expands (0, 1) to (0, 1, 0, 1)
    assert tuple(table.padding) == (0, 1, 0, 1)

    # Test overrides
    custom_table = create_table(show_header=False, padding=(1, 1))
    assert custom_table.show_header is False
    assert tuple(custom_table.padding) == (1, 1, 1, 1)


def test_create_panel():
    """Test panel factory."""
    panel = create_panel("content", title="Title")
    assert isinstance(panel, Panel)
    assert panel.renderable == "content"
    # In some Rich versions title is a Text object, in others a string
    title = panel.title
    if hasattr(title, "plain"):
        assert title.plain == "Title"
    else:
        assert title == "Title"
    assert panel.border_style == Colors.PANEL_BORDER

    # Test primary style
    primary_panel = create_panel("content", primary=True)
    assert primary_panel.border_style == Colors.PANEL_BORDER_PRIMARY

    # Test overrides
    custom_panel = create_panel("content", border_style="red")
    assert custom_panel.border_style == "red"


def test_tmux_fg():
    """Test tmux foreground formatting."""
    assert tmux_fg("hello", "green") == "#[fg=green]hello#[default]"


def test_tmux_status_segment():
    """Test tmux status bar segment formatting."""
    from shoal.core.theme import Symbols

    assert tmux_status_segment("●", 5, "green") == "#[fg=green]● 5"
    assert tmux_status_segment("●", 0, "green") == f"#[fg=green] {Symbols.BULLET_OFF}  "
    assert (
        tmux_status_segment("●", 0, "green", empty_width=5)
        == f"#[fg=green] {Symbols.BULLET_OFF}    "
    )
