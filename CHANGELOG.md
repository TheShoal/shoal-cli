# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.19.0] - 2026-03-07

### Added
- **Tool-native prompt delivery**: Three `input_mode` mechanisms in `ToolConfig` for initial session prompts — `"arg"` (positional CLI arg, e.g. `claude "prompt"`), `"flag"` (named flag, e.g. `opencode --prompt "prompt"`), `"keys"` (post-launch `send_keys`, legacy). For `omp`, `prompt_file_prefix="@"` writes to `~/.local/share/shoal/prompts/<session>.md` and passes `@/path` for native expansion. Eliminates TUI render race for initial prompts. Robo escalation uses `@file` for omp sessions to avoid garbling multi-line prompts. New `core/prompt_delivery.py` module with `write_prompt_file()` and `build_tool_command_with_prompt()`.
- **Status provider abstraction**: Explicit backend adapters in `core/status_provider.py` (`pi`, `opencode_compat`, `regex`) with tool-level selection via `tool.status_provider`
- **Detection mode visibility**: `shoal info` now shows a `Detection` field so sessions surface provider mode, including compatibility markers
- **Fin contract-v1 adapter**: New `shoal fin` command group with `inspect`, `validate`, and `run` subcommands for path-based fin execution
- **Fin runtime support**: Manifest parsing, contract-version checks, entrypoint resolution, subprocess invocation, and exit-code propagation in `services/fin_runtime.py`
- **Extension capability docs**: `docs/EXTENSIONS.md` adds discovery/loading/lifecycle map, gaps, and `shoal-cli` vs `shoal-core` boundary recommendation
- **Fin lifecycle completeness (Iteration 2)**: Added first-class `shoal fin install` and `shoal fin configure` commands with env/exit parity
- **Fin discovery basics**: Added `shoal fin ls [--path <dir-or-fin.toml>]` for path-based listing with valid/invalid manifest reporting
- **Cross-repo contract guard**: Added integration test that bootstraps a fin from `fins-template` and verifies inspect/validate/run roundtrip

### Changed
- **Pi-first defaults**: `default_tool` defaults now use `pi` in general config, robo config, profile loading, templates, and demo startup
- **Watcher pane tracking fallback**: watcher now falls back from `shoal:<session_id>` title to tool-command and single-pane heuristics when titles drift
- **Tool docs and examples**: README/tool examples now document Pi as primary and OpenCode as compatibility mode
- **Fin env handshake parity**: Fin subprocess runtime now passes `SHOAL_LOG_LEVEL` when available

### Fixed
- **Remote API robustness**: remote GET/POST/DELETE helpers now normalize connection reset OS errors into `RemoteConnectionError`
- **Flaky tests**: stabilized concurrent API load and Unix socket server tests for deterministic CI behavior
- **Lint regression**: removed explicit `return None` in robo watch test helpers (RET501)
- **mypy assignment error**: renamed shadowed `manifest` variable to `child_manifest` in `fin_runtime.py` to resolve `Path` vs `FinManifest` type conflict
- **Double `feat/` branch prefix**: extracted `infer_branch_name()` to `core/git.py` so the API server and MCP server no longer prepend `feat/` when input already carries a category prefix (e.g. `feat/foo` no longer became `feat/feat/foo`)
- **`send_keys` Enter racing TUI rendering**: added `send_keys_delay` float field to `ToolConfig` (default `0.0`); when non-zero, `async_send_keys` splits the text paste and Enter keypress into separate `asyncio.to_thread` calls with a configurable sleep in between
- **`shoal --version` flag**: Standard `--version` flag now supported in addition to `shoal version` subcommand; exits 0 with `shoal <version>` output
- **XDG directory naming**: Corrected `state_dir()` → `data_dir()` (`XDG_DATA_HOME`) and `runtime_dir()` → `state_dir()` (`XDG_STATE_HOME`) across 26 files; function names now match the XDG Base Directory spec
- **`shoal journal --archived` post-kill lookup**: Archived journals are now findable by session name after the session is deleted from DB; new `find_archived_session_id()` scans frontmatter title/aliases as fallback when DB resolution fails

## [0.18.0] - 2026-02-24

