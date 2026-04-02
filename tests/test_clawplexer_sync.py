"""Tests for shoal.integrations.lobster.clawplexer_sync module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from shoal.integrations.lobster.clawplexer_sync import ClawplexerSync, sync_for_handoff

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def session_id() -> str:
    return "sess-1"


@pytest.fixture
def convos_dir(tmp_path: Path) -> Path:
    d = tmp_path / "convos"
    d.mkdir()
    return d


@pytest.fixture
def syncer(session_id: str, convos_dir: Path) -> ClawplexerSync:
    return ClawplexerSync(session_id=session_id, conversations_dir=convos_dir)


# -----------------------------------------------------------------------------
# ClawplexerSync Tests
# -----------------------------------------------------------------------------


def test_clawplexer_sync_instantiation(session_id: str, convos_dir: Path):
    """Verify basic instantiation and attribute storage."""
    syncer = ClawplexerSync(session_id=session_id, conversations_dir=convos_dir)
    assert syncer.session_id == session_id
    assert syncer.conversations_dir == convos_dir
    assert syncer.poll_interval == 30.0


def test_clawplexer_sync_custom_poll_interval(session_id: str, convos_dir: Path):
    """Verify custom poll interval is stored."""
    syncer = ClawplexerSync(
        session_id=session_id,
        conversations_dir=convos_dir,
        poll_interval=10.0,
    )
    assert syncer.poll_interval == 10.0


def test_sync_once_calls_sync_journal_with_qmd(syncer: ClawplexerSync, session_id: str):
    """Verify sync_once calls the underlying sync function with correct arguments."""
    with patch("shoal.core.qmd.sync_journal_with_qmd") as mock_sync:
        mock_sync.return_value = {"imported": 3, "exported": 0}

        syncer.sync_once(direction="import")

        mock_sync.assert_called_once()
        _, kwargs = mock_sync.call_args
        assert kwargs["session_id"] == session_id
        assert kwargs["direction"] == "import"


def test_sync_once_returns_counts(syncer: ClawplexerSync):
    """Verify sync_once returns the counts from the underlying sync function."""
    counts = {"imported": 5, "exported": 2}
    with patch(
        "shoal.core.qmd.sync_journal_with_qmd",
        return_value=counts,
    ):
        result = syncer.sync_once(direction="both")
        assert result == counts


def test_sync_once_default_direction_is_import(syncer: ClawplexerSync):
    """Verify 'import' is the default direction for sync_once."""
    with patch("shoal.core.qmd.sync_journal_with_qmd") as mock_sync:
        mock_sync.return_value = {"imported": 0, "exported": 0}

        syncer.sync_once()

        mock_sync.assert_called_once()
        assert mock_sync.call_args.kwargs["direction"] == "import"


async def test_run_sync_loop_stops_after_one_sync(syncer: ClawplexerSync):
    """Verify run_sync_loop respects the stop event."""
    with (
        patch(
            "shoal.core.qmd.sync_journal_with_qmd",
            return_value={"imported": 0, "exported": 0},
        ) as mock_sync,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        stop = asyncio.Event()
        stop.set()  # Already set to stop immediately

        await syncer.run_sync_loop(stop_event=stop)

        assert mock_sync.call_count >= 1


# -----------------------------------------------------------------------------
# sync_for_handoff Tests
# -----------------------------------------------------------------------------


def test_sync_for_handoff_returns_imported_count(session_id: str, convos_dir: Path):
    """Verify sync_for_handoff extracts the imported count."""
    with patch(
        "shoal.core.qmd.sync_journal_with_qmd",
        return_value={"imported": 7, "exported": 0},
    ):
        result = sync_for_handoff(session_id, convos_dir)
        assert result == 7


def test_sync_for_handoff_zero_imported(session_id: str, convos_dir: Path):
    """Verify sync_for_handoff handles zero imports correctly."""
    with patch(
        "shoal.core.qmd.sync_journal_with_qmd",
        return_value={"imported": 0, "exported": 0},
    ):
        result = sync_for_handoff(session_id, convos_dir)
        assert result == 0
