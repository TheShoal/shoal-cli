"""Tests for 'shoal done' CLI command."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

runner = CliRunner()


def _make_state(name: str = "myworker"):
    from shoal.models.state import SessionState, SessionStatus

    now = datetime.now(UTC)
    return SessionState(
        id="abc123",
        name=name,
        tool="claude",
        path="/tmp/repo",
        tmux_session=f"_{name}",
        status=SessionStatus.idle,
        created_at=now,
        last_activity=now,
        status_since=now,
    )


def test_session_done_success(mock_dirs):
    """shoal done myworker calls complete_session and prints confirmation."""
    from shoal.cli import app

    mock_state = _make_state("myworker")

    with patch(
        "shoal.services.lifecycle.complete_session",
        new_callable=AsyncMock,
        return_value=mock_state,
    ) as mock_cs:
        result = runner.invoke(app, ["done", "myworker"])

    assert result.exit_code == 0, result.output
    assert "myworker" in result.output
    assert "marked complete" in result.output
    mock_cs.assert_called_once_with("myworker", "")


def test_session_done_with_summary(mock_dirs):
    """shoal done myworker --summary ... passes summary to complete_session."""
    from shoal.cli import app

    mock_state = _make_state("myworker")

    with patch(
        "shoal.services.lifecycle.complete_session",
        new_callable=AsyncMock,
        return_value=mock_state,
    ) as mock_cs:
        result = runner.invoke(app, ["done", "myworker", "--summary", "finished feature X"])

    assert result.exit_code == 0, result.output
    mock_cs.assert_called_once_with("myworker", "finished feature X")


def test_session_done_not_found(mock_dirs):
    """shoal done nonexistent exits with code 1 when session is missing."""
    from shoal.cli import app
    from shoal.services.lifecycle import SessionNotFoundError

    with patch(
        "shoal.services.lifecycle.complete_session",
        new_callable=AsyncMock,
        side_effect=SessionNotFoundError("Session not found: nonexistent"),
    ):
        result = runner.invoke(app, ["done", "nonexistent"])

    assert result.exit_code == 1
