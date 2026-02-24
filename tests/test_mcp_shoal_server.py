"""Tests for services.mcp_shoal_server module."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from shoal.models.state import SessionState, SessionStatus


def _make_session(
    name: str = "test-session",
    tool: str = "claude",
    status: SessionStatus = SessionStatus.running,
    session_id: str = "abc12345",
    worktree: str = "",
    branch: str = "main",
    mcp_servers: list[str] | None = None,
    pid: int | None = 42,
) -> SessionState:
    now = datetime.now(UTC)
    return SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path="/tmp/project",
        worktree=worktree,
        branch=branch,
        tmux_session=f"_{name}",
        tmux_session_id="$1",
        tmux_window="@0",
        nvim_socket="",
        status=status,
        pid=pid,
        mcp_servers=mcp_servers or [],
        created_at=now,
        last_activity=now,
    )


# ---------------------------------------------------------------------------
# Import / instantiation tests
# ---------------------------------------------------------------------------


def test_import() -> None:
    """Module can be imported without errors."""
    from shoal.services import mcp_shoal_server  # noqa: F401


def test_server_name() -> None:
    """FastMCP server has correct name."""
    from shoal.services.mcp_shoal_server import mcp

    assert mcp.name == "shoal-orchestrator"


def test_main_exists() -> None:
    """Entry point function exists and is callable."""
    from shoal.services.mcp_shoal_server import main

    assert callable(main)


def test_auto_enter_tools() -> None:
    """CLI tools are in the auto-enter set, TUI tools are not."""
    from shoal.services.mcp_shoal_server import _AUTO_ENTER_TOOLS

    assert "claude" in _AUTO_ENTER_TOOLS
    assert "gemini" in _AUTO_ENTER_TOOLS
    assert "pi" in _AUTO_ENTER_TOOLS
    assert "opencode" not in _AUTO_ENTER_TOOLS


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


async def test_list_sessions_empty() -> None:
    from shoal.services.mcp_shoal_server import list_sessions_tool

    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[]):
        result = await list_sessions_tool()

    assert result == []


async def test_list_sessions_multiple() -> None:
    from shoal.services.mcp_shoal_server import list_sessions_tool

    sessions = [
        _make_session(name="s1", session_id="aaa", status=SessionStatus.running),
        _make_session(name="s2", session_id="bbb", status=SessionStatus.waiting, tool="opencode"),
        _make_session(name="s3", session_id="ccc", status=SessionStatus.error),
    ]
    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=sessions):
        result = await list_sessions_tool()

    assert len(result) == 3
    assert result[0]["name"] == "s1"
    assert result[0]["status"] == "running"
    assert result[1]["tool"] == "opencode"
    assert result[2]["status"] == "error"


async def test_list_sessions_fields() -> None:
    from shoal.services.mcp_shoal_server import list_sessions_tool

    s = _make_session(
        mcp_servers=["memory", "github"],
        worktree="/tmp/wt",
        branch="feat/test",
    )
    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[s]):
        result = await list_sessions_tool()

    item = result[0]
    assert set(item.keys()) == {
        "id",
        "name",
        "tool",
        "status",
        "path",
        "branch",
        "worktree",
        "mcp_servers",
    }
    assert item["mcp_servers"] == ["memory", "github"]
    assert item["branch"] == "feat/test"


# ---------------------------------------------------------------------------
# session_status
# ---------------------------------------------------------------------------


async def test_session_status_empty() -> None:
    from shoal.services.mcp_shoal_server import session_status_tool

    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[]):
        result = await session_status_tool()

    assert result["total"] == 0
    assert result["running"] == 0


async def test_session_status_mixed() -> None:
    from shoal.services.mcp_shoal_server import session_status_tool

    sessions = [
        _make_session(session_id="a", status=SessionStatus.running),
        _make_session(session_id="b", status=SessionStatus.running),
        _make_session(session_id="c", status=SessionStatus.waiting),
        _make_session(session_id="d", status=SessionStatus.error),
        _make_session(session_id="e", status=SessionStatus.idle),
    ]
    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=sessions):
        result = await session_status_tool()

    assert result["total"] == 5
    assert result["running"] == 2
    assert result["waiting"] == 1
    assert result["error"] == 1
    assert result["idle"] == 1
    assert result["stopped"] == 0


# ---------------------------------------------------------------------------
# session_info
# ---------------------------------------------------------------------------


async def test_session_info_found() -> None:
    from shoal.services.mcp_shoal_server import session_info_tool

    s = _make_session(name="worker-1", mcp_servers=["memory"])
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
    ):
        result = await session_info_tool(session="worker-1")

    assert result["name"] == "worker-1"
    assert result["id"] == "abc12345"
    assert result["mcp_servers"] == ["memory"]
    assert "created_at" in result
    assert "last_activity" in result
    assert "tmux_session" in result


async def test_session_info_not_found() -> None:
    from shoal.services.mcp_shoal_server import session_info_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await session_info_tool(session="nonexistent")


async def test_session_info_resolve_then_missing() -> None:
    """resolve_session finds ID but get_session returns None (race condition)."""
    from shoal.services.mcp_shoal_server import session_info_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await session_info_tool(session="worker-1")


# ---------------------------------------------------------------------------
# send_keys
# ---------------------------------------------------------------------------


async def test_send_keys_claude_auto_enter() -> None:
    """Claude (CLI tool) gets auto-enter by default."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-1", tool="claude")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-1", keys="y")

    assert "worker-1" in result["message"]
    mock_send.assert_called_once_with("_worker-1", "y", enter=True)


