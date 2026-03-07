"""Tests for services.mcp_shoal_server module."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from shoal.models.config import ToolConfig
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
    from shoal.services import mcp_shoal_server

    assert hasattr(mcp_shoal_server, "mcp")
    assert hasattr(mcp_shoal_server, "main")


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
    assert "codex" in _AUTO_ENTER_TOOLS
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
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%1",
        ) as mock_pane,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-1", keys="y")

    assert "worker-1" in result["message"]
    # Must target the titled pane, not just the session name
    mock_pane.assert_called_once_with("_worker-1", "shoal:abc12345")
    # Claude is a CLI tool → auto-enter=True
    mock_send.assert_called_once_with("%1", "y", enter=True, delay=0.0)


async def test_send_keys_codex_auto_enter() -> None:
    """Codex (CLI tool) gets auto-enter by default."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-codex", tool="codex", session_id="codex123")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="codex123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%3",
        ) as mock_pane,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-codex", keys="continue")

    assert "worker-codex" in result["message"]
    mock_pane.assert_called_once_with("_worker-codex", "shoal:codex123")
    mock_send.assert_called_once_with("%3", "continue", enter=True, delay=0.0)


async def test_send_keys_opencode_no_auto_enter() -> None:
    """OpenCode (TUI tool) does not get auto-enter by default."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-2", tool="opencode", session_id="def67890")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="def67890"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%2",
        ) as mock_pane,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-2", keys="y")

    assert "worker-2" in result["message"]
    mock_pane.assert_called_once_with("_worker-2", "shoal:def67890")
    mock_send.assert_called_once_with("%2", "y", enter=False, delay=0.0)


async def test_send_keys_explicit_enter_override() -> None:
    """Explicit enter parameter overrides tool-based auto-detection."""
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-3", tool="opencode", session_id="ghi11111")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="ghi11111"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%4",
        ) as mock_pane,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-3", keys="y", enter=True)

    assert "worker-3" in result["message"]
    mock_pane.assert_called_once_with("_worker-3", "shoal:ghi11111")
    mock_send.assert_called_once_with("%4", "y", enter=True, delay=0.0)


async def test_send_keys_not_found() -> None:
    from shoal.services.mcp_shoal_server import send_keys_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await send_keys_tool(session="ghost", keys="y")


# ---------------------------------------------------------------------------
# capture_pane
# ---------------------------------------------------------------------------


async def test_capture_pane_success() -> None:
    """capture_pane returns pane content for a valid session."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    s = _make_session(name="worker-1")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%1",
        ) as mock_pane,
        patch(
            "shoal.core.tmux.async_capture_pane",
            new_callable=AsyncMock,
            return_value="$ echo hello\nhello\n$",
        ) as mock_capture,
    ):
        result = await capture_pane_tool(session="worker-1")

    assert result["content"] == "$ echo hello\nhello\n$"
    mock_pane.assert_called_once_with("_worker-1", "shoal:abc12345")
    mock_capture.assert_called_once_with("%1", 20)


async def test_capture_pane_custom_lines() -> None:
    """capture_pane respects the lines parameter."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    s = _make_session(name="worker-1")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%1",
        ),
        patch(
            "shoal.core.tmux.async_capture_pane",
            new_callable=AsyncMock,
            return_value="output",
        ) as mock_capture,
    ):
        result = await capture_pane_tool(session="worker-1", lines=50)

    assert result["content"] == "output"
    mock_capture.assert_called_once_with("%1", 50)


async def test_capture_pane_not_found() -> None:
    """capture_pane raises ToolError for unknown session."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await capture_pane_tool(session="ghost")


