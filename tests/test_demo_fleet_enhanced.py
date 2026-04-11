"""Tests for enhanced fleet demo with --live and --interactive flags."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.cli.demo.fleet import (
    step_morning_summary,
    step_planner,
    step_reviewer,
)


@pytest.mark.asyncio
async def test_step_planner_mock_mode() -> None:
    """Test planner step with live=False preserves mock behavior."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as mock_append,
        patch("shoal.cli.demo.fleet.read_journal") as mock_read,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
    ):
        # Setup mocks
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["planner", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"

        mock_entry = MagicMock()
        mock_entry.content = "## Plan: Greeting Feature"
        mock_read.return_value = [mock_entry]

        # Execute
        result, session_id = await step_planner("/tmp/test", live=False)

        # Verify mock behavior was used
        assert session_id == "test-session-id"
        assert result.passed
        assert result.label == "Planner scopes work"

        # Verify append_entry was called with mock content
        mock_append.assert_called_once()
        call_args = mock_append.call_args
        assert "greeting" in call_args[0][1].lower()
        assert call_args[1]["source"] == "planner"


@pytest.mark.asyncio
async def test_step_planner_live_mode_no_token() -> None:
    """Test planner step with live=True but no LINEAR_TOKEN falls back to mock."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as mock_append,
        patch("shoal.cli.demo.fleet.read_journal") as mock_read,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
        patch.dict("os.environ", {}, clear=True),  # No LINEAR_TOKEN
    ):
        # Setup mocks
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["planner", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"

        mock_entry = MagicMock()
        mock_entry.content = "## Plan: Greeting Feature"
        mock_read.return_value = [mock_entry]

        # Execute
        result, session_id = await step_planner("/tmp/test", live=True)

        # Verify it fell back to mock mode
        assert session_id == "test-session-id"
        assert result.passed

        # Should have used mock content
        mock_append.assert_called_once()
        call_args = mock_append.call_args
        assert "greeting" in call_args[0][1].lower()


@pytest.mark.asyncio
async def test_step_planner_live_mode_with_token_mock_bridge() -> None:
    """Test planner step with live=True and LINEAR_TOKEN but mocked bridge."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as _mock_append,
        patch("shoal.cli.demo.fleet.read_journal") as mock_read,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
        patch.dict("os.environ", {"LINEAR_TOKEN": "test-token"}),
    ):
        # Setup mocks
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["planner", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"

        mock_entry = MagicMock()
        mock_entry.content = "## Plan: Live ticket"
        mock_read.return_value = [mock_entry]

        # Mock the Linear bridge
        mock_bridge = AsyncMock()
        mock_bridge.close = AsyncMock()

        with patch("shoal.services.linear_bridge.get_linear_bridge", return_value=mock_bridge):
            # Execute
            result, session_id = await step_planner("/tmp/test", live=True)

            # Verify session was created
            assert session_id == "test-session-id"
            assert result.passed

            # Bridge should have been closed
            mock_bridge.close.assert_called_once()


@pytest.mark.asyncio
async def test_step_reviewer_mock_mode() -> None:
    """Test reviewer step with live=False preserves mock behavior."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as mock_append,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
        patch("shoal.cli.demo.fleet.derive_urgency") as mock_urgency,
    ):
        # Setup mocks
        from shoal.core.urgency import UrgencyTier

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["reviewer", "review-ready", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"
        mock_urgency.return_value = (UrgencyTier.review, "review")

        # Execute
        result, session_id = await step_reviewer("/tmp/test", live=False)

        # Verify mock behavior was used
        assert session_id == "test-session-id"
        assert result.passed
        assert result.label == "Reviewer + urgency"

        # Verify append_entry was called with mock content
        mock_append.assert_called_once()
        call_args = mock_append.call_args
        assert "greeting.py" in call_args[0][1].lower()
        assert call_args[1]["source"] == "reviewer"


@pytest.mark.asyncio
async def test_step_reviewer_live_mode_no_token() -> None:
    """Test reviewer step with live=True but no GITHUB_TOKEN falls back to mock."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as mock_append,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
        patch("shoal.cli.demo.fleet.derive_urgency") as mock_urgency,
        patch.dict("os.environ", {}, clear=True),  # No GITHUB_TOKEN
    ):
        # Setup mocks
        from shoal.core.urgency import UrgencyTier

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["reviewer", "review-ready", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"
        mock_urgency.return_value = (UrgencyTier.review, "review")

        # Execute
        result, session_id = await step_reviewer("/tmp/test", live=True)

        # Verify it fell back to mock mode
        assert session_id == "test-session-id"
        assert result.passed

        # Should have used mock content
        mock_append.assert_called_once()
        call_args = mock_append.call_args
        assert "greeting.py" in call_args[0][1].lower()


@pytest.mark.asyncio
async def test_step_reviewer_live_mode_with_token_mock_bridge() -> None:
    """Test reviewer step with live=True and GITHUB_TOKEN but mocked bridge."""
    with (
        patch("shoal.cli.demo.fleet.create_session") as mock_create,
        patch("shoal.cli.demo.fleet.get_session") as mock_get,
        patch("shoal.cli.demo.fleet.append_entry") as _mock_append,
        patch("shoal.cli.demo.fleet.git.current_branch") as mock_branch,
        patch("shoal.cli.demo.fleet.derive_urgency") as mock_urgency,
        patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}),
    ):
        # Setup mocks
        from shoal.core.urgency import UrgencyTier

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.tags = ["reviewer", "review-ready", "fleet-demo"]
        mock_create.return_value = mock_session
        mock_get.return_value = mock_session
        mock_branch.return_value = "main"
        mock_urgency.return_value = (UrgencyTier.review, "review")

        # Mock the GitHub bridge
        mock_bridge = AsyncMock()
        mock_bridge.close = AsyncMock()

        with patch("shoal.services.github_bridge.get_github_bridge", return_value=mock_bridge):
            # Execute
            result, session_id = await step_reviewer("/tmp/test", live=True)

            # Verify session was created
            assert session_id == "test-session-id"
            assert result.passed

            # Bridge should have been closed
            mock_bridge.close.assert_called_once()


