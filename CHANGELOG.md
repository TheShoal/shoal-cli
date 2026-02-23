# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Transport evaluation spike**: Benchmark comparing UDS byte bridge vs FastMCP HTTP transport ([docs/transport-spike.md](docs/transport-spike.md))
- **`shoal-mcp-server --http`**: HTTP (streamable-http) transport mode for the Shoal MCP server
- **Benchmark script**: `benchmarks/transport_spike.py` for self-contained transport performance comparison

### Changed
- **`mcp doctor`**: Replaced manual JSON-RPC probe with FastMCP Client for protocol-aware health checks
- **`mcp doctor` table**: New columns (PROTOCOL, TOOLS, VERSION, LATENCY) replace old SOCKET + JSON-RPC columns
- **Graceful fallback**: `mcp doctor` shows "skip" with install hint when `fastmcp` is not installed

### Fixed
- 4 pre-existing ruff lint warnings in test_mcp_pool, test_notify, test_popup

## [0.15.0] - 2026-02-22

### Added
- **Shoal MCP Server**: FastMCP-based MCP server (`shoal-orchestrator`) exposing 6 orchestration tools: `list_sessions`, `session_status`, `session_info`, `send_keys`, `create_session`, `kill_session`
- **`shoal-mcp-server`**: New console script entry point for the MCP server (stdio transport)
- **Optional `mcp` dependency**: `pip install shoal[mcp]` installs `fastmcp>=3.0.0`
- **Pool registration**: `shoal-orchestrator` added to default MCP server registry — `shoal mcp start shoal-orchestrator` works out of the box
- **`shoal-orchestrator` mixin**: Additive mixin for any template to gain orchestration MCP tools
- **`robo-orchestrator` template**: Pre-configured Claude template with Shoal MCP for robo supervisor workflows

### Stats
- 618 tests (26 new), ruff/mypy all clean

## [0.14.0] - 2026-02-22

### Added
- **Template Inheritance**: `extends` field for single inheritance with cycle detection
- **Template Mixins**: `mixins` field for additive composition (env merge, mcp union, windows append)
- **`TemplateMixinConfig`**: New Pydantic model for additive template fragments
- **`template mixins`**: CLI command to list available mixins
- **`template show --raw`**: Display unresolved template (pre-inheritance merge)
- **Example Templates**: base-dev, claude-dev (extends), pi-dev (extends), mcp-memory and with-tests mixins

### Changed
- `load_template()` refactored to `resolve_template()` with full inheritance resolution
- Template CLI `ls` shows EXTENDS and MIX columns; `validate` shows extends chain info
- Fish completions updated for `template mixins` subcommand

### Stats
- 589 tests (39 new), ruff/mypy all clean

## [0.13.0] - 2026-02-22

### Added
- **Ruff Lint Expansion**: 10 new rule sets (ASYNC, PERF, RUF, LOG, G, C4, PIE, DTZ, RET, RSE, S)

### Changed
- Consolidated Bandit security scanning into ruff S rules
- Removed Bandit from pre-commit and CI

### Fixed
- 1 genuine event-loop-blocking bug in lifecycle.py (blocking subprocess in async)
- 28 additional lint violations across the codebase

## [0.12.0] - 2026-02-22

### Added
- **Compiled Regex Detection**: `DetectionPatterns` pre-compiles patterns via `model_validator`; detection engine uses `re.search()` for word boundaries, anchors, and alternation
- **MCP Socket Cleanup**: `shoal init` scans for and removes stale MCP sockets/PIDs from reboots or crashes

### Changed
- **Session CLI Decomposition**: Split `session.py` (1,069 lines) into `session.py`, `session_create.py`, `session_view.py`
- `_reconcile_mcp_pool()` renamed to `reconcile_mcp_pool()` (public API)

### Stats
- 553 tests (10 new), ruff/mypy/bandit all clean

## [0.11.0] - 2026-02-22

### Added
- **Pre-commit Framework**: `.pre-commit-config.yaml` with ruff, gitlint, fish syntax check, trailing whitespace, YAML/TOML validation
- **Conventional Commits**: Gitlint enforcement via `commit-msg` hook
- **Dependabot**: `.github/dependabot.yml` for pip and GitHub Actions updates
- **Task Runner**: `justfile` with targets: `just lint`, `just fmt`, `just test`, `just typecheck`, `just ci`, `just cov`, `just fish-check`
- **`.editorconfig`**: 100-char line length, UTF-8, LF endings
- **Parallel CI**: 5 concurrent jobs (lint, typecheck, test, fish-check, security)
- **Bandit**: Python security linter in pre-commit and CI
- **Release Automation**: `just release X.Y.Z` + GitHub Actions release workflow on tag push
- **CodeQL**: SAST scanning on PRs, pushes, and weekly schedule
- **pytest-xdist**: Parallel test execution (`pytest -n auto`)
- **py.typed**: PEP 561 marker for type export signaling
- **Coverage Reporting**: XML coverage upload to Codecov on main pushes

### Changed
- **mypy strict**: Added to pre-commit hooks (was only in `just typecheck`)
- **Coverage Gate**: Raised from 70% to 80%

### Fixed
- 3 pre-existing mypy strict errors (StreamWriter protocol, unused type-ignore, bare dict annotation)