### Added
- **`shoal journal --archived <session>`**: Read archived journals from killed sessions with `read_archived_journal()` core helper, DB name resolution fallback, and Rich rendering
- **Nerd Font toggle**: `use_nerd_fonts` config flag in `GeneralConfig` (default `True`), wired through `_ls_impl` and `_status_impl` with Unicode fallback symbols
- **Feature documentation**: `docs/JOURNALS.md`, `docs/LOCAL_TEMPLATES.md`, `docs/HTTP_TRANSPORT.md` — standalone guides for shipped features
- **Lifecycle event system**: `LifecycleEvent` enum (`session_created`, `session_killed`, `session_forked`, `status_changed`) with async callback registry (`lifecycle.on()` / `lifecycle.emit()`)
- **Built-in lifecycle hooks**: Auto-journal entry on session create, fish event emission via `fish -c "emit shoal_status_changed <name> <status>"`
- **Fish event hook templates**: `hooks.fish` with `__shoal_on_status_changed` dispatcher and per-status handlers (`__shoal_on_waiting`, `__shoal_on_error`, `__shoal_on_created`, `__shoal_on_killed`), installed by `shoal setup fish`
- **Pre-commit agent bypass**: `SHOAL_AGENT=1` env var skips pre-commit hooks in Shoal-spawned agent sessions
- **`capture_pane` MCP tool**: Read last N lines from a session's terminal via `shoal-orchestrator` MCP server
- **`read_history` MCP tool**: Query status transition history for a session via `shoal-orchestrator` MCP server
- **`status_transitions` SQLite table**: Records every status change with session ID, from/to status, timestamp, and optional pane snapshot
- **`shoal history <session>` CLI**: Rich table showing status transition timeline with timestamps, color-styled statuses, and durations
- **Status change lifecycle hooks**: `_hook_record_status_transition` persists to DB; `_hook_journal_on_status_change` appends journal entries
- **Session graph fields**: `parent_id`, `tags`, `template_name` on `SessionState` — Pydantic defaults handle existing DB rows
- **`shoal tag` CLI subcommand**: `shoal tag <session> add/remove/ls` for managing session tags
- **`shoal ls --tag <tag>`**: Filter sessions by tag
- **`shoal ls --tree`**: Display fork relationships as indented tree with tree characters
- **`shoal journal --search <query>`**: Search across all session journals (case-insensitive substring match)
- **`JournalSearchResult`**: Dataclass for structured journal search results
- **Fork tracking**: `fork_session_lifecycle` records `parent_id` from source session
- **Template tracking**: `create_session_lifecycle` records `template_name` from template config
- **Enhanced `shoal info`**: Shows parent session, template name, and tags when present
- **Composition gateway spike**: `docs/composition-gateway.md` — FastMCP `mount()` investigation, decision no-go
- **Robo supervision loop**: `services/robo_supervisor.py` — async `RoboSupervisor` class with configurable poll loop, safe-to-approve pattern detection, auto-approve via tmux send_keys, timeout escalation, and journal decision logging
- **`shoal robo watch` CLI command**: Start the robo supervision loop for a named profile — loads `RoboProfileConfig`, prints config summary, runs in foreground or background daemon mode
- **Robo daemon mode**: `shoal robo watch --daemon` launches supervisor as background process with PID file management; `watch-stop` and `watch-status` commands for daemon lifecycle; profile-specific PID files (`robo-{profile}.pid`)
- **LLM escalation**: `_escalate_to_llm()` sends ambiguous waiting sessions to a configured LLM agent session via `send_keys`, polls journal for `robo-escalation-response` entries; `EscalationConfig` gains `escalation_session` and `escalation_timeout` fields; graceful fallback when no escalation session configured or on timeout
- **Fish completions**: Added `watch`, `watch-stop`, `watch-status` to robo subcommand completions
- **`shoal-robo-supervisor`**: New console script entry point for background daemon invocation

### Changed
- **Parallel test execution**: Added `-n auto` (pytest-xdist) to justfile `test` and `test-all` recipes
- **Tool-profile-aware `send_keys`**: MCP `send_keys` tool checks session tool profile for Enter handling behavior

### Fixed
- **Template env gap**: `template_cfg.env` now applied to the initial pane via fish `set -gx` commands sent before agent launch — `tmux set-environment` alone only affects subsequent panes, not the one created by `new-session`
- **send_keys Enter bug**: Use `-l` flag for literal text in tmux send-keys, then send Enter as a separate command — fixes key-name interpretation issues in Claude Code sessions
- **mypy strict**: Resolved type narrowing error in journal archived CLI (`str | None` assignment)

## [0.17.0] - 2026-02-24

