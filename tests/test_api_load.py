"""Load tests for Shoal API."""

import asyncio
import pytest
from httpx import AsyncClient
from shoal.core.state import create_session
from shoal.models.state import SessionStatus
from unittest.mock import patch


@pytest.mark.asyncio
async def test_concurrent_session_listing(async_client: AsyncClient, mock_dirs):
    """Test concurrent GET /sessions requests."""
    # Create some sessions first
    for i in range(5):
        await create_session(f"load-test-{i}", "claude", "/tmp")

    # 20 concurrent requests
    tasks = [async_client.get("/sessions") for _ in range(20)]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5


@pytest.mark.asyncio
async def test_concurrent_status_polling(async_client: AsyncClient, mock_dirs):
    """Test concurrent GET /status requests."""
    await create_session("s1", "claude", "/tmp")

    tasks = [async_client.get("/status") for _ in range(20)]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1


@pytest.mark.asyncio
async def test_concurrent_mixed_operations(async_client: AsyncClient, mock_dirs):
    """Test concurrent mixed read/write operations."""

    async def create_and_check(i):
        # Write
        post_resp = await async_client.post(
            "/sessions",
            json={
                "name": f"mixed-{i}",
                "tool": "claude",
                "path": ".",  # Current dir is a git repo in tests
            },
        )
        # Read
        get_resp = await async_client.get("/sessions")
        return post_resp, get_resp

    # Use a smaller number for mixed ops to avoid overwhelming the mock git/tmux calls
    # although those are patched in conftest/mock_dirs.
    # Wait, POST /sessions in test_api.py was skipped because it is complex.
    # Let's see if we can make it work here with proper mocks.

    with (
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value="/tmp"),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.tmux.new_session"),
        patch("shoal.core.tmux.set_environment"),
        patch("shoal.core.tmux.run_command"),
        patch("shoal.core.tmux.pane_pid", return_value=123),
    ):
        tasks = [create_and_check(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        for post_resp, get_resp in results:
            assert post_resp.status_code == 201
            assert get_resp.status_code == 200
