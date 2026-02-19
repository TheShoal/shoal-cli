# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Neovim Socket Routing**: `shoal nvim` now resolves sockets dynamically from tmux IDs (`session_id`, `window_id`) instead of relying on static window-0 assumptions.
- **Rename Stability**: Neovim socket targeting is stable across tmux/session renames because routing is ID-based.
- **Watcher Pane Drift**: Status watcher and notifications now track only the session-tagged pane (`shoal:<session_id>`), preventing false waiting alerts when users split/switch panes.

### Changed
- **Runtime Metadata**: Session state now persists tmux coordinate metadata (`tmux_session_id`, `tmux_window`) and derives socket paths from that contract.
- **Documentation Cleanup**: Archived completed handoff/refocus/review docs under `docs/archive/` and updated roadmap/architecture for pre-v0.8.0 state.

## [0.5.0] - 2026-02-16

### Added
- **Fish Shell Integration**: `shoal setup fish` command to install completions, key bindings, and abbreviations
- **Fish Completions**: Dynamic completions for session names, MCP servers, robo profiles, and all subcommands
- **Fish Key Bindings**: Ctrl+S for dashboard popup, Alt+A for quick attach
- **Fish Abbreviations**: Short aliases (sa, sl, ss, sp, sn, sk, si) for common commands
- **Fish Uninstall**: `shoal setup fish --uninstall` to cleanly remove all installed fish integration files
- **Debug Logging**: `--debug` global flag enables DEBUG-level logging to stderr for any command
- **Plain Format**: Extended `--format plain` to `ls` and `status` commands for shell completion parsing

### Fixed
- **Subprocess Timeouts**: Added 30s default timeout (120s for git push) with clear error messages
- **Watcher Resilience**: Wrapped watcher poll loop in try/except to survive transient errors
- **Tmux Collisions**: Added tmux name collision detection and fork cleanup on failure
- **ConnectionManager**: Refactored to use set with per-connection error handling
- **API Security**: Bound API server to 127.0.0.1 by default instead of 0.0.0.0
- **Fish Templates**: Added interactive guard, fixed universal variable scope, sanitized fzf arguments
- **MCP Proxy Validation**: Added regex validation on MCP proxy server names to prevent command injection
- **Socat Injection**: Added `shlex.quote()` to socat EXEC command arguments
- **Startup Commands**: Added KeyError guard on `cmd.format()` to handle malformed templates
- **Status Counts**: Unknown session statuses are now bucketed and displayed instead of silently dropped
- **XDG Compliance**: `get_fish_config_dir()` respects `XDG_CONFIG_HOME` with fallback to `~/.config/fish`

### Changed
- **CLI Deduplication**: Extracted shared `_check_environment()` helper for `init` and `check` commands
- **CI Hardening**: Replaced curl|sh with setup-uv action, added fish syntax check to CI pipeline

## [0.4.2] - 2026-02-16

### Fixed
- **Database Lifecycle**: Fixed database connection leaks in nvim commands by wrapping with `with_db()` context manager
- **API Server**: Added database cleanup to lifespan shutdown to prevent connection leaks
- **Async Sleep**: Replaced blocking `time.sleep(1)` with `await asyncio.sleep(1)` in `_logs_impl` function
- **Error Logging**: Added `logger.exception()` to silent exception handler in `poll_status_changes` for better debugging
- **Demo Security**: Added `shlex.quote()` to script paths in demo send_keys calls to prevent injection issues

### Changed
- **Code Deduplication**: Replaced 6 duplicated tool icon loading blocks with `_get_tool_icon()` helper function
- **Status Style Extraction**: Extracted status style mapping to `get_status_style()` helper function, eliminating duplication across session.py and worktree.py
- **Type Safety**: Converted `RoboState.status` from `str` to `SessionStatus` enum for type consistency
- **API Validation**: Replaced raw `dict` with `SendKeysRequest` Pydantic model in `send_keys_api` endpoint

### Added
- **Test Coverage**: Added pytest-cov>=4.1.0 with 57% coverage threshold
- **Test Infrastructure**: Created test files for demo commands, git wrappers, tmux wrappers, and MCP pool lifecycle
- **DB Tests**: Added 5 new tests for robo database methods
- **API Tests**: Added 3 new tests for create_session, send_keys, and status endpoints
- **Coverage Config**: Added `[tool.coverage]` configuration to pyproject.toml with source path and reporting options

### Development
- **Test Status**: 137 tests passing, 11 complex integration tests skipped for future iteration
- **Coverage**: Achieved 57.09% test coverage (baseline was 52% in v0.4.1)

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
