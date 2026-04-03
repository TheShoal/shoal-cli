"""Tests for the Linear bridge service."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from shoal.services.linear_bridge import (
    LinearBridge,
    LinearIssue,
    LinearNamedTarget,
    get_linear_bridge,
)


def _mock_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=httpx.Response)
    response.json.return_value = payload
    response.raise_for_status = Mock()
    return response


class TestLinearIssueModel:
    def test_defaults(self) -> None:
        issue = LinearIssue()
        assert issue.id == ""
        assert issue.identifier == ""
        assert issue.title == ""
        assert issue.priority == 0
        assert issue.labels == []

    def test_full(self) -> None:
        issue = LinearIssue(
            id="abc-123",
            identifier="BE-1234",
            title="Fix auth bug",
            description="Long desc",
            state_name="In Progress",
            state_type="started",
            priority=1,
            assignee_name="Ricardo",
            branch_name="ricardo/be-1234",
            url="https://linear.app/usm/issue/BE-1234",
            labels=["bug", "auth"],
        )
        assert issue.identifier == "BE-1234"
        assert issue.priority == 1
        assert len(issue.labels) == 2


class TestGetLinearBridge:
    def test_missing_key_raises(self) -> None:
        with patch.dict(os.environ, {"SHOAL_LINEAR_API_KEY": ""}):
            with pytest.raises(RuntimeError, match="SHOAL_LINEAR_API_KEY"):
                get_linear_bridge()

    def test_whitespace_key_raises(self) -> None:
        with patch.dict(os.environ, {"SHOAL_LINEAR_API_KEY": "   "}):
            with pytest.raises(RuntimeError, match="SHOAL_LINEAR_API_KEY"):
                get_linear_bridge()

    def test_valid_key(self) -> None:
        with patch.dict(os.environ, {"SHOAL_LINEAR_API_KEY": "lin_api_test123"}):
            bridge = get_linear_bridge()
            assert isinstance(bridge, LinearBridge)


class TestLinearBridgeParseIssue:
    def test_parse_full_node(self) -> None:
        bridge = LinearBridge(api_key="test")
        node: dict[str, Any] = {
            "id": "uuid-1",
            "identifier": "BE-42",
            "title": "Fix bug",
            "description": "Detailed desc",
            "url": "https://linear.app/usm/issue/BE-42",
            "priority": 2,
            "branchName": "ricardo/be-42",
            "state": {"name": "In Progress", "type": "started"},
            "assignee": {"name": "Ricardo"},
            "labels": {"nodes": [{"name": "bug"}, {"name": "auth"}]},
        }
        issue = bridge._parse_issue(node)
        assert issue.identifier == "BE-42"
        assert issue.state_name == "In Progress"
        assert issue.state_type == "started"
        assert issue.assignee_name == "Ricardo"
        assert issue.branch_name == "ricardo/be-42"
        assert issue.labels == ["bug", "auth"]

    def test_parse_minimal_node(self) -> None:
        bridge = LinearBridge(api_key="test")
        node: dict[str, Any] = {
            "id": "uuid-2",
            "identifier": "FE-1",
            "title": "Add button",
        }
        issue = bridge._parse_issue(node)
        assert issue.identifier == "FE-1"
        assert issue.state_name == ""
        assert issue.assignee_name == ""
        assert issue.labels == []


class TestLinearBridgeListTeamIssues:
    @pytest.mark.asyncio
    async def test_list_returns_issues(self) -> None:
        bridge = LinearBridge(api_key="test")
        response_data = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "BE-1",
                            "title": "Task 1",
                            "description": "",
                            "url": "",
                            "priority": 1,
                            "branchName": "",
                            "state": {"name": "Todo", "type": "unstarted"},
                            "assignee": None,
                            "labels": {"nodes": []},
                        }
                    ]
                }
            }
        }
        mock_response = _mock_response(response_data)

        with patch.object(bridge, "_ensure_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            issues = await bridge.list_team_issues("BE")
            assert len(issues) == 1
            assert issues[0].identifier == "BE-1"

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        bridge = LinearBridge(api_key="test")
        mock_response = _mock_response({"data": {"issues": {"nodes": []}}})

        with patch.object(bridge, "_ensure_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            issues = await bridge.list_team_issues("BE")
            assert issues == []

    @pytest.mark.asyncio
    async def test_graphql_error_raises(self) -> None:
        bridge = LinearBridge(api_key="test")
        mock_response = _mock_response({"errors": [{"message": "Team not found"}]})

        with patch.object(bridge, "_ensure_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            with pytest.raises(RuntimeError, match="Team not found"):
                await bridge.list_team_issues("INVALID")


class TestLinearBridgeStatusUpdates:
    @pytest.mark.asyncio
    async def test_resolve_project_target_by_slug(self) -> None:
        bridge = LinearBridge(api_key="test")
        mock_response = _mock_response(
            {
                "data": {
                    "projects": {
                        "nodes": [
                            {
                                "id": "proj-1",
                                "name": "Backend Platform",
                                "slugId": "backend-platform",
                                "url": "https://linear.app/project/backend-platform",
                            }
                        ]
                    }
                }
            }
        )

        with patch.object(bridge, "_ensure_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            target = await bridge.resolve_target(kind="project", slug="backend-platform")

        assert target == LinearNamedTarget(
            kind="project",
            id="proj-1",
            name="Backend Platform",
            slug="backend-platform",
            url="https://linear.app/project/backend-platform",
        )

    @pytest.mark.asyncio
    async def test_create_project_status_update(self) -> None:
        bridge = LinearBridge(api_key="test")
        mock_response = _mock_response(
            {
                "data": {
                    "projectUpdateCreate": {
                        "success": True,
                        "projectUpdate": {
                            "id": "upd-1",
                            "url": "https://linear.app/update/upd-1",
                        },
                    }
                }
            }
        )

        with patch.object(bridge, "_ensure_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            update = await bridge.create_status_update(
                kind="project",
                target_id="proj-1",
                body="# Sprint Summary",
                health="onTrack",
            )

        assert update.kind == "project"
        assert update.id == "upd-1"
        assert update.url == "https://linear.app/update/upd-1"
        assert update.health == "onTrack"


class TestHookLinearOnComplete:
    @pytest.mark.asyncio
    async def test_skips_without_api_key(self) -> None:
        """Hook is a no-op when no API key is set."""
        from shoal.services.linear_bridge import hook_linear_on_complete

        session = type("FakeSession", (), {"tags": ["linear:BE-42"]})()
        with patch.dict(os.environ, {"SHOAL_LINEAR_API_KEY": ""}):
            await hook_linear_on_complete(session=session)

    @pytest.mark.asyncio
    async def test_skips_without_linear_tag(self) -> None:
        """Hook is a no-op when session has no linear: tags."""
        from shoal.services.linear_bridge import hook_linear_on_complete

        session = type("FakeSession", (), {"tags": ["other:tag"]})()
        with patch.dict(os.environ, {"SHOAL_LINEAR_API_KEY": "lin_test"}):
            await hook_linear_on_complete(session=session)

    @pytest.mark.asyncio
    async def test_skips_without_session(self) -> None:
        """Hook is a no-op when no session kwarg is passed."""
        from shoal.services.linear_bridge import hook_linear_on_complete

        await hook_linear_on_complete()
