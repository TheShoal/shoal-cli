import asyncio
from datetime import UTC, datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from shoal.services.dreamer import (
    DreamerService,
    DreamerSession,
    get_dreamer,
    init_dreamer,
)


class DreamerConfig(BaseModel):
    model: str = "gpt-oss-20b"
    summary_interval_seconds: int = 10
    log_lines: int = 100

@pytest.fixture
def config():
    return DreamerConfig(summary_interval_seconds=1, log_lines=5)

@pytest.fixture
def service(config):
    return DreamerService(config)

@pytest.fixture
def session(config):
    return DreamerSession(
        session_id="session-1",
        session_name="test-session",
        dreamer_pane_id="pane-1",
        tmux_session="tmux-1",
        config=config,
    )

@pytest.mark.asyncio
async def test_init_dreamer(config):
    service = init_dreamer(config)
    assert get_dreamer() is service
    assert get_dreamer().config == config

@pytest.mark.asyncio
async def test_watch_unwatch(service, session):
    await service.watch_session(
        session.session_id,
        session.session_name,
        session.dreamer_pane_id,
        session.tmux_session,
    )
    assert session.session_id in service._sessions
    
    # Unwatch
    await service.unwatch_session(session.session_id)
    assert session.session_id not in service._sessions

@pytest.mark.asyncio
async def test_run_loop(service, session):
    await service.watch_session(
        session.session_id,
        session.session_name,
        session.dreamer_pane_id,
        session.tmux_session,
    )
    
    # We will patch poll cycle so we can end it
    poll_call_count = 0
    async def mock_poll():
        nonlocal poll_call_count
        poll_call_count += 1
        if poll_call_count == 2:
            service._running = False
    
    with patch.object(service, "_poll_cycle", new_callable=AsyncMock) as mock_cycle:
        mock_cycle.side_effect = mock_poll
        service._running = True
        await service._run_loop()
        
    assert poll_call_count == 2

@pytest.mark.asyncio
@patch("shoal.core.tmux.async_first_pane", new_callable=AsyncMock)
@patch("shoal.core.tmux.async_capture_pane", new_callable=AsyncMock)
async def test_tail_logs(mock_capture, mock_first, service, session):
    mock_first.return_value = "pane-agent"
    mock_capture.return_value = "line 1\nline 2\n"

    await service._tail_logs(session)

    assert session.accumulated_logs == ["line 1", "line 2", ]

    # Test trim
    mock_capture.return_value = "line 3\nline 4\nline 5\nline 6\nline 7\n"
    await service._tail_logs(session)
    # total 8 lines, limit is 5
    assert len(session.accumulated_logs) == 5

@pytest.mark.asyncio
async def test_summarize(service, session):
    session.accumulated_logs = ["line 1"]
    
    with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "Summary!"
        await service._summarize(session)
        assert session.summary_history == ["Summary!"]
        assert len(session.accumulated_logs) == 0

@pytest.mark.asyncio
async def test_fallback_summarize(service):
    summary = service._fallback_summarize("session-test", "line 1\nline 2")
    assert "Session session-test: 2 lines. Last: line 2" in summary

    summary = service._fallback_summarize("session-test", "")
    assert "Last: " in summary

@pytest.mark.asyncio
async def test_get_summary(service, session):
    await service.watch_session(
        session.session_id,
        session.session_name,
        session.dreamer_pane_id,
        session.tmux_session,
    )
    assert service.get_summary(session.session_id) is None
    
    service._sessions[session.session_id].summary_history.append("summ")
    assert service.get_summary(session.session_id) == "summ"
    assert service.get_all_summaries(session.session_id) == ["summ"]
    
@pytest.mark.asyncio
async def test_start_stop(service):
    with patch.object(service, "_run_loop", new_callable=AsyncMock) as mock_loop:
        await service.start()
        assert service._running is True
        assert service._task is not None
        
        # Test already running
        await service.start()
        
        await service.stop()
        assert service._running is False


@pytest.mark.asyncio
async def test_run_loop_exceptions(service, session):
    # Test CancelledError
    with patch.object(service, "_poll_cycle", new_callable=AsyncMock) as mock_poll:
        mock_poll.side_effect = asyncio.CancelledError()
        service._running = True
        await service._run_loop()
        assert service._running is True  # Didn't clear it, but broke out

    # Test Exception
    with patch.object(service, "_poll_cycle", new_callable=AsyncMock) as mock_poll:
        side_effects = [Exception("error"), ValueError("Stop iterator")]
        def side_effect():
            if side_effects:
                raise side_effects.pop(0)
            service._running = False
        mock_poll.side_effect = side_effect
        service._running = True
        await service._run_loop()

@pytest.mark.asyncio
async def test_poll_cycle(service, session):
    await service.watch_session(
        session.session_id,
        session.session_name,
        session.dreamer_pane_id,
        session.tmux_session,
    )
    
    with patch.object(service, "_tail_logs", new_callable=AsyncMock) as mock_tail, \
         patch.object(service, "_summarize", new_callable=AsyncMock) as mock_summ:
        
        # Test summarize triggered
        service._sessions[session.session_id].last_summary_time = datetime(2000, 1, 1, tzinfo=UTC) # very old
        await service._poll_cycle()
        mock_tail.assert_called_once()
        mock_summ.assert_called_once()
        
        # Test summarize skipped
        mock_tail.reset_mock()
        mock_summ.reset_mock()
        service._sessions[session.session_id].last_summary_time = datetime.now(UTC)
        await service._poll_cycle()
        mock_tail.assert_called_once()
        mock_summ.assert_not_called()

@pytest.mark.asyncio
@patch("shoal.core.tmux.async_first_pane", new_callable=AsyncMock)
async def test_tail_logs_exception(mock_first, service, session):
    mock_first.side_effect = Exception("failed tmux")
    await service._tail_logs(session)

@pytest.mark.asyncio
async def test_summarize_empty(service, session):
    session.accumulated_logs = []
    # Should safely return
    await service._summarize(session)

@pytest.mark.asyncio
async def test_summarize_exception(service, session):
    session.accumulated_logs = ["line"]
    with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("llm error")
        await service._summarize(session)
        assert session.accumulated_logs != [] # Was not cleared

@pytest.mark.asyncio
async def test_call_llm_imports(service):
    with patch("builtins.__import__", side_effect=ImportError("No ai_client")):
        res = await service._call_llm("test", "logs")
        assert "fallback" in res.lower()

@pytest.mark.asyncio
async def test_call_llm_exceptions(service):
    # If the real call__llm wasn't importable, simulate that via mocking build_prompt
    with patch.object(service, "_build_prompt", return_value="Prompt:"), \
        patch("builtins.__import__") as mock_import:
        
        # Make it simulate throwing an exception at the module load or function call level
        mock_import.side_effect = Exception("random failure")
        res = await service._call_llm("test", "logs")
        assert "fallback" in res.lower()

