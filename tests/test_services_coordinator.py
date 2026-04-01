from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.models.config.workspace import CoordinatorConfig
from shoal.models.state import SessionState, SessionStatus
from shoal.services.coordinator import CoordinatorService, CoordinatorSession


@pytest.fixture
def config():
    return CoordinatorConfig(
        poll_interval_seconds=1,
        squash_merge=True,
    )


@pytest.fixture
def service(config):
    return CoordinatorService(config)


@pytest.mark.asyncio
async def test_start_stop(service):
    await service.start()
    assert service._running is True
    assert service._task is not None

    # Try starting again
    await service.start()

    await service.stop()
    assert service._running is False


@pytest.mark.asyncio
async def test_register_unregister(service):
    await service.register_session(
        session_id="1",
        session_name="test-session",
        worktree_path="/tmp/worktree",
        branch_name="feature",
        parent_branch="main",
    )

    assert "1" in service._sessions
    session = service._sessions["1"]
    assert session.session_name == "test-session"
    assert session.worktree_path == "/tmp/worktree"
    assert session.branch_name == "feature"
    assert session.parent_branch == "main"

    await service.unregister_session("1")
    assert "1" not in service._sessions


@pytest.mark.asyncio
async def test_poll_loop_error_handling(service):
    service._running = True

    with patch.object(service, "_poll_sessions", side_effect=Exception("Test error")) as mock_poll:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # We want to run one loop then stop
            mock_sleep.side_effect = lambda _: setattr(service, "_running", False)
            await service._poll_loop()

            mock_poll.assert_called_once()
            mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_check_session_status(service, config):
    coord_session = CoordinatorSession(
        session_id="1",
        session_name="test",
        worktree_path="/path",
        branch_name="feature",
        parent_branch="main",
        config=config,
        last_status=SessionStatus.waiting,
    )

    # Not found
    with patch("shoal.services.coordinator.get_session", return_value=None):
        await service._check_session_status(coord_session)
        assert coord_session.last_status == SessionStatus.waiting

    # Found but not terminal
    mock_session = MagicMock(spec=SessionState)
    mock_session.status = SessionStatus.working
    with patch("shoal.services.coordinator.get_session", return_value=mock_session):
        await service._check_session_status(coord_session)
        # It shouldn't change
        # wait, if current != error, does it update last_status? The code says NO!
        assert coord_session.last_status == SessionStatus.waiting

    # Transition to terminal state (error)
    mock_session.status = SessionStatus.error
    with patch("shoal.services.coordinator.get_session", return_value=mock_session):
        with patch.object(service, "_perform_squash_merge", new_callable=AsyncMock) as mock_merge:
            await service._check_session_status(coord_session)
            assert coord_session.last_status == SessionStatus.error
            assert coord_session.squash_pending is True
            mock_merge.assert_called_once_with(coord_session)


@pytest.mark.asyncio
async def test_poll_sessions(service, config):
    coord_session = CoordinatorSession(
        session_id="1",
        session_name="test",
        worktree_path="/path",
        branch_name="feature",
        parent_branch="main",
        config=config,
    )
    service._sessions["1"] = coord_session

    with patch.object(service, "_check_session_status", new_callable=AsyncMock) as mock_check:
        await service._poll_sessions()
        mock_check.assert_called_once_with(coord_session)

    # Error checking session status does not raise uncaught
    with patch.object(service, "_check_session_status", side_effect=Exception("Check error")):
        await service._poll_sessions()  # Should not raise


@pytest.mark.asyncio
@patch("shoal.services.coordinator.git._run")
async def test_perform_squash_merge_success(mock_run, service, config):
    coord_session = CoordinatorSession(
        session_id="1",
        session_name="test",
        worktree_path="/path",
        branch_name="feature",
        parent_branch="main",
        config=config,
    )

    def side_effect(args, cwd):
        mock_result = MagicMock()
        if args[0] == "rev-list":
            mock_result.stdout = "2\n"
        return mock_result

    mock_run.side_effect = side_effect

    await service._perform_squash_merge(coord_session)
    assert mock_run.call_count >= 5  # checkout, rev-list, reset, commit (add + commit), merge
    assert coord_session.squash_pending is False


@pytest.mark.asyncio
@patch("shoal.services.coordinator.git._run")
async def test_perform_squash_merge_no_commits(mock_run, service, config):
    coord_session = CoordinatorSession(
        session_id="1",
        session_name="test",
        worktree_path="/path",
        branch_name="feature",
        parent_branch="main",
        config=config,
    )

    def side_effect(args, cwd):
        mock_result = MagicMock()
        if args[0] == "rev-list":
            mock_result.stdout = "0\n"
        return mock_result

    mock_run.side_effect = side_effect

    await service._perform_squash_merge(coord_session)
    # Only checkout and rev-list called
    assert mock_run.call_count == 2
    assert coord_session.squash_pending is False


@pytest.mark.asyncio
@patch("shoal.services.coordinator.git._run")
async def test_perform_squash_merge_error(mock_run, service, config):
    coord_session = CoordinatorSession(
        session_id="1",
        session_name="test",
        worktree_path="/path",
        branch_name="feature",
        parent_branch="main",
        config=config,
    )

    mock_run.side_effect = Exception("Git error")

    with pytest.raises(Exception, match="Git error"):
        await service._perform_squash_merge(coord_session)

    assert coord_session.squash_pending is False
