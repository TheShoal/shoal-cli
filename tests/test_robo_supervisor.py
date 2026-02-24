"""Tests for the robo supervisor service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from shoal.core.state import create_session, update_session
from shoal.models.config import (
    DetectionPatterns,
    EscalationConfig,
    MonitoringConfig,
    RoboProfileConfig,
    ToolConfig,
)
from shoal.models.state import SessionStatus
from shoal.services.robo_supervisor import RoboSupervisor


def _make_profile(
    *,
    auto_approve: bool = False,
    poll_interval: int = 10,
    waiting_timeout: int = 300,
) -> RoboProfileConfig:
    return RoboProfileConfig(
        name="test",
        tool="claude",
        auto_approve=auto_approve,
        monitoring=MonitoringConfig(
            poll_interval=poll_interval,
            waiting_timeout=waiting_timeout,
        ),
        escalation=EscalationConfig(notify=True, auto_respond=False),
    )


def _make_tool_config() -> ToolConfig:
    return ToolConfig(
        name="claude",
        command="claude",
        icon="C",
        detection=DetectionPatterns(
            busy_patterns=["thinking"],
            waiting_patterns=["Yes/No", "Allow"],
            error_patterns=["Error:", "ERROR"],
            idle_patterns=["\\$"],
        ),
    )


# ------------------------------------------------------------------
# _safe_to_approve tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestSafeToApprove:
    async def test_yes_no_prompt(self) -> None:
        """Returns True for 'Yes/No' pattern when auto_approve is on."""
        sup = RoboSupervisor(_make_profile(auto_approve=True))
        tc = _make_tool_config()
        assert sup._safe_to_approve("Do you want to continue? Yes/No", tc) is True

    async def test_permission_prompt(self) -> None:
        """Returns True for 'Allow' pattern when auto_approve is on."""
        sup = RoboSupervisor(_make_profile(auto_approve=True))
        tc = _make_tool_config()
        assert sup._safe_to_approve("Allow this action?", tc) is True

    async def test_error_state(self) -> None:
        """Returns False when pane content contains an error pattern."""
        sup = RoboSupervisor(_make_profile(auto_approve=True))
        tc = _make_tool_config()
        assert sup._safe_to_approve("Error: something broke\nYes/No", tc) is False

    async def test_unknown_content(self) -> None:
        """Returns False for unrecognized content."""
        sup = RoboSupervisor(_make_profile(auto_approve=True))
        tc = _make_tool_config()
        assert sup._safe_to_approve("some random output", tc) is False

    async def test_disabled(self) -> None:
        """Returns False when auto_approve is disabled."""
        sup = RoboSupervisor(_make_profile(auto_approve=False))
        tc = _make_tool_config()
        assert sup._safe_to_approve("Yes/No", tc) is False


# ------------------------------------------------------------------
# _handle_waiting tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandleWaiting:
    async def test_approves_safe(self, mock_dirs: object) -> None:
        """Auto-approves safe waiting prompts and journals the decision."""
        s = await create_session("robo-test", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.waiting)

        sup = RoboSupervisor(_make_profile(auto_approve=True))

        with (
            patch(
                "shoal.core.tmux.preferred_pane",
                return_value=f"%robo-{s.id}",
            ),
            patch(
                "shoal.core.tmux.capture_pane",
                return_value="Allow this action?",
            ),
            patch(
                "shoal.services.robo_supervisor.load_tool_config",
                return_value=_make_tool_config(),
            ),
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
        ):
            await sup._handle_waiting(s)

            mock_send.assert_called_once_with(f"%robo-{s.id}", "", enter=True)
            mock_journal.assert_called_once()
            call_args = mock_journal.call_args
            assert call_args[0][0] == s.id
            assert "approved" in call_args[0][1]
            assert call_args[0][2] == "robo"

    async def test_escalates_timeout(self, mock_dirs: object) -> None:
        """Escalates when waiting duration exceeds timeout."""
        s = await create_session("robo-test", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.waiting)

        sup = RoboSupervisor(_make_profile(auto_approve=False, waiting_timeout=60))

        # Record a transition 120 seconds ago
        old_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()

        with (
            patch(
                "shoal.core.tmux.preferred_pane",
                return_value=f"%robo-{s.id}",
            ),
            patch(
                "shoal.core.tmux.capture_pane",
                return_value="some unknown prompt",
            ),
            patch(
                "shoal.services.robo_supervisor.load_tool_config",
                return_value=_make_tool_config(),
            ),
            patch("shoal.core.tmux.send_keys"),
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
            patch(
                "shoal.services.robo_supervisor.get_db",
                new_callable=AsyncMock,
            ) as mock_get_db,
        ):
            mock_db = AsyncMock()
            mock_db.get_status_transitions.return_value = [
                {
                    "id": "t1",
                    "session_id": s.id,
                    "from_status": "running",
                    "to_status": "waiting",
                    "timestamp": old_ts,
                    "pane_snapshot": None,
                },
            ]
            mock_get_db.return_value = mock_db

            await sup._handle_waiting(s)

            mock_journal.assert_called_once()
            call_args = mock_journal.call_args
            assert call_args[0][0] == s.id
            assert "escalated" in call_args[0][1]

    async def test_waits_under_timeout(self, mock_dirs: object) -> None:
        """Does nothing when under timeout and not safe to approve."""
        s = await create_session("robo-test", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.waiting)

        sup = RoboSupervisor(_make_profile(auto_approve=False, waiting_timeout=300))

        # Transition only 10 seconds ago
        recent_ts = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()

        with (
            patch(
                "shoal.core.tmux.preferred_pane",
                return_value=f"%robo-{s.id}",
            ),
            patch(
                "shoal.core.tmux.capture_pane",
                return_value="some unknown prompt",
            ),
            patch(
                "shoal.services.robo_supervisor.load_tool_config",
                return_value=_make_tool_config(),
            ),
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
            patch(
                "shoal.services.robo_supervisor.get_db",
                new_callable=AsyncMock,
            ) as mock_get_db,
        ):
            mock_db = AsyncMock()
            mock_db.get_status_transitions.return_value = [
                {
                    "id": "t1",
                    "session_id": s.id,
                    "from_status": "running",
                    "to_status": "waiting",
                    "timestamp": recent_ts,
                    "pane_snapshot": None,
                },
            ]
            mock_get_db.return_value = mock_db

            await sup._handle_waiting(s)

            mock_send.assert_not_called()
            mock_journal.assert_not_called()


# ------------------------------------------------------------------
# _poll tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestPoll:
    async def test_skips_non_waiting(self, mock_dirs: object) -> None:
        """Poll only processes sessions with 'waiting' status."""
        s1 = await create_session("busy-session", "claude", "/tmp/repo")
        await update_session(s1.id, status=SessionStatus.running)

        s2 = await create_session("idle-session", "claude", "/tmp/repo")
        await update_session(s2.id, status=SessionStatus.idle)

        s3 = await create_session("error-session", "claude", "/tmp/repo")
        await update_session(s3.id, status=SessionStatus.error)

        sup = RoboSupervisor(_make_profile())

        with patch.object(sup, "_handle_waiting", new_callable=AsyncMock) as mock_handle:
            await sup._poll()
            mock_handle.assert_not_called()

    async def test_handles_waiting_sessions(self, mock_dirs: object) -> None:
        """Poll processes only sessions with 'waiting' status."""
        s1 = await create_session("running-session", "claude", "/tmp/repo")
        await update_session(s1.id, status=SessionStatus.running)

        s2 = await create_session("waiting-session", "claude", "/tmp/repo")
        await update_session(s2.id, status=SessionStatus.waiting)

        sup = RoboSupervisor(_make_profile())

        with patch.object(sup, "_handle_waiting", new_callable=AsyncMock) as mock_handle:
            await sup._poll()
            mock_handle.assert_called_once()
            handled = mock_handle.call_args[0][0]
            assert handled.name == "waiting-session"


# ------------------------------------------------------------------
# _journal_decision tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestJournalDecision:
    async def test_format(self, mock_dirs: object) -> None:
        """Journal decision writes expected format with source='robo'."""
        s = await create_session("robo-test", "claude", "/tmp/repo")

        sup = RoboSupervisor(_make_profile())

        with patch("shoal.services.robo_supervisor.append_entry") as mock_entry:
            await sup._journal_decision(s, "approved", "Test detail")

            mock_entry.assert_called_once()
            args = mock_entry.call_args[0]
            assert args[0] == s.id
            assert "**Robo decision**: approved" in args[1]
            assert "Test detail" in args[1]
            assert args[2] == "robo"
