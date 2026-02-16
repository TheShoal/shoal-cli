# TO-DO

## Done in v0.4.0

- [x] **SQLite Migration**: Replace JSON files with a single `shoal.db` (using WAL mode for concurrency).
- [x] **Async Refactor**: Move `shoal.core` to an async-first model using `aiosqlite` and `anyio`.
- [x] **Strict Typing**: Audited `src/shoal/core/state.py` and improved typing.
- [x] **API Update**: Refactored `server.py` to use async DB calls.
- [x] **Tmux Startup Commands**: Added `startup_commands` to `config.toml` for custom session initialization.
- [x] **CLI Commands**:
  - [x] `shoal rename <old> <new>`: rename a session and its tmux session.
  - [x] `shoal logs <name>`: tail the logs of a session tool.
  - [x] `shoal info <name>`: detailed session summary.
- [x] **Code Consolidation**: Merged CLI tests and cleaned up redundant documentation/comments.

## Next (General Improvements)

- [x] **Session Groups**: Group sessions for the same repo/project in `shoal ls` (e.g., group by git root).
- [x] **Improve Conductor**: Provide a way for the conductor to actually interact with child sessions (e.g., send keys, approve actions).
- [x] **Robust Process Management**: Better tracking of session PIDs and auto-cleanup of "ghost" sessions.

## Code Quality

- [x] **Testing**: Added comprehensive tests for session lifecycle, PID tracking, and ghost detection.
- [ ] **Dependency Injection**: Use FastAPI `Depends` in `server.py` for config/state access.

## Roadmap v0.5.0: The Interface (UI & UX)

- [ ] **Web Dashboard**: React + Tailwind frontend for managing sessions via the API.
- [ ] **Advanced TUI**: Richer `shoal popup` with interactive logs and session switching.
- [ ] **Notifications**: Desktop alerts for session state transitions (waiting/error).
- [ ] **Event Bus**: Implement a Unix-socket or SQLite-based pub/sub for real-time state updates.