@pytest.mark.asyncio
async def test_step_morning_summary_mock_mode() -> None:
    """Test morning summary step with live=False preserves mock behavior."""
    with (
        patch("shoal.cli.demo.fleet.list_sessions") as mock_list,
        patch("shoal.cli.demo.fleet.delete_session") as mock_delete,
        patch("shoal.cli.demo.fleet.read_journal") as mock_read,
        patch("shoal.cli.demo.fleet.generate_handoff") as mock_handoff,
        patch("shoal.cli.demo.fleet.derive_urgency") as mock_urgency,
    ):
        # Setup mocks
        from shoal.core.urgency import UrgencyTier

        mock_session1 = MagicMock()
        mock_session1.name = "fleet/planner"
        mock_session1.tags = ["planner", "fleet-demo"]
        mock_session1.status = "idle"

        mock_session2 = MagicMock()
        mock_session2.name = "fleet/implementer"
        mock_session2.tags = ["implementer", "fleet-demo"]
        mock_session2.status = "idle"

        mock_session3 = MagicMock()
        mock_session3.name = "fleet/reviewer"
        mock_session3.tags = ["reviewer", "fleet-demo"]
        mock_session3.status = "idle"

        mock_list.return_value = [mock_session1, mock_session2, mock_session3]
        mock_read.return_value = []
        mock_urgency.return_value = (UrgencyTier.idle, "idle")

        mock_artifact = MagicMock()
        mock_artifact.suggested_next = "Continue work"
        mock_handoff.return_value = mock_artifact

        # Execute
        result = await step_morning_summary("planner-id", "impl-id", "reviewer-id", live=False)

        # Verify mock behavior
        assert result.passed
        assert result.label == "Morning fleet summary"

        # Verify cleanup was called
        assert mock_delete.call_count == 3


@pytest.mark.asyncio
async def test_step_morning_summary_live_mode_mock_report() -> None:
    """Test morning summary step with live=True but mocked report service."""
    with (
        patch("shoal.cli.demo.fleet.list_sessions") as mock_list,
        patch("shoal.cli.demo.fleet.delete_session") as _mock_delete,
        patch("shoal.cli.demo.fleet.read_journal") as mock_read,
        patch("shoal.cli.demo.fleet.generate_handoff") as mock_handoff,
        patch("shoal.cli.demo.fleet.derive_urgency") as mock_urgency,
    ):
        # Setup mocks
        from shoal.core.urgency import UrgencyTier

        mock_session1 = MagicMock()
        mock_session1.name = "fleet/planner"
        mock_session1.tags = ["planner", "fleet-demo"]
        mock_session1.status = "idle"

        mock_session2 = MagicMock()
        mock_session2.name = "fleet/implementer"
        mock_session2.tags = ["implementer", "fleet-demo"]
        mock_session2.status = "idle"

        mock_session3 = MagicMock()
        mock_session3.name = "fleet/reviewer"
        mock_session3.tags = ["reviewer", "fleet-demo"]
        mock_session3.status = "idle"

        mock_list.return_value = [mock_session1, mock_session2, mock_session3]
        mock_read.return_value = []
        mock_urgency.return_value = (UrgencyTier.idle, "idle")

        mock_artifact = MagicMock()
        mock_artifact.suggested_next = "Continue work"
        mock_handoff.return_value = mock_artifact

        with patch("shoal.services.report.generate_weekly_summary"):
            # Execute
            result = await step_morning_summary("planner-id", "impl-id", "reviewer-id", live=True)

            # Verify it completes even with live mode
            assert result.passed


@pytest.mark.asyncio
async def test_fleet_demo_flags_parsing() -> None:
    """Test that fleet_demo command accepts the new flags."""
    # This test just verifies the function signature accepts the new parameters
    # We won't actually run it, just check it can be called with the parameters
    import inspect

    from shoal.cli.demo.fleet import fleet_demo

    sig = inspect.signature(fleet_demo)
    params = list(sig.parameters.keys())

    assert "cleanup" in params
    assert "live" in params
    assert "interactive" in params


def test_interactive_mode_no_prompts_when_disabled() -> None:
    """Test that interactive=False runs without any user prompts."""
    # This is a smoke test to ensure the code path exists
    # The actual implementation tests are async and above
    # Just verify the function has the parameter
    import inspect

    from shoal.cli.demo.fleet import _fleet_impl

    sig = inspect.signature(_fleet_impl)
    params = list(sig.parameters.keys())

    assert "interactive" in params


def test_live_mode_flag_exists() -> None:
    """Test that live mode flag exists in implementation."""
    import inspect

    from shoal.cli.demo.fleet import _fleet_impl

    sig = inspect.signature(_fleet_impl)
    params = list(sig.parameters.keys())

    assert "live" in params