async def test_capture_pane_resolve_then_missing() -> None:
    """capture_pane handles race where resolve succeeds but get returns None."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await capture_pane_tool(session="worker-1")


async def test_capture_pane_empty_output() -> None:
    """capture_pane returns empty string when pane has no output."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    s = _make_session(name="worker-1")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%1",
        ),
        patch(
            "shoal.core.tmux.async_capture_pane",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        result = await capture_pane_tool(session="worker-1")

    assert result["content"] == ""


# ---------------------------------------------------------------------------
# kill_session
# ---------------------------------------------------------------------------


async def test_send_keys_targets_shoal_pane() -> None:
    """send_keys uses preferred_pane to avoid landing in the wrong pane.

    Without preferred_pane, tmux targets the *active* pane which may not be
    the tool pane when the session has multiple panes (e.g. editor + terminal).
    """
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-2", session_id="deadbeef")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="deadbeef"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%3",
        ) as mock_pane,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await send_keys_tool(session="worker-2", keys="ls -la")

    # Pane title is "shoal:<session_id>" matching the Shoal pane identity contract
    mock_pane.assert_called_once_with("_worker-2", "shoal:deadbeef")
    # Keys go to the resolved pane ID, not the raw session name
    mock_send.assert_called_once_with("%3", "ls -la", enter=True, delay=0.0)
    assert result["message"] == "Keys sent to session 'worker-2'"


async def test_send_keys_delay_forwarded_from_tool_config() -> None:
    """send_keys_delay from tool config is forwarded to async_send_keys."""
    from shoal.models.config import ToolConfig
    from shoal.services.mcp_shoal_server import send_keys_tool

    s = _make_session(name="worker-slow", tool="claude", session_id="slow0001")
    slow_cfg = ToolConfig(name="claude", command="claude", send_keys_delay=0.1)
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="slow0001"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            return_value="%9",
        ),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
        patch("shoal.core.config.load_tool_config", return_value=slow_cfg),
    ):
        result = await send_keys_tool(session="worker-slow", keys="y")

    assert "worker-slow" in result["message"]
    mock_send.assert_called_once_with("%9", "y", enter=True, delay=0.1)


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
            return_value=ToolConfig(name="claude", command="claude", input_mode="keys"),
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


async def test_create_session_keys_prompt_uses_send_keys() -> None:
    """When input_mode='keys', prompt is delivered via send_keys after launch."""
    from shoal.services.mcp_shoal_server import create_session_tool

    session = _make_session(name="new-session", session_id="new12345")
    keys_tool_cfg = ToolConfig(name="pi", command="pi", input_mode="keys")
    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp/project"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="pi"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch("shoal.core.config.load_tool_config", return_value=keys_tool_cfg),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ) as mock_create,
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await create_session_tool(
            name="new-session", path="/tmp/project", prompt="do the thing"
        )

    assert result["name"] == "new-session"
    # tool_command passed to lifecycle should be the bare command (no prompt baked in)
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    assert call_kwargs["tool_command"] == "pi"
    # send_keys must have been called with the prompt
    mock_send.assert_called_once()
    assert mock_send.call_args.args[1] == "do the thing"


async def test_create_session_arg_mode_prompt_baked_into_command() -> None:
    """When input_mode='arg', prompt is baked into tool_command; send_keys skipped."""
    from shoal.services.mcp_shoal_server import create_session_tool

    session = _make_session(name="new-session", session_id="new12345")
    arg_tool_cfg = ToolConfig(name="claude", command="claude", input_mode="arg")
    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp/project"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="claude"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch("shoal.core.config.load_tool_config", return_value=arg_tool_cfg),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ) as mock_create,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await create_session_tool(
            name="new-session", path="/tmp/project", prompt="fix the issue"
        )

    assert result["name"] == "new-session"
    # Prompt must be baked into the launch command
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    assert "fix the issue" in call_kwargs["tool_command"]
    assert call_kwargs["tool_command"].startswith("claude")
    # send_keys must NOT have been called for native delivery
    mock_send.assert_not_called()


async def test_create_session_flag_mode_prompt_baked_into_command() -> None:
    """When input_mode='flag', prompt is baked via --prompt flag; send_keys skipped."""
    from shoal.services.mcp_shoal_server import create_session_tool

    session = _make_session(name="new-session", session_id="new12345")
    flag_tool_cfg = ToolConfig(
        name="opencode", command="opencode", input_mode="flag", prompt_flag="--prompt"
    )
    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp/project"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="opencode"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch("shoal.core.config.load_tool_config", return_value=flag_tool_cfg),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ) as mock_create,
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await create_session_tool(
            name="new-session", path="/tmp/project", prompt="write tests"
        )

    assert result["name"] == "new-session"
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    assert "--prompt" in call_kwargs["tool_command"]
    assert "write tests" in call_kwargs["tool_command"]
    mock_send.assert_not_called()


