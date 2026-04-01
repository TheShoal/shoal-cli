"""Integration test for MCP SessionState serialization with discriminated unions."""

from __future__ import annotations

from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState
from shoal.services.runtime_provider import runtime_payload


def test_session_state_tmux_runtime_property() -> None:
    """Test that SessionState.tmux_runtime property works correctly."""
    session = SessionState(
        id="test123",
        name="test-session",
        tool="opencode",
        path="/tmp/test",
        runtime=TmuxRuntimeState(
            session_name="_test-session",
            session_id="$1",
            window_id="@1",
            nvim_socket="/tmp/nvim-$1-@1.sock",
        ),
        status=SessionStatus.idle,
    )

    assert session.tmux_runtime.session_name == "_test-session"
    assert session.tmux_runtime.session_id == "$1"
    assert session.tmux_runtime.window_id == "@1"


def test_session_state_json_roundtrip() -> None:
    """Test that SessionState serializes and deserializes correctly with discriminated union."""
    original = SessionState(
        id="test456",
        name="roundtrip-test",
        tool="claude",
        path="/tmp/project",
        runtime=TmuxRuntimeState(
            session_name="_roundtrip-test",
            session_id="$2",
            window_id="@2",
            nvim_socket="/tmp/nvim-$2-@2.sock",
        ),
        status=SessionStatus.running,
        pid=12345,
        mcp_servers=["memory", "github"],
    )

    json_str = original.model_dump_json()
    loaded = SessionState.model_validate_json(json_str)

    assert loaded.id == original.id
    assert loaded.name == original.name
    assert loaded.tool == original.tool
    assert loaded.status == original.status
    assert loaded.pid == original.pid
    assert loaded.mcp_servers == original.mcp_servers

    assert loaded.runtime.kind == original.runtime.kind
    assert loaded.runtime.kind.value == "tmux"

    assert loaded.tmux_runtime.session_name == original.tmux_runtime.session_name
    assert loaded.tmux_runtime.session_id == original.tmux_runtime.session_id
    assert loaded.tmux_runtime.window_id == original.tmux_runtime.window_id
    assert loaded.tmux_runtime.nvim_socket == original.tmux_runtime.nvim_socket


def test_runtime_payload_tmux() -> None:
    """Test that runtime_payload returns correct dict for TmuxRuntimeState."""
    runtime = TmuxRuntimeState(
        session_name="_payload-test",
        session_id="$3",
        window_id="@3",
        nvim_socket="/tmp/nvim-$3-@3.sock",
    )

    payload = runtime_payload(runtime)

    assert payload == {
        "kind": "tmux",
        "session_name": "_payload-test",
        "session_id": "$3",
        "window_id": "@3",
        "nvim_socket": "/tmp/nvim-$3-@3.sock",
    }


def test_session_state_dict_serialization() -> None:
    """Test that SessionState.model_dump() preserves runtime type info."""
    session = SessionState(
        id="test789",
        name="dict-test",
        tool="pi",
        path="/tmp/dict-test",
        runtime=TmuxRuntimeState(
            session_name="_dict-test",
            session_id="$4",
            window_id="@4",
        ),
        status=SessionStatus.waiting,
    )

    d = session.model_dump()

    assert isinstance(d["runtime"], dict)
    assert d["runtime"]["kind"] == "tmux"
    assert d["runtime"]["session_name"] == "_dict-test"

    loaded = SessionState.model_validate(d)
    assert loaded.tmux_runtime.session_name == "_dict-test"
