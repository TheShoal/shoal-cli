"""Tests for fork_session, spawn_team, and wait_for_team MCP tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastmcp")
from fastmcp.exceptions import ToolError

from shoal.models.config import ToolConfig
from shoal.models.state import SessionState, SessionStatus


def _make_session(
    name: str = "coordinator",
    tool: str = "omp",
    status: SessionStatus = SessionStatus.running,
    session_id: str = "coord123",
    path: str = "/tmp/project",
    worktree: str = "",
    branch: str = "main",
    parent_id: str = "",
    completed_at: datetime | None = None,
) -> SessionState:
    now = datetime.now(UTC)
    return SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path=path,
        worktree=worktree,
        branch=branch,
        tmux_session=f"_{name}",
        tmux_session_id="$1",
        tmux_window="@0",
        nvim_socket="",
        status=status,
        parent_id=parent_id,
        created_at=now,
        last_activity=now,
        completed_at=completed_at,
    )


def _mock_fork_deps(
    source_session: SessionState | None = None,
    worker_session: SessionState | None = None,
) -> dict[str, object]:
    """Shared patch targets for fork_session and spawn_team tests."""
    src = source_session or _make_session(name="coordinator", session_id="coord123")
    worker = worker_session or _make_session(
        name="worker-a",
        session_id="work123",
        path="/tmp/project",
        worktree="/tmp/project/.worktrees/worker-a",
        branch="feat/worker-a",
        parent_id="coord123",
    )
    return {
        "ensure": patch("shoal.core.config.ensure_dirs"),
        "config": patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="omp"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        "tool_cfg": patch(
            "shoal.core.config.load_tool_config",
            return_value=ToolConfig(name="omp", command="omp", input_mode="keys"),
        ),
        "find_by_name": patch(
            "shoal.core.state.find_by_name",
            new_callable=AsyncMock,
            return_value=src.id,
        ),
        "get_session": patch(
            "shoal.core.state.get_session",
            new_callable=AsyncMock,
            return_value=src,
        ),
        "mkdir": patch("pathlib.Path.mkdir"),
        "worktree_add": patch("shoal.core.git.worktree_add"),
        "infer_branch": patch(
            "shoal.core.git.infer_branch_name",
            return_value="feat/worker-a",
        ),
        "lifecycle": patch(
            "shoal.services.lifecycle.fork_session_lifecycle",
            new_callable=AsyncMock,
            return_value=worker,
        ),
    }


# ---------------------------------------------------------------------------
# fork_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fork_session_tool_success() -> None:
    """Happy path: fork returns expected dict with parent_id."""
    from shoal.services.mcp_shoal_server import fork_session_tool

    mocks = _mock_fork_deps()
    with (
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find_by_name"],
        mocks["get_session"],
        mocks["mkdir"],
        mocks["worktree_add"],
        mocks["infer_branch"],
        mocks["lifecycle"] as mock_fork,
    ):
        result = await fork_session_tool(source="coordinator", name="worker-a")

    assert result["name"] == "worker-a"
    assert result["id"] == "work123"
    assert result["parent_id"] == "coord123"
    assert result["branch"] == "feat/worker-a"
    mock_fork.assert_called_once()  # type: ignore[attr-defined]
    call_kw = mock_fork.call_args.kwargs  # type: ignore[attr-defined]
    assert call_kw["session_name"] == "worker-a"
    assert call_kw["parent_id"] == "coord123"
    assert call_kw["source_path"] == "/tmp/project"


@pytest.mark.asyncio
async def test_fork_session_tool_source_not_found() -> None:
    """Raises ToolError when source session does not exist."""
    from shoal.services.mcp_shoal_server import fork_session_tool

    with (
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(general=MagicMock(default_tool="omp")),
        ),
        patch(
            "shoal.core.config.load_tool_config",
            return_value=ToolConfig(name="omp", command="omp"),
        ),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None),
        pytest.raises(ToolError, match="Source session not found"),
    ):
        await fork_session_tool(source="ghost", name="worker-a")


@pytest.mark.asyncio
async def test_fork_session_tool_exists_error() -> None:
    """SessionExistsError is re-raised as ToolError."""
    from shoal.services.lifecycle import SessionExistsError
    from shoal.services.mcp_shoal_server import fork_session_tool

    mocks = _mock_fork_deps()
    err = SessionExistsError("Session 'worker-a' already exists", session_id="x")
    with (
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find_by_name"],
        mocks["get_session"],
        mocks["mkdir"],
        mocks["worktree_add"],
        mocks["infer_branch"],
        patch(
            "shoal.services.lifecycle.fork_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=err,
        ),
        pytest.raises(ToolError, match="already exists"),
    ):
        await fork_session_tool(source="coordinator", name="worker-a")


@pytest.mark.asyncio
async def test_fork_session_tool_tmux_error() -> None:
    """TmuxSetupError is re-raised as ToolError."""
    from shoal.services.lifecycle import TmuxSetupError
    from shoal.services.mcp_shoal_server import fork_session_tool

    mocks = _mock_fork_deps()
    err = TmuxSetupError("tmux failed", session_id="x")
    with (
        mocks["ensure"],
        mocks["config"],
        mocks["tool_cfg"],
        mocks["find_by_name"],
        mocks["get_session"],
        mocks["mkdir"],
        mocks["worktree_add"],
        mocks["infer_branch"],
        patch(
            "shoal.services.lifecycle.fork_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=err,
        ),
        pytest.raises(ToolError, match="Failed to create tmux session"),
    ):
        await fork_session_tool(source="coordinator", name="worker-a")


# ---------------------------------------------------------------------------
# spawn_team
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_team_tool_success() -> None:
    """Happy path: spawns 2 workers, returns correlation_id and spawned list."""
    from shoal.services.mcp_shoal_server import spawn_team_tool

    src = _make_session(name="coordinator", session_id="coord123")
    worker_a = _make_session(
        name="worker-a",
        session_id="wa111",
        branch="feat/worker-a",
        parent_id="coord123",
    )
    worker_b = _make_session(
        name="worker-b",
        session_id="wb222",
        branch="feat/worker-b",
        parent_id="coord123",
    )

    mock_provider = MagicMock()
    mock_provider.async_wait_for_ready = AsyncMock()
    mock_provider.async_send_input = AsyncMock()

    with (
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="omp"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch(
            "shoal.core.config.load_tool_config",
            return_value=ToolConfig(name="omp", command="omp", input_mode="keys"),
        ),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="coord123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=src),
        patch("pathlib.Path.mkdir"),
        patch("shoal.core.git.infer_branch_name", side_effect=["feat/worker-a", "feat/worker-b"]),
        patch("shoal.core.git.worktree_add"),
        patch(
            "shoal.services.lifecycle.fork_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=[worker_a, worker_b],
        ),
        patch("shoal.core.message_bus.send_message", new_callable=AsyncMock, return_value=1),
        patch(
            "shoal.services.mcp_shoal_server.provider_for_session",
            return_value=mock_provider,
        ),
    ):
        result = await spawn_team_tool(
            source="coordinator",
            workers=[
                {"name": "worker-a", "prompt": "Do task A"},
                {"name": "worker-b", "prompt": "Do task B"},
            ],
        )

    assert "correlation_id" in result
    assert len(result["correlation_id"]) == 8
    assert len(result["spawned"]) == 2
    assert result["failed"] == []
    names = {w["name"] for w in result["spawned"]}
    assert names == {"worker-a", "worker-b"}


@pytest.mark.asyncio
async def test_spawn_team_tool_missing_name() -> None:
    """Worker dict without 'name' key raises ToolError immediately."""
    from shoal.services.mcp_shoal_server import spawn_team_tool

    with (
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(general=MagicMock(default_tool="omp")),
        ),
        pytest.raises(ToolError, match="missing required 'name'"),
    ):
        await spawn_team_tool(
            source="coordinator",
            workers=[{"prompt": "no name provided"}],
        )


@pytest.mark.asyncio
async def test_spawn_team_tool_partial_failure() -> None:
    """One worker fails — others succeed and failed list is populated."""
    from shoal.services.lifecycle import TmuxSetupError
    from shoal.services.mcp_shoal_server import spawn_team_tool

    src = _make_session(name="coordinator", session_id="coord123")
    worker_ok = _make_session(
        name="worker-ok",
        session_id="wok111",
        branch="feat/worker-ok",
        parent_id="coord123",
    )

    fork_results: list[object] = [
        TmuxSetupError("tmux exploded", session_id="x"),
        worker_ok,
    ]

    with (
        patch("shoal.core.config.ensure_dirs"),
        patch(
            "shoal.core.config.load_config",
            return_value=MagicMock(
                general=MagicMock(default_tool="omp"),
                tmux=MagicMock(startup_commands=[]),
            ),
        ),
        patch(
            "shoal.core.config.load_tool_config",
            return_value=ToolConfig(name="omp", command="omp", input_mode="keys"),
        ),
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="coord123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=src),
        patch("pathlib.Path.mkdir"),
        patch(
            "shoal.core.git.infer_branch_name",
            side_effect=["feat/worker-fail", "feat/worker-ok"],
        ),
        patch("shoal.core.git.worktree_add"),
        patch(
            "shoal.services.lifecycle.fork_session_lifecycle",
            new_callable=AsyncMock,
            side_effect=fork_results,
        ),
        patch("shoal.core.message_bus.send_message", new_callable=AsyncMock, return_value=1),
    ):
        result = await spawn_team_tool(
            source="coordinator",
            workers=[
                {"name": "worker-fail"},
                {"name": "worker-ok"},
            ],
        )

    assert len(result["spawned"]) == 1
    assert result["spawned"][0]["name"] == "worker-ok"
    assert len(result["failed"]) == 1
    assert result["failed"][0]["name"] == "worker-fail"
    assert "tmux exploded" in result["failed"][0]["error"]


# ---------------------------------------------------------------------------
# wait_for_team
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_team_all_complete() -> None:
    """All workers have completed_at set — returns immediately with all_complete=True."""
    from shoal.services.mcp_shoal_server import wait_for_team_tool

    now = datetime.now(UTC)
    wa = _make_session(name="worker-a", session_id="wa1", completed_at=now)
    wb = _make_session(name="worker-b", session_id="wb2", completed_at=now)

    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[wa, wb]):
        result = await wait_for_team_tool(
            correlation_id="abc12345",
            session_names=["worker-a", "worker-b"],
            timeout_seconds=30,
            poll_interval_seconds=5,
        )

    assert result["all_complete"] is True
    assert result["timed_out"] is False
    assert result["correlation_id"] == "abc12345"
    statuses = {w["name"]: w["status"] for w in result["workers"]}
    assert statuses["worker-a"] == "completed"
    assert statuses["worker-b"] == "completed"


@pytest.mark.asyncio
async def test_wait_for_team_timeout() -> None:
    """Workers never complete — poll loop exhausts and timed_out=True."""
    from shoal.services.mcp_shoal_server import wait_for_team_tool

    wa = _make_session(name="worker-a", session_id="wa1", status=SessionStatus.running)

    with (
        patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[wa]),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await wait_for_team_tool(
            correlation_id="tid",
            session_names=["worker-a"],
            timeout_seconds=1,
            poll_interval_seconds=1,
        )

    assert result["timed_out"] is True
    assert result["all_complete"] is False
    assert result["workers"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_wait_for_team_mixed_states() -> None:
    """One worker completed, one still running — all_complete=False, timed_out=True."""
    from shoal.services.mcp_shoal_server import wait_for_team_tool

    now = datetime.now(UTC)
    wa_done = _make_session(name="worker-a", session_id="wa1", completed_at=now)
    wb_running = _make_session(name="worker-b", session_id="wb2", status=SessionStatus.running)

    with (
        patch(
            "shoal.core.state.list_sessions",
            new_callable=AsyncMock,
            return_value=[wa_done, wb_running],
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await wait_for_team_tool(
            correlation_id="cid",
            session_names=["worker-a", "worker-b"],
            timeout_seconds=1,
            poll_interval_seconds=1,
        )

    assert result["timed_out"] is True
    assert result["all_complete"] is False
    statuses = {w["name"]: w["status"] for w in result["workers"]}
    assert statuses["worker-a"] == "completed"
    assert statuses["worker-b"] == "running"


@pytest.mark.asyncio
async def test_wait_for_team_error_terminal() -> None:
    """Error-status workers count as terminal — all_complete=True when all are error."""
    from shoal.services.mcp_shoal_server import wait_for_team_tool

    wa_err = _make_session(name="worker-a", session_id="wa1", status=SessionStatus.error)

    with patch("shoal.core.state.list_sessions", new_callable=AsyncMock, return_value=[wa_err]):
        result = await wait_for_team_tool(
            correlation_id="eid",
            session_names=["worker-a"],
            timeout_seconds=30,
            poll_interval_seconds=5,
        )

    assert result["all_complete"] is True
    assert result["timed_out"] is False
    assert result["workers"][0]["status"] == "error"
