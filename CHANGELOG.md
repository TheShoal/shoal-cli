# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-02-16

### Changed
- **Robo Supervisor**: Renamed "conductor" to "robo" (inspired by robo-fish research). Backward-compatible aliases maintained.
- **Configuration**: Config sections renamed from `[conductor]` to `[robo]`. Both names supported for backward compatibility.
- **File Paths**: Robo profiles now stored in `~/.config/shoal/robo/` (falls back to `conductor/` for existing configs).

### Added
- **Demo Command**: New `shoal demo start/stop` for interactive onboarding with example sessions.
- **Documentation**: Comprehensive robo workflow guide (docs/ROBO_GUIDE.md) with patterns and examples.
- **Documentation**: Release process guide (RELEASE_PROCESS.md) with semver workflow and checklist.
- **Error Messages**: Improved CLI error messages with actionable suggestions for common mistakes.
- **Use Cases**: Added practical examples to README (parallel development, code review, batch processing).

### Performance
- **Database Optimization**: Added indexed lookup for session name queries (replaced O(n) scan).

### Development
- **Test Coverage**: Measured baseline at 52% (96 tests passing).
- **Dependencies**: Added pytest-cov for coverage tracking.

## [0.4.0] - 2026-02-16

### Added
- **Command Rename**: `shoal new` is now the primary command (was `add`). `add` remains as a hidden alias.
- **Table Consistency**: All `ls` commands now use consistent Panel styling with Nerd Font icons.

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
- **Robo Interactions**: Way for the robo supervisor to interact with child sessions (send keys, approve actions).

### Changed
- **API Update**: Refactored `server.py` to use async DB calls.
- **Strict Typing**: Audited `src/shoal/core/state.py` and improved typing.
- **Code Consolidation**: Merged CLI tests and cleaned up redundant documentation/comments.
- **Process Management**: Better tracking of session PIDs and auto-cleanup of "ghost" sessions.

### Fixed
- **Testing**: Added comprehensive tests for session lifecycle, PID tracking, and ghost detection.
