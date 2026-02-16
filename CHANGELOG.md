# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-02-16

### Added
- **SQLite Migration**: Replaced JSON files with a single `shoal.db` (using WAL mode for concurrency).
- **Async Refactor**: Moved `shoal.core` to an async-first model using `aiosqlite` and `anyio`.
- **Tmux Startup Commands**: Added `startup_commands` to `config.toml` for custom session initialization.
- **CLI Commands**:
  - `shoal rename <old> <new>`: rename a session and its tmux session.
  - `shoal logs <name>`: tail the logs of a session tool.
  - `shoal info <name>`: detailed session summary.
- **Session Groups**: Group sessions for the same repo/project in `shoal ls` (e.g., group by git root).
- **Conductor Interactions**: Way for the conductor to interact with child sessions (send keys, approve actions).

### Changed
- **API Update**: Refactored `server.py` to use async DB calls.
- **Strict Typing**: Audited `src/shoal/core/state.py` and improved typing.
- **Code Consolidation**: Merged CLI tests and cleaned up redundant documentation/comments.
- **Process Management**: Better tracking of session PIDs and auto-cleanup of "ghost" sessions.

### Fixed
- **Testing**: Added comprehensive tests for session lifecycle, PID tracking, and ghost detection.