### Added
- **Demo & onboarding overhaul**: Split monolithic `demo.py` (1249 lines) into `cli/demo/` package with `__init__.py`, `start_stop.py`, `tour.py`, `tutorial.py`
- **`shoal demo tutorial`**: Interactive 7-step guided walkthrough — creates real sessions, worktrees, journals, and diagnostics in `/tmp/shoal-tutorial/` with `typer.confirm()` pacing, `--cleanup` flag, `--step N` resume, and Ctrl+C crash recovery
- **Redesigned `shoal demo tour`**: 7 user-facing feature steps (was 9 internal verification steps) — Session Lifecycle, Status Detection, Templates & Inheritance, Journals, Diagnostics, MCP Orchestration, Theme & Status; each step is an independent async function returning `TourResult` dataclass
- **Next-step prompts**: `shoal init` shows "Get Started" panel; `shoal setup fish` shows tutorial/demo hints after install
- **Fish completions**: Added `tour` and `tutorial` to demo subcommand completions
- **Journal frontmatter**: Obsidian-compatible YAML frontmatter (`title`, `aliases`, `tags`, `created`) written on journal creation via `JournalMetadata` dataclass and `build_journal_metadata()` factory
- **Journal size warning**: Advisory 1MB threshold with `shoal.journal` logger warning after writes
- **`read_frontmatter()`**: Parse YAML frontmatter from journal files for future tooling
- **Logging infrastructure**: Named loggers for 8 previously silent modules (`db`, `tmux`, `git`, `config`, `detection`, `mcp_pool`, `mcp_proxy`, `status_bar`) with targeted DEBUG/WARNING statements
- **Context propagation**: `core/context.py` with `ContextVar`-based `session_id` and `request_id` propagation; `ContextFilter` wired into CLI, watcher, and lifecycle
- **Request ID middleware**: FastAPI `RequestIdMiddleware` reads/generates `X-Request-ID` header on all API requests
- **`shoal diag` command**: Diagnostics command checking DB connectivity, watcher PID, tmux reachability, MCP sockets; supports `--json` output
- **Structured logging**: `JsonFormatter` for JSON-lines output; `--log-level`, `--log-file`, `--json-logs` CLI flags via `configure_logging()`
- **Operation timing**: `time.monotonic()` timing at DEBUG level for DB operations (`save_session`, `get_session`, `list_sessions`, `update_session`, `delete_session`) and MCP pool connections
- **Deepened `/health` endpoint**: Returns component-level status (`db`, `watcher`, `tmux`) with `healthy`/`degraded` overall status
- **XDG Base Directory compliance**: `config_dir()`, `state_dir()`, `runtime_dir()` read `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` respectively; `build_nvim_socket_path()` reads `XDG_RUNTIME_DIR`
- **`shoal remote` subcommand group**: 7 commands for remote session management via SSH tunnel — `ls`, `connect`, `disconnect`, `status`, `sessions`, `send`, `attach`
- **SSH tunnel lifecycle**: `core/remote.py` with PID/port file management, auto port selection, tunnel health checks
- **`RemoteHostConfig`**: Pydantic model for remote hosts in `~/.config/shoal/config.toml` (`[remote.<name>]` sections)
- **Remote HTTP client**: stdlib `urllib.request`-based API client (GET/POST/DELETE) — no new dependencies
- **Fish completions**: Remote subcommands and dynamic host name completions
- **Transport evaluation spike**: Benchmark comparing UDS byte bridge vs FastMCP HTTP transport ([docs/transport-spike.md](docs/transport-spike.md))
- **`shoal-mcp-server --http`**: HTTP (streamable-http) transport mode for the Shoal MCP server
- **Benchmark script**: `benchmarks/transport_spike.py` for self-contained transport performance comparison

### Changed
- **Demo tour**: Reduced from 9 steps to 7, removed developer-facing tests (Pydantic validation, exception hierarchy, MCP name regex), added Journals and Diagnostics steps
- **Demo pane content**: Updated command references to include `shoal demo tutorial`
- **Ghost session wording**: `shoal ls` now shows "was running" instead of "running" for ghost sessions
- **`mcp status` hint**: Suggests `shoal mcp doctor --cleanup` instead of manual `mcp stop` for stale entries
- **Fish completions**: `__shoal_tools`, `__shoal_templates`, `__shoal_remote_hosts` use `$XDG_CONFIG_HOME` instead of hardcoded `~/.config`
- **Status bar**: `status_bar.py` returns dict of counts, `main()` prints JSON; removed `tmux_fg`/`tmux_status_segment` from theme
- **`mcp doctor`**: Replaced manual JSON-RPC probe with FastMCP Client for protocol-aware health checks
- **`mcp doctor` table**: New columns (PROTOCOL, TOOLS, VERSION, LATENCY) replace old SOCKET + JSON-RPC columns
- **Graceful fallback**: `mcp doctor` shows "skip" with install hint when `fastmcp` is not installed

### Removed
- Dead `state_dir` field from `GeneralConfig` model (never read anywhere)

### Fixed
- **Async-unsafe prune**: `_prune_impl()` now calls `archive_journal()` via `asyncio.to_thread()` instead of blocking the event loop
- **Nerd Font glyphs**: Populated all 5 `STATUS_STYLES` nerd fields (were empty strings)
- **Demo branch detection**: `demo-main` and `demo-robo` sessions now correctly pass `branch=` to `create_session()`
- **Tour MCP skip**: Step 8 (MCP Orchestration) now shows "skipped" instead of false pass when `fastmcp` is not installed
- **`mcp doctor --cleanup`**: New flag to remove stale PID/socket files for dead MCP servers
- **CORS configuration**: Changed `allow_credentials=True` to `allow_credentials=False` — invalid per CORS spec when `origins=["*"]`
- **SSH credential redaction**: `_redact_ssh_cmd()` replaces identity file paths with `<redacted>` in remote tunnel logs
- **Watcher error backoff**: Exponential backoff on consecutive poll failures (`_MAX_BACKOFF=300s`), reset on success
- **Watcher logging**: Replaced `logging.basicConfig` with named `FileHandler` to avoid conflicts with CLI logging
- **Bandit B310**: Added `# nosec B310` to intentional localhost-only `urlopen()` calls in `remote.py`
- **MCP proxy Python 3.13 compatibility**: Replaced `BaseProtocol` with `StreamReaderProtocol` for stdout write pipe — `StreamWriter` requires `_drain_helper` from `FlowControlMixin` which `BaseProtocol` lacks on Python 3.13+
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