### Removed
- **Backward-compat aliases**: `conductor`, `cond`, `add` CLI commands removed
- **Conductor fallbacks**: Config path fallback, `[conductor]` TOML section support, model aliases
- **`get_status_style` re-export**: Removed from `core/state.py`; callers now import from `core/theme.py`

## [0.10.1] - 2026-02-22

### Added
- **MCP Server Logging**: Per-server log files with 10MB rotation; `shoal mcp logs <name>` CLI command
- **`shoal mcp doctor`**: Deep health check — PID liveness, socket connectivity, JSON-RPC probe, latency report
- **Dirty Worktree Protection**: `kill_session_lifecycle()` checks for uncommitted changes; `DirtyWorktreeError` with `--force` override

### Fixed
- **Shell Injection**: Replaced `shell=True` with `shlex.split()` in `mcp_configure.py`
- **Unified MCP Validation**: Removed duplicate regex from `mcp_proxy.py`, imported from `mcp_pool`
- **Narrow Exception Handling**: Replaced catch-all `except Exception` in lifecycle startup paths

### Changed
- **Connection Timeouts**: 30s connect, 120s idle timeout on MCP socket connections
- **Architecture Docs**: Rewrote ARCHITECTURE.md section 4 to describe per-connection spawning semantics

## [0.10.0] - 2026-02-22

### Added
- **Pure Python MCP Bridge**: Replaced socat dependency with asyncio-based stdio-to-unix-socket bridge
- **MCP Server Registry**: Configurable `~/.config/shoal/mcp-servers.toml` replacing hardcoded `KNOWN_SERVERS`
- **Auto-configure on Attach**: `shoal mcp attach` runs tool config command automatically
- **Auto-start on Attach**: Starts MCP server automatically if not running but in registry
- **`--mcp` Flag**: `shoal new --mcp memory,github` starts and attaches MCP servers during session creation
- **Template MCP Declarations**: `SessionTemplateConfig` gains `mcp: list[str]` field
- **MCP Auto-cleanup**: Servers stopped when last session using them is killed; boot-time reconciliation

## [0.9.0] - 2026-02-22

### Added
- **Lifecycle Service**: Extracted create/fork/kill orchestration into `services/lifecycle.py` with shared rollback
- **Rollback Helpers**: Single `_rollback()` / `_rollback_async()` for CLI and API
- **Startup Reconciliation**: Boot-time check to reconcile stale DB rows with tmux state
- **Async Subprocess Wrappers**: `async_*` prefixed functions for non-blocking tmux/git calls
- **Concurrent Update Guards**: `asyncio.Lock` in `ShoalDB.update_session`

### Fixed
- **Structured Logging**: Session ID and operation name in lifecycle log lines
- **Scoped Exceptions**: Replaced broad `except Exception` in watcher with specific types
- **WebSocket Cleanup**: Explicit connection cleanup on broadcast failure

## [0.8.0] - 2026-02-21

### Added
- **Session Templates**: Declarative template schema with Pydantic validation (`--template` flag)
- **Failure Compensation**: Create/fork failures cleanly rollback DB, tmux, and worktree artifacts
- **Nvim Diagnostics Safety**: Temp-file Lua script invocation replacing fragile dynamic string composition
- **MCP Name Validation**: `validate_mcp_name()` enforced across API, CLI, and pool/proxy
- **`shoal demo tour`**: Guided walkthrough exercising 6 feature areas with live pass/fail results
- **Worktree Param Fix**: Fixed `session.py` passing `work_dir` instead of `wt_path` to `create_session()`

### Fixed
- **Tempfile Race**: Replaced deprecated `tempfile.mktemp()` with `NamedTemporaryFile(delete=False)`
- **Pi Detection**: Removed ambiguous `"❯"` from waiting patterns
- **Fish Completion Safety**: Added `test -d` guards before globbing
- **Overly Broad Catch**: Narrowed `except (ValueError, Exception)` in server.py

## [0.7.1] - 2026-02-21

### Changed
- **Socket Contract**: Moved Neovim socket routing to tmux ID coordinates (`session_id`, `window_id`)
- **Dynamic Resolution**: `shoal nvim` resolves socket paths at execution time
- **Watcher Stability**: Status watcher pinned to session-tagged pane (`shoal:<session_id>`)

### Added
- **Pi Agent Support**: Tool config, detection patterns, and `pi-dev` session template
- **Fish Enhancements**: Tool/template completions, `--tool`/`--template`/`--dry-run` flag completions

## [0.7.0] - 2026-02-18

### Changed
- **Fish-First Scope**: Removed bash/zsh support claims; fish is the single supported shell
- **OpenCode-First UX**: Claude/Gemini as secondary tool profiles
- **Template Foundation**: Added global template management and template-driven session startup

### Removed
- Bash-dependent demo paths and scripts

## [0.6.0] - 2026-02-17

### Added
- **Integration Tests**: Full workflows (new → fork → kill)
- **Load Tests**: API server with concurrent requests
- **Troubleshooting Guide**: `docs/TROUBLESHOOTING.md` for common issues
- **`--debug` Flag**: Global flag for verbose logging

### Changed
- **Coverage Target**: Achieved 77% (was 59%)
- **Database Optimization**: Reduced multiple DB connection cycles in popup.py

### Fixed
- **Error Messages**: Improved with actionable suggestions across CLI

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
