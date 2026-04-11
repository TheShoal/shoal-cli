"""Tests for branch_status and merge_branch MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastmcp")
from fastmcp.exceptions import ToolError

from shoal.models.state import SessionState, SessionStatus


def _make_session(name: str = "worker", worktree: str = "/repo/.worktrees/worker") -> SessionState:
    return SessionState(
        id="abc123",
        name=name,
        tool="pi",
        path="/repo",
        tmux_session=f"_{name}",
        status=SessionStatus.running,
        worktree=worktree,
    )


# ---------------------------------------------------------------------------
# branch_status_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_status_tool_session_not_found() -> None:
    from shoal.services.mcp_shoal_server import branch_status_tool

    with patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ToolError, match="Session not found"):
            await branch_status_tool("nonexistent")


@pytest.mark.asyncio
async def test_branch_status_tool_no_worktree() -> None:
    from shoal.services.mcp_shoal_server import branch_status_tool

    session = _make_session(worktree="")
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
    ):
        with pytest.raises(ToolError, match="no worktree"):
            await branch_status_tool("worker")


@pytest.mark.asyncio
async def test_branch_status_tool_returns_git_info() -> None:
    from shoal.services.mcp_shoal_server import branch_status_tool

    session = _make_session()
    expected = {
        "branch": "feat/my-feature",
        "ahead": 3,
        "behind": 0,
        "dirty": False,
        "last_commit_sha": "deadbeef",
        "last_commit_msg": "feat: add thing",
    }
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
        patch(
            "shoal.services.mcp_shoal_server.git_tools.branch_status",
            new_callable=AsyncMock,
            return_value=expected,
        ),
    ):
        result = await branch_status_tool("worker")

    assert result == expected


# ---------------------------------------------------------------------------
# merge_branch_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_branch_tool_session_not_found() -> None:
    from shoal.services.mcp_shoal_server import merge_branch_tool

    with patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ToolError, match="Session not found"):
            await merge_branch_tool("nonexistent", "main")


@pytest.mark.asyncio
async def test_merge_branch_tool_no_worktree() -> None:
    from shoal.services.mcp_shoal_server import merge_branch_tool

    session = _make_session(worktree="")
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
    ):
        with pytest.raises(ToolError, match="no worktree"):
            await merge_branch_tool("worker", "main")


@pytest.mark.asyncio
async def test_merge_branch_tool_invalid_strategy() -> None:
    from shoal.services.mcp_shoal_server import merge_branch_tool

    session = _make_session()
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
    ):
        with pytest.raises(ToolError, match="Invalid strategy"):
            await merge_branch_tool("worker", "main", strategy="rebase")


@pytest.mark.asyncio
async def test_merge_branch_tool_success() -> None:
    from shoal.services.mcp_shoal_server import merge_branch_tool

    session = _make_session()
    merge_result = {"success": True, "conflicts": False, "merge_commit_sha": "abc123"}
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
        patch(
            "shoal.services.mcp_shoal_server.git_tools.merge_branch",
            new_callable=AsyncMock,
            return_value=merge_result,
        ),
    ):
        result = await merge_branch_tool("worker", "main")

    assert result["success"] is True
    assert result["merge_commit_sha"] == "abc123"


@pytest.mark.asyncio
async def test_merge_branch_tool_squash_strategy_passed_through() -> None:
    from shoal.services.mcp_shoal_server import merge_branch_tool

    session = _make_session()
    merge_result = {"success": True, "conflicts": False, "merge_commit_sha": "squashsha"}
    mock_merge = AsyncMock(return_value=merge_result)
    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
        patch("shoal.services.mcp_shoal_server.git_tools.merge_branch", mock_merge),
    ):
        await merge_branch_tool("worker", "main", strategy="squash")

    mock_merge.assert_called_once_with(session.worktree, "main", strategy="squash")
