"""Tests for dashboard fzf configuration — _build_fzf_args()."""

from __future__ import annotations

import pytest

from shoal.dashboard.popup import _build_fzf_args


@pytest.fixture
def fzf_args() -> list[str]:
    """Return the built fzf args list."""
    return _build_fzf_args()


def test_build_fzf_args_returns_list(fzf_args: list[str]) -> None:
    """_build_fzf_args returns a non-empty list of strings."""
    assert isinstance(fzf_args, list)
    assert len(fzf_args) > 0
    assert all(isinstance(a, str) for a in fzf_args)


def test_build_fzf_args_starts_with_fzf(fzf_args: list[str]) -> None:
    """First element is the fzf binary name."""
    assert fzf_args[0] == "fzf"


def test_build_fzf_args_contains_ctrl_a(fzf_args: list[str]) -> None:
    """ctrl-a (approve) binding is present."""
    assert any("ctrl-a" in a for a in fzf_args)


def test_build_fzf_args_contains_ctrl_f(fzf_args: list[str]) -> None:
    """ctrl-f (fork) binding is present."""
    assert any("ctrl-f" in a for a in fzf_args)


def test_build_fzf_args_contains_ctrl_r(fzf_args: list[str]) -> None:
    """ctrl-r (reload) binding is present."""
    assert any("ctrl-r" in a for a in fzf_args)


def test_build_fzf_args_contains_ctrl_w(fzf_args: list[str]) -> None:
    """ctrl-w (waiting filter) binding is present."""
    assert any("ctrl-w" in a for a in fzf_args)


def test_build_fzf_args_header_mentions_ctrl_a(fzf_args: list[str]) -> None:
    """Header mentions ctrl-a."""
    header = next(a for a in fzf_args if a.startswith("--header="))
    assert "ctrl-a" in header


def test_build_fzf_args_header_mentions_ctrl_f(fzf_args: list[str]) -> None:
    """Header mentions ctrl-f."""
    header = next(a for a in fzf_args if a.startswith("--header="))
    assert "ctrl-f" in header


def test_build_fzf_args_ctrl_a_uses_shoal_send(fzf_args: list[str]) -> None:
    """ctrl-a binding invokes shoal send with session ID placeholder."""
    ctrl_a = next(a for a in fzf_args if a.startswith("--bind=") and "ctrl-a" in a)
    assert "shoal send" in ctrl_a
    assert "{1}" in ctrl_a


def test_build_fzf_args_ctrl_f_calls_fork_with_id(fzf_args: list[str]) -> None:
    """ctrl-f binding calls shoal fork with the session ID placeholder."""
    ctrl_f = next(a for a in fzf_args if a.startswith("--bind=") and "ctrl-f" in a)
    assert "shoal fork" in ctrl_f
    assert "{1}" in ctrl_f


def test_build_fzf_args_ctrl_w_filters_waiting(fzf_args: list[str]) -> None:
    """ctrl-w binding filters output to waiting sessions."""
    ctrl_w = next(a for a in fzf_args if a.startswith("--bind=") and "ctrl-w" in a)
    assert "waiting" in ctrl_w


def test_build_fzf_args_ctrl_r_reloads(fzf_args: list[str]) -> None:
    """ctrl-r binding triggers a list reload."""
    ctrl_r = next(a for a in fzf_args if a.startswith("--bind=") and "ctrl-r" in a)
    assert "reload" in ctrl_r
    assert "shoal _popup-list" in ctrl_r
