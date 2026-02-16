# TO-DO

## Done in v0.4.0

- [x] **SQLite Migration**: Replace JSON files with a single `shoal.db` (using WAL mode for concurrency).
- [x] **Async Refactor**: Move `shoal.core` to an async-first model using `aiosqlite` and `anyio`.
- [x] **Strict Typing**: Audited `src/shoal/core/state.py` and improved typing.
- [x] **API Update**: Refactored `server.py` to use async DB calls.

## Done in v0.3.0

- [x] Fix Pydantic serialization warnings (pass `SessionStatus` enum instead of raw strings)
- [x] Change tmux session name to use session name (e.g., `shoal_grove-hub` instead of `shoal_s4vx65au`)
- [x] Change default session name to `{project}/{worktree}` when worktree is supplied
- [x] Fix `shoal fork` without worktree (added `--no-worktree` flag)
- [x] Move watcher PID/logs to `~/.local/state/shoal/` for XDG compliance
- [x] Change popup kill shortcut from ctrl-k to ctrl-x
- [x] Add tmux status bar and popup configuration guide to README
- [x] Update architecture docs and README
- [x] Conductor documentation: explain it's an AI agent running with AGENTS.md instructions

## Roadmap v0.5.0: The Interface (UI & UX)
- [ ] **Web Dashboard**: React + Tailwind frontend for managing sessions via the API.
- [ ] **Advanced TUI**: Richer `shoal popup` with interactive logs and session switching.
- [ ] **Notifications**: Desktop alerts for session state transitions (waiting/error).
- [ ] **Event Bus**: Implement a Unix-socket or SQLite-based pub/sub for real-time state updates.

## Next (General Improvements)
- [ ] **Session Groups**: Group sessions for the same repo/project in `shoal ls` (e.g., group by git root).
- [ ] **Improve Conductor**: Provide a way for the conductor to actually interact with child sessions (e.g., send keys, approve actions).
- [ ] **CLI Commands**:
    - [ ] `shoal rename <old> <new>`: rename a session and its tmux session.
    - [ ] `shoal logs <name>`: tail the logs of a session tool.
- [ ] **Robust Process Management**: Better tracking of session PIDs and auto-cleanup of "ghost" sessions.

## Code Quality
- [ ] **Testing**: Add integration tests that use a mock `tmux` and `git` to verify session lifecycle.
- [ ] **Dependency Injection**: Use FastAPI `Depends` in `server.py` for config/state access.
