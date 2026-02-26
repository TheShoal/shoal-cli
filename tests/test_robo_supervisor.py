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


def _make_profile_with_escalation(
    esc_session: str,
    *,
    timeout: int = 60,
) -> RoboProfileConfig:
    return RoboProfileConfig(
        name="test",
        tool="claude",
        auto_approve=False,
        monitoring=MonitoringConfig(poll_interval=10, waiting_timeout=300),
        escalation=EscalationConfig(
            notify=True,
            auto_respond=False,
            escalation_session=esc_session,
            escalation_timeout=timeout,
        ),
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
            assert mock_send.call_count == 0
            assert mock_journal.call_count == 0


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
            assert mock_handle.await_count == 0

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


# ------------------------------------------------------------------
# main() entry point tests
# ------------------------------------------------------------------


def test_main_reads_profile_from_argv(mock_dirs):
    """main() reads profile name from sys.argv[1]."""
    import contextlib
    from unittest.mock import patch

    from shoal.services.robo_supervisor import main

    with (
        patch(
            "shoal.core.config.load_robo_profile",
            side_effect=FileNotFoundError("not found"),
        ) as mock_load,
        patch("shoal.services.robo_supervisor.asyncio.run") as mock_asyncio_run,
        patch("sys.argv", ["shoal-robo-supervisor", "my-profile"]),
        contextlib.suppress(FileNotFoundError),
    ):
        main()
    mock_load.assert_called_once_with("my-profile")
    mock_asyncio_run.assert_not_called()
    assert mock_asyncio_run.call_count == 0


def test_main_defaults_to_default_profile(mock_dirs):
    """main() uses 'default' when sys.argv has no extra args."""
    import contextlib
    from unittest.mock import patch

    from shoal.services.robo_supervisor import main

    with (
        patch(
            "shoal.core.config.load_robo_profile",
            side_effect=FileNotFoundError("not found"),
        ) as mock_load,
        patch("shoal.services.robo_supervisor.asyncio.run") as mock_asyncio_run,
        patch("sys.argv", ["shoal-robo-supervisor"]),
        contextlib.suppress(FileNotFoundError),
    ):
        main()
    mock_load.assert_called_once_with("default")
    mock_asyncio_run.assert_not_called()
    assert mock_asyncio_run.call_count == 0


# ------------------------------------------------------------------
# LLM escalation tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestEscalateLLM:
    async def test_escalate_to_llm_sends_prompt(self, mock_dirs: object) -> None:
        """Verify send_keys is called on escalation session with the prompt."""
        waiting = await create_session("waiting-llm", "claude", "/tmp/repo")
        _esc = await create_session("esc-agent", "claude", "/tmp/repo")

        sup = RoboSupervisor(_make_profile_with_escalation("esc-agent"))

        with (
            patch("shoal.core.tmux.preferred_pane", return_value="%1"),
            patch("shoal.core.tmux.capture_pane", return_value="waiting content"),
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry"),
            patch.object(
                sup,
                "_wait_for_escalation_response",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await sup._escalate_to_llm(waiting, "timeout exceeded")

        mock_send.assert_called_once()
        keys_sent = mock_send.call_args[0][1]
        assert "ROBO ESCALATION" in keys_sent
        assert "waiting-llm" in keys_sent

    async def test_escalate_no_config_falls_back(self, mock_dirs: object) -> None:
        """Verify journal-only behavior when no escalation_session is configured."""
        s = await create_session("no-esc", "claude", "/tmp/repo")
        sup = RoboSupervisor(_make_profile())  # no escalation_session

        with (
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
        ):
            await sup._escalate(s, "timeout exceeded")

        mock_send.assert_not_called()
        mock_journal.assert_called_once()
        content = mock_journal.call_args[0][1]
        assert "**Robo decision**: escalated" in content

    async def test_escalate_timeout(self, mock_dirs: object) -> None:
        """Verify timeout journals escalated-to-llm and escalation-timeout entries."""
        waiting = await create_session("timeout-test", "claude", "/tmp/repo")
        _esc = await create_session("esc-timeout", "claude", "/tmp/repo")

        sup = RoboSupervisor(_make_profile_with_escalation("esc-timeout", timeout=10))

        with (
            patch("shoal.core.tmux.preferred_pane", return_value="%1"),
            patch("shoal.core.tmux.capture_pane", return_value="prompt here"),
            patch("shoal.core.tmux.send_keys"),
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
            patch.object(
                sup,
                "_wait_for_escalation_response",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await sup._escalate_to_llm(waiting, "timeout exceeded")

        decisions = [call[0][1] for call in mock_journal.call_args_list]
        assert any("escalated-to-llm" in d for d in decisions)
        assert any("escalation-timeout" in d for d in decisions)

    async def test_escalate_approve_response(self, mock_dirs: object) -> None:
        """Verify auto_approve is called when LLM agent responds with 'approve'."""
        waiting = await create_session("approve-test", "claude", "/tmp/repo")
        _esc = await create_session("esc-approve", "claude", "/tmp/repo")

        sup = RoboSupervisor(_make_profile_with_escalation("esc-approve"))

        with (
            patch("shoal.core.tmux.preferred_pane", return_value="%1"),
            patch("shoal.core.tmux.capture_pane", return_value="Allow this action?"),
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
            patch.object(
                sup,
                "_wait_for_escalation_response",
                new_callable=AsyncMock,
                return_value="approve",
            ),
        ):
            await sup._escalate_to_llm(waiting, "ambiguous prompt")

        # send_keys called once for the prompt, once for the approval Enter
        assert mock_send.call_count >= 2
        decisions = [call[0][1] for call in mock_journal.call_args_list]
        assert any("approved-by-llm" in d for d in decisions)

    async def test_escalate_session_not_found(self, mock_dirs: object) -> None:
        """Verify graceful fallback when escalation session name is not in DB."""
        waiting = await create_session("not-found-test", "claude", "/tmp/repo")
        # "nonexistent-esc" is not created in DB

        sup = RoboSupervisor(_make_profile_with_escalation("nonexistent-esc"))

        with (
            patch("shoal.core.tmux.send_keys") as mock_send,
            patch("shoal.services.robo_supervisor.append_entry") as mock_journal,
        ):
            await sup._escalate_to_llm(waiting, "timeout exceeded")

        mock_send.assert_not_called()
        mock_journal.assert_called_once()
        content = mock_journal.call_args[0][1]
        assert "escalated" in content
