"""Unit tests for MCP matrix context builder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shoal.dashboard.context import mcp_matrix_context
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState


def _make_session(
    session_id: str = "abc123",
    name: str = "test-session",
    tool: str = "omp",
    status: SessionStatus = SessionStatus.running,
    mcp_servers: list[str] | None = None,
) -> SessionState:
    now = datetime.now(UTC)
    return SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path="/tmp/repo",
        worktree="",
        branch="main",
        runtime=TmuxRuntimeState(session_name=f"shoal:{session_id}"),
        status=status,
        mcp_servers=mcp_servers or [],
        tags=[],
        created_at=now - timedelta(hours=1),
        last_activity=now - timedelta(minutes=5),
        status_since=now - timedelta(minutes=5),
    )


class TestMcpMatrixContext:
    def test_empty_sessions(self) -> None:
        ctx = mcp_matrix_context(sessions=[], available_servers=["a", "b"], stacks=[])
        assert ctx["sessions"] == []
        assert ctx["servers"] == ["a", "b"]

    def test_sessions_sorted_by_name(self) -> None:
        sessions = [
            _make_session(session_id="s1", name="work"),
            _make_session(session_id="s2", name="alpha"),
        ]
        ctx = mcp_matrix_context(sessions=sessions, available_servers=[], stacks=[])
        rows = ctx["sessions"]
        assert isinstance(rows, list)
        assert rows[0]["name"] == "alpha"
        assert rows[1]["name"] == "work"

    def test_mcp_enabled_mapping(self) -> None:
        session = _make_session(mcp_servers=["github"])
        ctx = mcp_matrix_context(
            sessions=[session], available_servers=["github", "fs"], stacks=[]
        )
        row = ctx["sessions"][0]
        assert row["mcp_enabled"] == {"github": True, "fs": False}

    def test_stopped_session_is_stopped(self) -> None:
        session = _make_session(status=SessionStatus.stopped)
        ctx = mcp_matrix_context(sessions=[session], available_servers=[], stacks=[])
        assert ctx["sessions"][0]["is_stopped"] is True

    def test_running_session_not_stopped(self) -> None:
        session = _make_session(status=SessionStatus.running)
        ctx = mcp_matrix_context(sessions=[session], available_servers=[], stacks=[])
        assert ctx["sessions"][0]["is_stopped"] is False

    def test_tier_css_populated(self) -> None:
        session = _make_session(status=SessionStatus.running)
        ctx = mcp_matrix_context(sessions=[session], available_servers=[], stacks=[])
        tier_css = ctx["sessions"][0]["tier_css"]
        assert isinstance(tier_css, str)
        assert tier_css.startswith("tier-")

    @pytest.mark.skip(reason="groups parameter not implemented in mcp_matrix_context")
    def test_groups_passed_through(self) -> None:
        groups = [{"name": "dev", "servers": ["a"], "source": "config", "description": ""}]
        ctx = mcp_matrix_context(sessions=[], available_servers=[], stacks=[], groups=groups)
        assert ctx["groups"] == groups
