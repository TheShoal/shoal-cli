"""Tests for dashboard/popup.py."""

import asyncio

import pytest

from shoal.core.db import with_db
from shoal.core.state import create_session, update_session
from shoal.dashboard.popup import _build_entries, print_popup_list
from shoal.models.state import SessionStatus


@pytest.mark.asyncio
async def test_build_entries_empty(mock_dirs):
    """Test _build_entries with no sessions."""
    entries, lookup = await _build_entries()
    assert entries == []
    assert lookup == {}


@pytest.mark.asyncio
async def test_build_entries_with_sessions(mock_dirs):
    """Test _build_entries with existing sessions."""
    s1 = await create_session("test1", "claude", "/tmp/repo1")
    await update_session(s1.id, status=SessionStatus.running, branch="main")

    s2 = await create_session("test2", "opencode", "/tmp/repo2")
    await update_session(s2.id, status=SessionStatus.idle)

    entries, lookup = await _build_entries()
    assert len(entries) == 2
    assert len(lookup) == 2
    assert lookup[s1.id] == s1.tmux_session

    # Check format: id\ticon name\ttool\tstatus\tbranch\tlast
    entry1 = next(e for e in entries if e.startswith(s1.id))
    assert "test1" in entry1
    assert "claude" in entry1
    assert "running" in entry1
    assert "main" in entry1

    entry2 = next(e for e in entries if e.startswith(s2.id))
    assert "test2" in entry2
    assert "opencode" in entry2
    assert "idle" in entry2
    assert "-" in entry2  # Default branch


def test_run_popup_success(mock_dirs, tmp_path):
    """Test run_popup handles selection using lookup."""
    from unittest.mock import MagicMock, patch

    from shoal.dashboard.popup import run_popup

    async def setup():
        await create_session("test-popup", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    mock_result = MagicMock()
    mock_result.returncode = 0
    # Simulate selecting the first session
    entries, _ = asyncio.run(with_db(_build_entries()))
    mock_result.stdout = entries[0]

    with (
        patch("shoal.dashboard.popup.subprocess.run", return_value=mock_result),
        patch("shoal.core.tmux.has_session", return_value=True),
        patch("shoal.core.tmux.switch_client") as mock_switch,
    ):
        run_popup()
        mock_switch.assert_called_once_with("_test-popup")
        assert mock_switch.call_count == 1


def test_print_popup_list(mock_dirs, capsys):
    """Test print_popup_list output."""
    import asyncio

    from shoal.core.db import with_db

    async def setup():
        s = await create_session("test-print", "claude", "/tmp")
        await update_session(s.id, status=SessionStatus.running)

    asyncio.run(with_db(setup()))

    print_popup_list()

    captured = capsys.readouterr()
    assert "test-print" in captured.out
    assert "claude" in captured.out
    assert "running" in captured.out
