"""Tests for FsWatcher — filesystem monitoring service."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from shoal.services.fs_watcher import (
    FsWatcher,
    WatchedPath,
    _make_watch_filter,
    _should_ignore,
    _WatchFilter,
    get_fs_watcher,
    init_fs_watcher,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton() -> Any:
    """Ensure the global FsWatcher singleton is reset between tests."""
    import shoal.services.fs_watcher as _mod

    _mod._fs_watcher_instance = None
    yield
    _mod._fs_watcher_instance = None


# ---------------------------------------------------------------------------
# WatchedPath dataclass
# ---------------------------------------------------------------------------


class TestWatchedPath:
    def test_fields(self, tmp_path: Path) -> None:
        wp = WatchedPath(path=tmp_path, session_id="s1", session_name="my-session")
        assert wp.path == tmp_path
        assert wp.session_id == "s1"
        assert wp.session_name == "my-session"


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_returns_none_before_init(self) -> None:
        assert get_fs_watcher() is None

    def test_init_creates_instance(self) -> None:
        watcher = init_fs_watcher()
        assert isinstance(watcher, FsWatcher)
        assert get_fs_watcher() is watcher

    def test_init_replaces_existing(self) -> None:
        first = init_fs_watcher()
        second = init_fs_watcher()
        assert second is not first
        assert get_fs_watcher() is second


# ---------------------------------------------------------------------------
# add_path / remove_path / watched_paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPathManagement:
    async def test_add_path_registers_session(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        await watcher.add_path(tmp_path, "sess-1", "alpha")
        paths = watcher.watched_paths()
        assert len(paths) == 1
        assert paths[0].session_id == "sess-1"
        assert paths[0].session_name == "alpha"
        assert paths[0].path == tmp_path.resolve()

    async def test_add_path_resolves_symlinks(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        # Pass a path with trailing separator — resolve() normalises it
        await watcher.add_path(str(tmp_path) + "/", "s", "n")
        assert watcher.watched_paths()[0].path == tmp_path.resolve()

    async def test_add_path_accepts_string(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        await watcher.add_path(str(tmp_path), "s2", "beta")
        assert watcher.watched_paths()[0].path == tmp_path.resolve()

    async def test_add_multiple_sessions(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        p1 = tmp_path / "w1"
        p2 = tmp_path / "w2"
        p1.mkdir()
        p2.mkdir()
        await watcher.add_path(p1, "s1", "one")
        await watcher.add_path(p2, "s2", "two")
        ids = {wp.session_id for wp in watcher.watched_paths()}
        assert ids == {"s1", "s2"}

    async def test_remove_path_deregisters(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        await watcher.add_path(tmp_path, "s3", "gamma")
        await watcher.remove_path("s3")
        assert watcher.watched_paths() == []

    async def test_remove_nonexistent_is_noop(self) -> None:
        watcher = FsWatcher()
        await watcher.remove_path("does-not-exist")  # must not raise

    async def test_add_same_session_replaces(self, tmp_path: Path) -> None:
        watcher = FsWatcher()
        p1 = tmp_path / "a"
        p2 = tmp_path / "b"
        p1.mkdir()
        p2.mkdir()
        await watcher.add_path(p1, "s1", "first")
        await watcher.add_path(p2, "s1", "second")
        paths = watcher.watched_paths()
        assert len(paths) == 1
        assert paths[0].path == p2.resolve()
        assert paths[0].session_name == "second"


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStartStop:
    async def test_start_sets_running_flag(self) -> None:
        watcher = FsWatcher()
        with patch.object(watcher, "_run_loop", new_callable=AsyncMock):
            await watcher.start()
            assert watcher._running is True
            await watcher.stop()

    async def test_start_idempotent(self) -> None:
        watcher = FsWatcher()
        with patch.object(watcher, "_run_loop", new_callable=AsyncMock):
            await watcher.start()
            task_before = watcher._task
            await watcher.start()  # second call — no-op
            assert watcher._task is task_before
            await watcher.stop()

    async def test_stop_clears_running_flag(self) -> None:
        watcher = FsWatcher()
        with patch.object(watcher, "_run_loop", new_callable=AsyncMock):
            await watcher.start()
            assert watcher._task is not None
            await watcher.stop()
            assert watcher._running is False

    async def test_stop_before_start_is_noop(self) -> None:
        watcher = FsWatcher()
        await watcher.stop()  # must not raise
        assert watcher._running is False


# ---------------------------------------------------------------------------
# _should_ignore helper
# ---------------------------------------------------------------------------


class TestShouldIgnore:
    def test_ignores_dot_git(self) -> None:
        assert _should_ignore(".git/config") is True

    def test_ignores_pycache(self) -> None:
        assert _should_ignore("__pycache__/module.pyc") is True

    def test_ignores_node_modules(self) -> None:
        assert _should_ignore("node_modules/pkg/index.js") is True

    def test_allows_normal_path(self) -> None:
        assert _should_ignore("src/shoal/core/db.py") is False

    def test_allows_root_file(self) -> None:
        assert _should_ignore("README.md") is False

    def test_empty_path_not_ignored(self) -> None:
        # No parts → not ignored
        assert _should_ignore("") is False


# ---------------------------------------------------------------------------
# _WatchFilter
# ---------------------------------------------------------------------------


class TestWatchFilter:
    def test_allows_normal_python_file(self, tmp_path: Path) -> None:
        wf = _WatchFilter()
        assert wf(0, str(tmp_path / "src" / "module.py")) is True

    def test_rejects_pyc(self, tmp_path: Path) -> None:
        wf = _WatchFilter()
        assert wf(0, str(tmp_path / "src" / "module.pyc")) is False

    def test_rejects_pyo(self, tmp_path: Path) -> None:
        wf = _WatchFilter()
        assert wf(0, str(tmp_path / "src" / "module.pyo")) is False

    def test_rejects_hidden_dir(self, tmp_path: Path) -> None:
        wf = _WatchFilter()
        assert wf(0, str(tmp_path / ".hidden" / "file.py")) is False

    def test_rejects_global_ignore(self, tmp_path: Path) -> None:
        wf = _WatchFilter()
        assert wf(0, str(tmp_path / "__pycache__" / "x.pyc")) is False

    def test_make_watch_filter_returns_instance(self) -> None:
        wf = _make_watch_filter(["*.pyc"])
        assert isinstance(wf, _WatchFilter)


# ---------------------------------------------------------------------------
# _dispatch_changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDispatchChanges:
    async def test_emits_file_changed_event(self, tmp_path: Path) -> None:
        from watchfiles import Change

        from shoal.models.state import LifecycleEvent

        watcher = FsWatcher()
        root = str(tmp_path.resolve())
        wp = WatchedPath(path=tmp_path.resolve(), session_id="s1", session_name="alpha")
        path_to_session = {root: wp}
        changed_file = str(tmp_path / "foo.py")

        emitted: list[dict[str, Any]] = []

        async def fake_emit(event: LifecycleEvent, **kwargs: Any) -> None:
            emitted.append({"event": event, **kwargs})

        with patch("shoal.services.lifecycle.emit", side_effect=fake_emit):
            await watcher._dispatch_changes({(Change.modified, changed_file)}, path_to_session)

        assert len(emitted) == 1
        assert emitted[0]["session_id"] == "s1"
        assert emitted[0]["session_name"] == "alpha"
        assert changed_file in emitted[0]["file_paths"]

    async def test_ignored_files_not_emitted(self, tmp_path: Path) -> None:
        from watchfiles import Change

        watcher = FsWatcher()
        root = str(tmp_path.resolve())
        wp = WatchedPath(path=tmp_path.resolve(), session_id="s1", session_name="alpha")
        path_to_session = {root: wp}
        pycache_file = str(tmp_path / "__pycache__" / "x.pyc")

        emitted: list[dict[str, Any]] = []

        async def fake_emit(event: Any, **kwargs: Any) -> None:
            emitted.append(kwargs)

        with patch("shoal.services.lifecycle.emit", side_effect=fake_emit):
            await watcher._dispatch_changes({(Change.modified, pycache_file)}, path_to_session)

        assert emitted == []

    async def test_emit_failure_is_swallowed(self, tmp_path: Path) -> None:
        from watchfiles import Change

        watcher = FsWatcher()
        root = str(tmp_path.resolve())
        wp = WatchedPath(path=tmp_path.resolve(), session_id="s1", session_name="alpha")
        path_to_session = {root: wp}
        changed_file = str(tmp_path / "app.py")

        with patch(
            "shoal.services.lifecycle.emit",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise
            await watcher._dispatch_changes({(Change.added, changed_file)}, path_to_session)
