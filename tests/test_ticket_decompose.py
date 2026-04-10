"""Tests for ticket decompose functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.services.linear_bridge import LinearBridge, LinearIssue


@pytest.fixture
def mock_parent_issue() -> LinearIssue:
    """Create a mock parent issue with structured description."""
    return LinearIssue(
        id="parent-uuid",
        identifier="AIA-123",
        title="Implement user authentication system",
        description="""## Implementation tasks

1. Set up OAuth provider integration
2. Create user session management
3. Implement JWT token validation

Additional notes:
- Use bcrypt for password hashing
- Add rate limiting for login attempts
""",
        team_id="team-uuid-123",
        state_name="Todo",
        state_type="unstarted",
        priority=1,
        url="https://linear.app/team/issue/AIA-123",
    )


@pytest.fixture
def mock_empty_description_issue() -> LinearIssue:
    """Create a mock issue with no description."""
    return LinearIssue(
        id="empty-uuid",
        identifier="AIA-456",
        title="Empty issue",
        description="",
        team_id="team-uuid-123",
        state_name="Todo",
        state_type="unstarted",
        priority=1,
        url="https://linear.app/team/issue/AIA-456",
    )


class TestLinearBridgeCreateIssue:
    """Test LinearBridge.create_issue method."""

    @pytest.mark.asyncio
    async def test_create_issue_success(self) -> None:
        """Test successful issue creation."""
        bridge = LinearBridge(api_key="test-key")

        mock_response = {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "new-issue-uuid",
                    "identifier": "AIA-124",
                    "title": "Set up OAuth provider integration",
                    "url": "https://linear.app/team/issue/AIA-124",
                },
            }
        }

        with patch.object(bridge, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await bridge.create_issue(
                team_id="team-uuid-123",
                title="Set up OAuth provider integration",
                description="Sub-task of parent issue",
                parent_id="parent-uuid",
                priority=3,
            )

            assert result["id"] == "new-issue-uuid"
            assert result["identifier"] == "AIA-124"
            assert result["title"] == "Set up OAuth provider integration"
            assert result["url"] == "https://linear.app/team/issue/AIA-124"

            # Verify mutation was called with correct input
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            variables = call_args[0][1]
            assert variables["input"]["teamId"] == "team-uuid-123"
            assert variables["input"]["title"] == "Set up OAuth provider integration"
            assert variables["input"]["parentId"] == "parent-uuid"
            assert variables["input"]["priority"] == 3

    @pytest.mark.asyncio
    async def test_create_issue_without_parent(self) -> None:
        """Test creating an issue without a parent."""
        bridge = LinearBridge(api_key="test-key")

        mock_response = {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "new-issue-uuid",
                    "identifier": "AIA-125",
                    "title": "Standalone issue",
                    "url": "https://linear.app/team/issue/AIA-125",
                },
            }
        }

        with patch.object(bridge, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await bridge.create_issue(
                team_id="team-uuid-123",
                title="Standalone issue",
                description="No parent",
            )

            assert result["identifier"] == "AIA-125"

            # Verify parentId was not included
            call_args = mock_post.call_args
            variables = call_args[0][1]
            assert "parentId" not in variables["input"]

    @pytest.mark.asyncio
    async def test_create_issue_failure(self) -> None:
        """Test handling of failed issue creation."""
        bridge = LinearBridge(api_key="test-key")

        mock_response = {
            "issueCreate": {
                "success": False,
            }
        }

        with patch.object(bridge, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError, match="Failed to create Linear issue"):
                await bridge.create_issue(
                    team_id="team-uuid-123",
                    title="Failing issue",
                    description="This should fail",
                )


class TestDecomposeCommand:
    """Test decompose CLI command."""

    @pytest.mark.asyncio
    async def test_decompose_dry_run(self, mock_parent_issue: LinearIssue) -> None:
        """Test decompose in dry-run mode displays proposals."""
        from shoal.cli.ticket import _ticket_decompose_impl

        with (
            patch("shoal.services.linear_bridge.get_linear_bridge") as mock_get_bridge,
            patch("shoal.cli.ticket.get_console") as mock_console,
        ):
            mock_bridge = MagicMock()
            mock_bridge.get_issue = AsyncMock(return_value=mock_parent_issue)
            mock_bridge.close = AsyncMock()
            mock_get_bridge.return_value = mock_bridge

            mock_console_instance = MagicMock()
            mock_console.return_value = mock_console_instance

            await _ticket_decompose_impl("AIA-123", count=3, dry_run=True)

            # Verify get_issue was called
            mock_bridge.get_issue.assert_called_once_with("AIA-123")

            # Verify create_issue was NOT called (dry-run)
            assert not hasattr(mock_bridge, "create_issue") or not mock_bridge.create_issue.called

            # Verify console output includes proposals
            assert mock_console_instance.print.called

    @pytest.mark.asyncio
    async def test_decompose_live_mode(self, mock_parent_issue: LinearIssue) -> None:
        """Test decompose creates actual issues in live mode."""
        from shoal.cli.ticket import _ticket_decompose_impl

        with (
            patch("shoal.services.linear_bridge.get_linear_bridge") as mock_get_bridge,
            patch("shoal.cli.ticket.get_console") as mock_console,
        ):
            mock_bridge = MagicMock()
            mock_bridge.get_issue = AsyncMock(return_value=mock_parent_issue)
            mock_bridge.create_issue = AsyncMock(return_value={
                "id": "child-uuid",
                "identifier": "AIA-124",
                "title": "Set up OAuth provider integration",
                "url": "https://linear.app/team/issue/AIA-124",
            })
            mock_bridge.close = AsyncMock()
            mock_get_bridge.return_value = mock_bridge

            mock_console_instance = MagicMock()
            mock_console.return_value = mock_console_instance

            await _ticket_decompose_impl("AIA-123", count=3, dry_run=False)

            # Verify create_issue was called 3 times
            assert mock_bridge.create_issue.call_count == 3

            # Verify parent_id was passed
            for call in mock_bridge.create_issue.call_args_list:
                kwargs = call.kwargs
                assert kwargs["parent_id"] == "parent-uuid"
                assert kwargs["team_id"] == "team-uuid-123"

    @pytest.mark.asyncio
    async def test_decompose_empty_description(self, mock_empty_description_issue: LinearIssue) -> None:
        """Test decompose handles empty description gracefully."""
        import typer

        from shoal.cli.ticket import _ticket_decompose_impl

        with (
            patch("shoal.services.linear_bridge.get_linear_bridge") as mock_get_bridge,
            patch("shoal.cli.ticket.get_console") as mock_console,
            pytest.raises(typer.Exit) as exc_info,
        ):
            mock_bridge = MagicMock()
            mock_bridge.get_issue = AsyncMock(return_value=mock_empty_description_issue)
            mock_bridge.close = AsyncMock()
            mock_get_bridge.return_value = mock_bridge

            mock_console_instance = MagicMock()
            mock_console.return_value = mock_console_instance

            await _ticket_decompose_impl("AIA-456", count=3, dry_run=True)

        # Should exit with code 0 (graceful)
        assert exc_info.value.exit_code == 0

        # Should display helpful message
        console_calls = [str(call) for call in mock_console_instance.print.call_args_list]
        assert any("No child issues could be generated" in str(call) for call in console_calls)

    @pytest.mark.asyncio
    async def test_decompose_nonexistent_issue(self) -> None:
        """Test decompose handles nonexistent issue."""
        import typer

        from shoal.cli.ticket import _ticket_decompose_impl

        with (
            patch("shoal.services.linear_bridge.get_linear_bridge") as mock_get_bridge,
            patch("shoal.cli.ticket.get_console") as mock_console,
            pytest.raises(typer.Exit) as exc_info,
        ):
            mock_bridge = MagicMock()
            mock_bridge.get_issue = AsyncMock(return_value=None)
            mock_bridge.close = AsyncMock()
            mock_get_bridge.return_value = mock_bridge

            mock_console_instance = MagicMock()
            mock_console.return_value = mock_console_instance

            await _ticket_decompose_impl("FAKE-999", count=3, dry_run=True)

        # Should exit with code 1 (error)
        assert exc_info.value.exit_code == 1


class TestParseChildProposals:
    """Test _parse_child_proposals helper."""

    def test_parse_numbered_list(self) -> None:
        """Test parsing numbered list items."""
        from shoal.cli.ticket import _parse_child_proposals

        description = """