async def test_create_session_omp_prompt_written_to_file(tmp_path: Path) -> None:
    """omp (arg+prefix mode) writes prompt file and passes @/path in tool_command."""
    from shoal.services.mcp_shoal_server import create_session_tool

    session = _make_session(name="new-session", session_id="new12345")
    omp_tool_cfg = ToolConfig(name="omp", command="omp", input_mode="arg", prompt_file_prefix="@")
    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp/project"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="omp"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch("shoal.core.config.load_tool_config", return_value=omp_tool_cfg),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ) as mock_create,
        patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        result = await create_session_tool(
            name="new-session", path="/tmp/project", prompt="build the thing"
        )

    assert result["name"] == "new-session"
    call_kwargs = mock_create.call_args.kwargs  # type: ignore[attr-defined]
    tool_cmd = call_kwargs["tool_command"]
    assert tool_cmd.startswith("omp @")
    # The file referenced in the command should contain the prompt
    file_path = tool_cmd[len("omp @") :]
    assert Path(file_path).read_text(encoding="utf-8") == "build the thing"
    mock_send.assert_not_called()


async def test_create_session_no_prompt_no_send_keys() -> None:
    """When no prompt is given, send_keys is never called regardless of input_mode."""
    from shoal.services.mcp_shoal_server import create_session_tool

    session = _make_session(name="new-session", session_id="new12345")
    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp/project"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="pi"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch(
            "shoal.core.config.load_tool_config",
            return_value=ToolConfig(name="pi", command="pi", input_mode="keys"),
        ),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        patch(
            "shoal.services.lifecycle.create_session_lifecycle",
            new_callable=AsyncMock,
            return_value=session,
        ),
        patch("shoal.core.tmux.async_send_keys", new_callable=AsyncMock) as mock_send,
    ):
        await create_session_tool(name="new-session", path="/tmp/project")

    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# read_history
# ---------------------------------------------------------------------------


async def test_read_history_returns_transitions() -> None:
    """read_history returns status transition list from DB."""
    from shoal.services.mcp_shoal_server import read_history_tool

    transitions = [
        {
            "id": "t1",
            "session_id": "abc12345",
            "from_status": "idle",
            "to_status": "running",
            "timestamp": "2026-02-24T05:00:00+00:00",
            "pane_snapshot": None,
        },
    ]
    mock_db = MagicMock()
    mock_db.get_status_transitions = AsyncMock(return_value=transitions)
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=mock_db),
    ):
        result = await read_history_tool(session="worker-1", limit=10)

    assert len(result) == 1
    assert result[0]["from_status"] == "idle"
    assert result[0]["to_status"] == "running"
    mock_db.get_status_transitions.assert_called_once_with("abc12345", limit=10)


async def test_read_history_not_found() -> None:
    """read_history raises ToolError for unknown session."""
    from shoal.services.mcp_shoal_server import read_history_tool

    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Session not found"),
    ):
        await read_history_tool(session="nonexistent")


async def test_read_history_empty() -> None:
    """read_history returns empty list when no transitions exist."""
    from shoal.services.mcp_shoal_server import read_history_tool

    mock_db = MagicMock()
    mock_db.get_status_transitions = AsyncMock(return_value=[])
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=mock_db),
    ):
        result = await read_history_tool(session="worker-1")

    assert result == []


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


# ---------------------------------------------------------------------------
# async_wait_for_ready
# ---------------------------------------------------------------------------