async def test_send_keys_opencode_no_auto_enter() -> None:
    """OpenCode (TUI tool) does not get auto-enter by default."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-2", tool="opencode", session_id="def67890")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="def67890"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-2", keys="y")

    assert "worker-2" in result["message"]
    mock_send.assert_called_once_with("_worker-2", "y", enter=False)


async def test_send_keys_explicit_enter_override() -> None:
    """Explicit enter parameter overrides tool-based auto-detection."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-3", tool="opencode", session_id="ghi11111")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="ghi11111"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-3", keys="y", enter=True)

    assert "worker-3" in result["message"]
    mock_send.assert_called_once_with("_worker-3", "y", enter=True)


async def test_send_keys_not_found() -> None:
    from shoal.services.mcp_shoal_server import send_keys_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await send_keys_tool(session="ghost", keys="y")


# ---------------------------------------------------------------------------
# kill_session
# ---------------------------------------------------------------------------


async def test_kill_session_success() -> None:
    from shoal.services.mcp_shoal_server import kill_session_tool

    s = _make_session(name="worker-1")
    summary = {
        "tmux_killed": True,
        "worktree_removed": False,
        "branch_deleted": False,
        "db_deleted": True,
        "journal_archived": False,
    }
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.services.lifecycle.kill_session_lifecycle",
            new_callable=AsyncMock,
            return_value=summary,
        ) as mock_kill,
    ):
        result = await kill_session_tool(session="worker-1")

    assert result["session"] == "worker-1"
    assert result["tmux_killed"] is True
    assert result["db_deleted"] is True
    mock_kill.assert_called_once_with(
        session_id="abc12345",
        tmux_session="_worker-1",
        worktree="",
        git_root="/tmp/project",
        branch="main",
        remove_worktree=False,
        force=False,
    )


async def test_kill_session_not_found() -> None:
    from shoal.services.mcp_shoal_server import kill_session_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await kill_session_tool(session="ghost")


async def test_kill_session_dirty_worktree() -> None:
    from shoal.services.lifecycle import DirtyWorktreeError
    from shoal.services.mcp_shoal_server import kill_session_tool

    s = _make_session(name="worker-1", worktree="/tmp/wt")
    err = DirtyWorktreeError(
        "Worktree dirty", session_id="abc12345", dirty_files="file1.py, file2.py"
    )
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.services.lifecycle.kill_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=err,
        ),
        pytest.raises(ToolError, match="uncommitted changes"),
    ):
        await kill_session_tool(session="worker-1")


async def test_kill_session_with_force() -> None:
    from shoal.services.mcp_shoal_server import kill_session_tool

    s = _make_session(name="worker-1", worktree="/tmp/wt")
    summary = {
        "tmux_killed": True,
        "worktree_removed": True,
        "branch_deleted": True,
        "db_deleted": True,
        "journal_archived": False,
    }
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.services.lifecycle.kill_session_lifecycle",
            new_callable=AsyncMock,
            return_value=summary,
        ) as mock_kill,
    ):
        result = await kill_session_tool(session="worker-1", remove_worktree=True, force=True)

    assert result["worktree_removed"] is True
    mock_kill.assert_called_once_with(
        session_id="abc12345",
        tmux_session="_worker-1",
        worktree="/tmp/wt",
        git_root="/tmp/project",
        branch="main",
        remove_worktree=True,
        force=True,
    )


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