1. First task
2. Second task
3. Third task
"""
        proposals = _parse_child_proposals(description, count=3, parent_title="Parent")

        assert len(proposals) == 3
        assert proposals[0]["title"] == "First task"
        assert proposals[1]["title"] == "Second task"
        assert proposals[2]["title"] == "Third task"
        assert all("Sub-task of Parent" in str(p["description"]) for p in proposals)

    def test_parse_bullet_points(self) -> None:
        """Test parsing bullet point items."""
        from shoal.cli.ticket import _parse_child_proposals

        description = """
- Task with dash
* Task with asterisk
• Task with bullet
"""
        proposals = _parse_child_proposals(description, count=3, parent_title="Parent")

        assert len(proposals) == 3
        assert proposals[0]["title"] == "Task with dash"
        assert proposals[1]["title"] == "Task with asterisk"
        assert proposals[2]["title"] == "Task with bullet"

    def test_parse_headings(self) -> None:
        """Test parsing heading items."""
        from shoal.cli.ticket import _parse_child_proposals

        description = """
## First heading
### Second heading
## Third heading
"""
        proposals = _parse_child_proposals(description, count=3, parent_title="Parent")

        assert len(proposals) == 3
        assert proposals[0]["title"] == "First heading"
        assert proposals[1]["title"] == "Second heading"
        assert proposals[2]["title"] == "Third heading"

    def test_parse_mixed_formats(self) -> None:
        """Test parsing with mixed formats prefers numbered lists."""
        from shoal.cli.ticket import _parse_child_proposals

        description = """
1. Numbered one
2. Numbered two
- Bullet point
## Heading
"""
        proposals = _parse_child_proposals(description, count=3, parent_title="Parent")

        # Should get 2 numbered + 1 bullet (since count=3)
        assert len(proposals) == 3
        assert proposals[0]["title"] == "Numbered one"
        assert proposals[1]["title"] == "Numbered two"
        assert proposals[2]["title"] == "Bullet point"

    def test_parse_empty_description(self) -> None:
        """Test parsing empty description returns empty list."""
        from shoal.cli.ticket import _parse_child_proposals

        proposals = _parse_child_proposals("", count=3, parent_title="Parent")
        assert proposals == []

    def test_parse_respects_count_limit(self) -> None:
        """Test that count parameter limits results."""
        from shoal.cli.ticket import _parse_child_proposals

        description = """
1. First
2. Second
3. Third
4. Fourth
5. Fifth
"""
        proposals = _parse_child_proposals(description, count=2, parent_title="Parent")

        assert len(proposals) == 2
        assert proposals[0]["title"] == "First"
        assert proposals[1]["title"] == "Second"

    def test_parse_default_priority(self) -> None:
        """Test that proposals have default priority."""
        from shoal.cli.ticket import _parse_child_proposals

        description = "1. Task one"
        proposals = _parse_child_proposals(description, count=1, parent_title="Parent")

        assert proposals[0]["priority"] == 3  # Medium priority
