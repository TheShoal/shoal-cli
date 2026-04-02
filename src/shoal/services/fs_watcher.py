"""Filesystem watcher — monitors session worktrees for file changes.

Uses ``watchfiles`` (async-native, core dependency) to watch active session
worktrees and emit ``LifecycleEvent.file_changed`` events via the Shoal
lifecycle hook system.

Usage::

    from shoal.services.fs_watcher import FsWatcher

    watcher = FsWatcher()
    await watcher.start()
    await watcher.add_path("/path/to/worktree", session_id="abc123", session_name="my-session")
    # … later:
    await watcher.stop()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger("shoal.fs_watcher")

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class WatchedPath:
    """A filesystem path associated with a session."""

    path: Path
    session_id: str
    session_name: str


# ---------------------------------------------------------------------------
# FsWatcher
# ---------------------------------------------------------------------------


class FsWatcher:
    """Background service that watches session worktrees for file changes.

    Emits ``LifecycleEvent.file_changed`` via the lifecycle hook system
    when a tracked file is created, modified, or deleted.

    Ignore patterns from ``ProactiveConfig.ignore_patterns`` are respected.
    """

    def __init__(self) -> None:
        self._watched: dict[str, WatchedPath] = {}
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the background filesystem watch loop."""
        if self._running:
            logger.warning("FsWatcher already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="shoal-fs-watcher")
        logger.info("FsWatcher started")

    async def stop(self) -> None:
        """Stop the background watch loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("FsWatcher stopped")

    async def add_path(self, path: str | Path, session_id: str, session_name: str) -> None:
        """Register a path for watching.

        Args:
            path: Filesystem path to watch.
            session_id: Associated session ID.
            session_name: Human-readable session name.
        """
        resolved = Path(path).resolve()
        async with self._lock:
            self._watched[session_id] = WatchedPath(
                path=resolved,
                session_id=session_id,
                session_name=session_name,
            )
        logger.info("FsWatcher watching %s for session %s", resolved, session_id)

    async def remove_path(self, session_id: str) -> None:
        """Stop watching a session's path.

        Args:
            session_id: Session to stop watching.
        """
        async with self._lock:
            removed = self._watched.pop(session_id, None)
        if removed:
            logger.info("FsWatcher stopped watching session %s", session_id)

    def watched_paths(self) -> list[WatchedPath]:
        """Return a snapshot of all currently watched paths."""
        return list(self._watched.values())

    # -----------------------------------------------------------------------
    # Internal loop
    # -----------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main watch loop using watchfiles.awatch."""
        import watchfiles

        from shoal.core.config import load_config

        cfg = load_config()
        ignore_patterns = cfg.proactive.ignore_patterns

        logger.debug("FsWatcher loop started (ignore=%s)", ignore_patterns)

        while self._running:
            async with self._lock:
                paths = list(self._watched.values())

            if not paths:
                await asyncio.sleep(2.0)
                continue

            path_strs = [str(wp.path) for wp in paths]
            path_to_session = {str(wp.path): wp for wp in paths}

            try:
                # watch_filter applies a fast ignore before emitting events
                async for changes in watchfiles.awatch(
                    *path_strs,
                    watch_filter=_make_watch_filter(ignore_patterns),
                    stop_event=asyncio.Event() if not self._running else None,
                    yield_on_timeout=True,
                    debounce=500,
                    step=50,
                    rust_timeout=2_000,
                ):
                    if not self._running:
                        break
                    await self._dispatch_changes(changes, path_to_session)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("FsWatcher loop error, restarting in 5s")
                await asyncio.sleep(5.0)

    async def _dispatch_changes(
        self,
        changes: set[Any],
        path_to_session: dict[str, WatchedPath],
    ) -> None:
        """Dispatch file-change events to the lifecycle hook system.

        Args:
            changes: Set of (change_type, file_path) tuples from watchfiles.
            path_to_session: Mapping from watched root path to WatchedPath.
        """
        from shoal.models.state import LifecycleEvent
        from shoal.services.lifecycle import emit

        # Group changes by session
        session_changes: dict[str, list[str]] = {}
        for _change_type, file_path in changes:
            # Find which watched root this file belongs to
            for root_path, wp in path_to_session.items():
                try:
                    relative = Path(file_path).relative_to(root_path)
                    rel_str = str(relative)
                except ValueError:
                    continue
                if not _should_ignore(rel_str):
                    session_changes.setdefault(wp.session_id, []).append(file_path)
                    break

        # Build a direct session_id → WatchedPath index from the already-grouped changes.
        session_id_to_wp: dict[str, WatchedPath] = {
            wp.session_id: wp for wp in path_to_session.values()
        }

        for session_id, file_paths in session_changes.items():
            maybe_wp: WatchedPath | None = session_id_to_wp.get(session_id)
            if maybe_wp is None:
                continue
            found_wp: WatchedPath = maybe_wp
            logger.debug(
                "FsWatcher: %d file(s) changed in session %s",
                len(file_paths),
                session_id,
            )
            try:
                await emit(
                    LifecycleEvent.file_changed,
                    session_id=session_id,
                    session_name=found_wp.session_name,
                    file_paths=file_paths,
                )
            except Exception:
                logger.warning(
                    "FsWatcher: failed to emit file_changed for session %s",
                    session_id,
                    exc_info=True,
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_GLOBAL_IGNORES = frozenset(
    [
        ".git",
        "__pycache__",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    ]
)


def _should_ignore(relative_path: str) -> bool:
    """Return True if the path should be silently ignored.

    Args:
        relative_path: Path relative to the watched root.

    Returns:
        True if the path matches a hard-coded ignore pattern.
    """
    parts = Path(relative_path).parts
    return bool(parts and parts[0] in _GLOBAL_IGNORES)


@dataclass
class _WatchFilter:
    """watchfiles filter callable that rejects paths matching ignore patterns."""

    ignore_patterns: list[str] = field(default_factory=list)

    def __call__(self, _change: int, path: str) -> bool:
        from pathlib import Path as _Path

        p = _Path(path)
        # Reject hidden dirs and global ignores
        for part in p.parts:
            if part.startswith(".") or part in _GLOBAL_IGNORES:
                return False
        # Reject compiled Python artefacts
        return not path.endswith((".pyc", ".pyo"))


def _make_watch_filter(ignore_patterns: list[str]) -> _WatchFilter:
    """Create a watchfiles filter respecting the provided ignore patterns.

    Args:
        ignore_patterns: Gitignore-style patterns from ProactiveConfig.

    Returns:
        A callable filter for ``watchfiles.awatch``.
    """
    return _WatchFilter(ignore_patterns=ignore_patterns)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_fs_watcher_instance: FsWatcher | None = None


def get_fs_watcher() -> FsWatcher | None:
    """Return the global FsWatcher singleton if initialised.

    Returns:
        FsWatcher instance, or None if not yet started.
    """
    return _fs_watcher_instance


def init_fs_watcher() -> FsWatcher:
    """Initialise and return the global FsWatcher singleton.

    Returns:
        Initialised FsWatcher instance.
    """
    global _fs_watcher_instance
    _fs_watcher_instance = FsWatcher()
    return _fs_watcher_instance
