"""Tests for the shoal history CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

runner = CliRunner()


def test_history_session_not_found(mock_dirs: object) -> None:
    """history command exits with error for unknown session."""
    from shoal.cli import app

    result = runner.invoke(app, ["history", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_history_shows_transitions(mock_dirs: object) -> None:
    """history command displays transitions in a table."""
    from shoal.cli import app

    async def mock_resolve(name: str) -> str:
        return "sess-id-1"

    fake_transitions = [
        {
            "id": "t1",
            "session_id": "sess-id-1",
            "from_status": "idle",
            "to_status": "running",
            "timestamp": "2026-02-24T10:00:00+00:00",
            "pane_snapshot": None,
        },
        {
            "id": "t2",
            "session_id": "sess-id-1",
            "from_status": "running",
            "to_status": "waiting",
            "timestamp": "2026-02-24T10:00:30+00:00",
            "pane_snapshot": None,
        },
    ]

    mock_db = AsyncMock()
    mock_db.get_status_transitions = AsyncMock(return_value=fake_transitions)

    with (
        patch("shoal.cli.history.resolve_session", side_effect=mock_resolve),
        patch("shoal.cli.history.get_db", return_value=mock_db),
    ):
        result = runner.invoke(app, ["history", "my-session"])
    assert result.exit_code == 0
    assert "idle" in result.output
    assert "running" in result.output
    assert "waiting" in result.output
    assert "2 transition(s)" in result.output


def test_history_no_transitions(mock_dirs: object) -> None:
    """history command shows message when no transitions exist."""
    from shoal.cli import app

    async def mock_resolve(name: str) -> str:
        return "sess-id-1"

    mock_db = AsyncMock()
    mock_db.get_status_transitions = AsyncMock(return_value=[])

    with (
        patch("shoal.cli.history.resolve_session", side_effect=mock_resolve),
        patch("shoal.cli.history.get_db", return_value=mock_db),
    ):
        result = runner.invoke(app, ["history", "my-session"])
    assert result.exit_code == 0
    assert "No status transitions" in result.output


def test_history_limit_passed_to_db(mock_dirs: object) -> None:
    """--limit flag is forwarded to the DB query."""
    from shoal.cli import app

    async def mock_resolve(name: str) -> str:
        return "sess-id-1"

    mock_db = AsyncMock()
    mock_db.get_status_transitions = AsyncMock(return_value=[])

    with (
        patch("shoal.cli.history.resolve_session", side_effect=mock_resolve),
        patch("shoal.cli.history.get_db", return_value=mock_db),
    ):
        result = runner.invoke(app, ["history", "my-session", "--limit", "5"])

    assert result.exit_code == 0
    mock_db.get_status_transitions.assert_awaited_once_with("sess-id-1", limit=5)


def test_history_duration_display(mock_dirs: object) -> None:
    """Last transition shows 'current' duration."""
    from shoal.cli import app

    async def mock_resolve(name: str) -> str:
        return "sess-id-1"

    fake_transitions = [
        {
            "id": "t1",
            "session_id": "sess-id-1",
            "from_status": "idle",
            "to_status": "running",
            "timestamp": "2026-02-24T10:00:00+00:00",
            "pane_snapshot": None,
        },
    ]

    mock_db = AsyncMock()
    mock_db.get_status_transitions = AsyncMock(return_value=fake_transitions)

    with (
        patch("shoal.cli.history.resolve_session", side_effect=mock_resolve),
        patch("shoal.cli.history.get_db", return_value=mock_db),
    ):
        result = runner.invoke(app, ["history", "my-session"])
    assert result.exit_code == 0
    assert "current" in result.output