def _mock_create_deps(
    *,
    is_git_repo: bool = True,
    git_root: str = "/tmp/project",
    current_branch: str = "main",
    find_by_name: str | None = None,
) -> dict[str, AbstractContextManager[object]]:
    """Return a dict of patch context managers for create_session_tool deps."""
    session = _make_session(name="new-session", session_id="new12345")
    return {
        "git_repo": patch("shoal.core.git.is_git_repo", return_value=is_git_repo),
        "git_root": patch("shoal.core.git.git_root", return_value=git_root),
        "branch": patch("shoal.core.git.current_branch", return_value=current_branch),
        "ensure": patch("shoal.core.config.ensure_dirs"),
        "config": patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="opencode"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        "tool_cfg": patch(
            "shoal.core.config.load_tool_config",
            return_value=MagicMock(command="claude"),
        ),
        "find": patch(
            "shoal.core.state.find_by_name",
            new_callable=AsyncMock,
            return_value=find_by_name,
        ),
        "lifecycle": patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ),
    }


async def test_create_session_success() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps()
    with (
        mocks["git_repo"],
        mocks["git_root"],
        mocks["branch"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find"],
        mocks["lifecycle"] as mock_create,
    ):
        result = await create_session_tool(name="new-session", path="/tmp/project")

    assert result["name"] == "new-session"
    assert result["id"] == "new12345"
    mock_create.assert_called_once()  # type: ignore[attr-defined]
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    assert call_kwargs["session_name"] == "new-session"
    assert call_kwargs["git_root"] == "/tmp/project"


async def test_create_session_not_git_repo() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps(is_git_repo=False)
    with (
        mocks["git_repo"],
        mocks["ensure"],
        mocks["config"],
        pytest.raises(ToolError, match="Not a git repository"),
    ):
        await create_session_tool(name="test", path="/tmp/not-a-repo")


async def test_create_session_unknown_tool() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps()
    with (
        mocks["git_repo"],
        mocks["ensure"],
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(general=MagicMock(default_tool="opencode")),
        ),
        patch("shoal.core.config.load_tool_config", side_effect=FileNotFoundError),
        pytest.raises(ToolError, match="Unknown tool"),
    ):
        await create_session_tool(name="test", tool="badtool")


async def test_create_session_name_collision() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps(find_by_name="existing123")
    with (
        mocks["git_repo"],
        mocks["git_root"],
        mocks["branch"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find"],
        pytest.raises(ToolError, match="already exists"),
    ):
        await create_session_tool(name="taken", path="/tmp/project")


async def test_create_session_exists_error() -> None:
    from shoal.services.lifecycle import SessionExistsError
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps()
    err = SessionExistsError("Session exists", session_id="x")
    with (
        mocks["git_repo"],
        mocks["git_root"],
        mocks["branch"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find"],
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=err,
        ),
        pytest.raises(ToolError, match="Session exists"),
    ):
        await create_session_tool(name="dup", path="/tmp/project")


async def test_create_session_tmux_error() -> None:
    from shoal.services.lifecycle import TmuxSetupError
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps()
    err = TmuxSetupError("tmux failed", session_id="x")
    with (
        mocks["git_repo"],
        mocks["git_root"],
        mocks["branch"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find"],
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=err,
        ),
        pytest.raises(ToolError, match="Failed to create tmux session"),
    ):
        await create_session_tool(name="fail", path="/tmp/project")


async def test_create_session_with_template() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    template = MagicMock(tool="claude", mcp=["memory"])
    mocks = _mock_create_deps()
    with (
        mocks["git_repo"],
        mocks["git_root"],
        mocks["branch"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find"],
        mocks["lifecycle"] as mock_create,
        patch("shoal.core.config.load_template", return_value=template),
    ):
        result = await create_session_tool(
            name="new-session", path="/tmp/project", template="my-template"
        )

    assert result["name"] == "new-session"
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    assert call_kwargs["template_cfg"] == template
    assert "memory" in call_kwargs["mcp_servers"]


async def test_create_session_template_not_found() -> None:
    from shoal.services.mcp_shoal_server import create_session_tool

    mocks = _mock_create_deps()
    with (
        mocks["git_repo"],
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        patch("shoal.core.config.load_template", side_effect=FileNotFoundError),
        pytest.raises(ToolError, match="Template not found"),
    ):
        await create_session_tool(name="test", template="missing")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


async def test_lifespan_init_cleanup() -> None:
    from shoal.services.mcp_shoal_server import _lifespan

    mock_db = MagicMock()
    with (
        patch("shoal.core.config.ensure_dirs"),
        patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=mock_db),
        patch("shoal.core.db.ShoalDB.reset_instance", new_callable=AsyncMock) as mock_reset,
    ):
        async with _lifespan(None) as ctx:
            assert ctx == {}
        mock_reset.assert_called_once()