async def test_async_wait_for_ready_detects_pattern() -> None:
    """Returns True when a busy_pattern appears in pane content."""
    from unittest.mock import patch

    from shoal.core.tmux import async_wait_for_ready
    from shoal.models.config import DetectionPatterns, ToolConfig

    cfg = ToolConfig(
        name="pi",
        command="pi",
        detection=DetectionPatterns(busy_patterns=[r"\$\s"]),
    )
    with patch("shoal.core.tmux.capture_pane", return_value="user@host:~$ ") as mock_cap:
        result = await async_wait_for_ready("test-session:0.0", cfg, timeout=1.0)

    assert result is True
    mock_cap.assert_called()


async def test_async_wait_for_ready_timeout() -> None:
    """Returns False after timeout when no pattern matches content."""
    from unittest.mock import patch

    from shoal.core.tmux import async_wait_for_ready
    from shoal.models.config import DetectionPatterns, ToolConfig

    cfg = ToolConfig(
        name="pi",
        command="pi",
        detection=DetectionPatterns(busy_patterns=["THIS_PATTERN_NEVER_MATCHES_XYZ"]),
    )
    with patch("shoal.core.tmux.capture_pane", return_value="launching..."):
        result = await async_wait_for_ready(
            "test-session:0.0", cfg, timeout=0.2, poll_interval=0.05
        )

    assert result is False


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------


async def test_capture_pane_batch_returns_results_dict() -> None:
    """Batch capture_pane with a list of sessions returns {results: {name: data}}."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    s1 = _make_session(name="alpha", session_id="id1")
    s2 = _make_session(name="beta", session_id="id2")
    with (
        patch(
            "shoal.core.state.resolve_session",
            new_callable=AsyncMock,
            side_effect=["id1", "id2"],
        ),
        patch(
            "shoal.core.state.get_session",
            new_callable=AsyncMock,
            side_effect=[s1, s2],
        ),
        patch(
            "shoal.core.tmux.async_preferred_pane",
            new_callable=AsyncMock,
            side_effect=["%1", "%2"],
        ),
        patch(
            "shoal.core.tmux.async_capture_pane",
            new_callable=AsyncMock,
            side_effect=["output-alpha", "output-beta"],
        ),
    ):
        result = await capture_pane_tool(session=["alpha", "beta"])

    assert "results" in result
    assert result["results"]["alpha"] == {"content": "output-alpha"}
    assert result["results"]["beta"] == {"content": "output-beta"}


async def test_capture_pane_single_backwards_compat() -> None:
    """Single string input returns same shape as before — no 'results' wrapper."""
    from shoal.services.mcp_shoal_server import capture_pane_tool

    s = _make_session(name="worker-1")
    with (
        patch("shoal.core.state.resolve_session", new_callable=AsyncMock, return_value="abc12345"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=s),
        patch("shoal.core.tmux.async_preferred_pane", new_callable=AsyncMock, return_value="%1"),
        patch("shoal.core.tmux.async_capture_pane", new_callable=AsyncMock, return_value="hello"),
    ):
        result = await capture_pane_tool(session="worker-1")

    assert result == {"content": "hello"}
    assert "results" not in result


async def test_kill_session_batch_kills_all() -> None:
    """Batch kill_session with a list kills all named sessions."""
    from shoal.services.mcp_shoal_server import kill_session_tool

    s1 = _make_session(name="alpha", session_id="id1")
    s2 = _make_session(name="beta", session_id="id2")
    summary = {
        "tmux_killed": True,
        "worktree_removed": False,
        "branch_deleted": False,
        "db_deleted": True,
        "journal_archived": False,
    }
    with (
        patch(
            "shoal.core.state.resolve_session",
            new_callable=AsyncMock,
            side_effect=["id1", "id2"],
        ),
        patch(
            "shoal.core.state.get_session",
            new_callable=AsyncMock,
            side_effect=[s1, s2],
        ),
        patch(
            "shoal.services.lifecycle.kill_session_lifecycle",
            new_callable=AsyncMock,
            return_value=summary,
        ) as mock_kill,
    ):
        result = await kill_session_tool(session=["alpha", "beta"])

    assert "results" in result
    assert result["results"]["alpha"]["session"] == "alpha"
    assert result["results"]["beta"]["session"] == "beta"
    assert mock_kill.call_count == 2
