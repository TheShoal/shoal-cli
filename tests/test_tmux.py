"""Tests for core.tmux module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.core import tmux


def test_has_session_true():
    """Test has_session returns True when session exists."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.has_session("test-session")

        assert result is True
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "test-session"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_has_session_false():
    """Test has_session returns False when session doesn't exist."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        result = tmux.has_session("nonexistent")

        assert result is False


def test_new_session():
    """Test new_session creates a tmux session and sets SHOAL_AGENT."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        tmux.new_session("my-session", cwd="/tmp/project")

        assert mock_run.call_count == 2
        # First call: new-session
        mock_run.assert_any_call(
            ["tmux", "new-session", "-d", "-s", "my-session", "-c", "/tmp/project"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        # Second call: set SHOAL_AGENT env var
        mock_run.assert_any_call(
            ["tmux", "set-environment", "-t", "my-session", "SHOAL_AGENT", "1"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_new_session_no_cwd():
    """Test new_session without specifying cwd."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        tmux.new_session("my-session")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["tmux", "new-session", "-d", "-s", "my-session"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        # SHOAL_AGENT always set
        mock_run.assert_any_call(
            ["tmux", "set-environment", "-t", "my-session", "SHOAL_AGENT", "1"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_kill_session():
    """Test kill_session terminates a tmux session."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.kill_session("old-session")
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "kill-session", "-t", "old-session"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_send_keys():
    """Test send_keys sends literal text then Enter as separate tmux calls."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        tmux.send_keys("my-session", "echo hello")

        assert mock_run.call_count == 2
        # First call: send literal text with -l flag
        mock_run.assert_any_call(
            ["tmux", "send-keys", "-t", "my-session", "-l", "echo hello"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        # Second call: send Enter key separately (no -l)
        mock_run.assert_any_call(
            ["tmux", "send-keys", "-t", "my-session", "Enter"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_send_keys_without_enter() -> None:
    """Test send_keys with enter=False sends literal text only."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.send_keys("my-session", "echo hello", enter=False)
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "send-keys", "-t", "my-session", "-l", "echo hello"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_send_keys_enter_is_separate_command() -> None:
    """Enter is sent as a separate tmux send-keys call, not embedded in text."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        tmux.send_keys("my-session", "echo hello")

        assert mock_run.call_count == 2
        # First call sends literal text with -l
        text_call_args = mock_run.call_args_list[0][0][0]
        assert "-l" in text_call_args, "Text must be sent with -l flag"
        assert "\n" not in text_call_args[5], "Text must not contain embedded newline"
        # Second call sends Enter key without -l
        enter_call_args = mock_run.call_args_list[1][0][0]
        assert "-l" not in enter_call_args, "Enter must not use -l flag"
        assert "Enter" in enter_call_args, "Enter key must be sent separately"


def test_switch_client():
    """Test switch_client switches to a tmux session."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.switch_client("target-session")
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "switch-client", "-t", "target-session"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_run_command():
    """Test run_command executes a tmux command."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        tmux.run_command("display-message 'Hello'")

        # Should split by shlex and prepend 'tmux'
        assert mock_run.call_count == 1
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "tmux"
        assert "display-message" in call_args
        assert "Hello" in call_args


def test_set_environment():
    """Test set_environment sets an env var in a tmux session."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.set_environment("my-session", "MY_VAR", "my-value")
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "set-environment", "-t", "my-session", "MY_VAR", "my-value"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_popup():
    """Test popup creates a tmux popup."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.popup("shoal ls")
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "popup", "-E", "-w", "90%", "-h", "80%", "shoal ls"],
            capture_output=False,
            text=True,
            check=True,
            timeout=30,
        )


def test_popup_custom_size():
    """Test popup with custom width and height."""
    with patch("shoal.core.tmux.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = tmux.popup("shoal status", width="50%", height="60%")
        assert result is None

        mock_run.assert_called_once_with(
            ["tmux", "popup", "-E", "-w", "50%", "-h", "60%", "shoal status"],
            capture_output=False,
            text=True,
            check=True,
            timeout=30,
        )


# ---------------------------------------------------------------------------
# async_send_keys — delay behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_send_keys_no_delay_delegates_to_sync() -> None:
    """With delay=0 async_send_keys is a simple thread delegation."""
    with patch("shoal.core.tmux.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        await tmux.async_send_keys("my-session", "hello", enter=True, delay=0.0)
        mock_thread.assert_called_once_with(tmux.send_keys, "my-session", "hello", enter=True)


@pytest.mark.asyncio
async def test_async_send_keys_with_delay_splits_paste_and_enter() -> None:
    """With delay>0 text paste and Enter are sent as separate to_thread calls."""
    sleep_called_with: list[float] = []

    async def fake_sleep(secs: float) -> None:
        sleep_called_with.append(secs)

    to_thread_calls: list[tuple[object, ...]] = []

    async def fake_to_thread(fn: object, *args: object, **kwargs: object) -> None:
        to_thread_calls.append((fn, args, kwargs))

    with (
        patch("shoal.core.tmux.asyncio.to_thread", side_effect=fake_to_thread),
        patch("shoal.core.tmux.asyncio.sleep", side_effect=fake_sleep),
    ):
        await tmux.async_send_keys("my-session", "hello", enter=True, delay=0.15)

    # Sleep called once with the requested delay
    assert sleep_called_with == [0.15]

    # First to_thread call: paste text without Enter
    first_fn, first_args, first_kwargs = to_thread_calls[0]
    assert first_fn is tmux.send_keys
    assert first_args == ("my-session", "hello")
    assert first_kwargs == {"enter": False}

    # Second to_thread call: send Enter key via _run
    second_fn, second_args, _second_kwargs = to_thread_calls[1]
    assert second_fn is tmux._run
    assert second_args == (["send-keys", "-t", "my-session", "Enter"],)


@pytest.mark.asyncio
async def test_async_send_keys_delay_skipped_when_no_enter() -> None:
    """Delay is irrelevant when enter=False — sleep must not be called."""
    sleep_calls: list[float] = []

    async def fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    with (
        patch("shoal.core.tmux.asyncio.to_thread", new_callable=AsyncMock),
        patch("shoal.core.tmux.asyncio.sleep", side_effect=fake_sleep),
    ):
        await tmux.async_send_keys("my-session", "hello", enter=False, delay=0.5)

    assert sleep_calls == [], "sleep must not be called when enter=False"
