# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [0.32.0] - 2026-04-01

### Added
- **Agent Teams**: Create sessions that spawn nested parallel agent sub-sessions for wide tasks using `shoal create --team`. Supported by a new `CoordinatorSession` abstraction.
- **Journal Dreaming**: Agent sessions now compress past findings into the main session loop.

## [0.31.4] - 2026-04-01

### Fixed
- Fix broken mermaid markup on docs homepage


## [0.30.0] - 2026-04-01

### Added
- **Claw runtime provider**: Shoal now manages lobster-party Claw sessions via gRPC.
  `RuntimeKind.claw` with full `ClawRuntimeProvider` implementing all 13 Protocol methods.
  `ClawRuntimeState` (claw_id, endpoint, employee_id) joins `TmuxRuntimeState` in the
  `AnyRuntimeState` discriminated union with `SessionState.tmux_runtime` for type narrowing.
  `ClawConfig` model for `[claw]` config.toml section. `create_claw_session_lifecycle()` for
  Claw session creation without tmux/worktree. New `claw` optional dep group:
  `grpcio>=1.60`, `grpcio-tools>=1.60`, `protobuf>=4.25`.
- **MCP ↔ A2A bridge**: 5 new `shoal-orchestrator` MCP tools for cross-system agent
  collaboration: `send_to_claw` (gRPC Turn with streaming), `claw_status` (single or batch),
  `list_claws` (enumerate known Claws from config), `claw_health` (liveness check),
  `sync_claw_conversations` (import/export/both QMD↔journal). MCP server now exposes 23 tools.
- **Conversation/journal sync**: `core/claw_conversations.py` reads lobster-party QMD files
  (YAML frontmatter + JSON turns). `import_claw_turns()` appends new turns to session journals;
  `export_journal_to_qmd()` writes Shoal journals to QMD format. `shoal sync <session>` CLI
  command with `--direction` flag (import/export/both).
- **Lobster Party proto stubs**: Generated protobuf/gRPC stubs committed to
  `src/shoal/core/proto/` (lobster_loop, a2a_core, a2a_claw, delegation). Regenerate with
  `just gen-protos` when protos change.
- **Integration spec**: `INTEGRATION.md` documents the full Shoal × Lobster Party ×
  Smorgasbord integration architecture and data flow.

## [0.29.0] - 2026-03-31

### Added
- **MCP tools for robo workflows**: `mark_complete` (agents signal task completion),
  `read_worktree_file` (supervisors read worker output files with path traversal
  protection), `list_worktree_files` (enumerate worktree contents). MCP server
  now exposes 18 tools.
- **PyApp binary distribution**: Self-contained `shoal` binary via PyApp packaging.
  Homebrew formula at `TheShoal/tap/shoal-cli`.
- **omp as default tool**: Replaced `pi` with `omp` (oh-my-pi) as the default tool
  across `GeneralConfig`, robo profiles, mode presets, and templates.

### Changed
- **Deferred CLI imports**: All subcommand modules now use lazy imports via thin
  wrappers in `cli/__init__.py`, improving `shoal --help` startup latency.
- **Config model split**: Monolithic `models/config.py` refactored into focused
  submodules (`models/config/general.py`, `tools.py`, `templates.py`, `hooks.py`,
  `workspace.py`, `robo.py`). Public API unchanged via `__init__.py` re-exports.

### Fixed
- Default tool assertions in tests updated for omp default.

## [0.28.0] - 2026-03-31

### Added
- **Flagship fleet demo**: `shoal demo fleet` runs a 6-step scripted showcase —
  planner → implementer → reviewer → supervisor escalation → overnight progress
  → morning fleet summary. Uses real sessions, worktrees, journals, and handoff
  artifacts in a scratch repo.
- **Shoal-native skills**: `SkillConfig` model, `discover_skills()` searches
  `.shoal/skills/` (project-local) and `~/.config/shoal/skills/` (global) with
  local-wins dedup. `shoal skill ls` command. Auto-symlink into `.claude/skills/`
  for Claude Code sessions on worktree creation.
- **Project-level `.shoal.toml`**: Committed config at git root with `[env]`,
  `setup_commands`, `default_tool`, `default_template`. Precedence: project <
  template < CLI flags.
- **Cross-agent skill setup**: OpenCode agents (`.opencode/agents/`), omp skills
  (`.omp/skills/`), and rules for both tools. Parity with Claude Code skills.
  New docs: `OPENCODE_SETUP.md`, `OMP_SETUP.md`.
- **`claude-review` template**: Review-oriented Claude session for reviewer mode.

### Fixed
- **`send_keys` pane targeting**: `shoal:<session_id>` title was set on the active
  pane (terminal) instead of the agent pane (first pane) in multi-pane templates.
  Now uses `first_pane()` for both create and fork lifecycle paths.
- **GitHub Actions Node.js 24**: Bumped checkout v6, setup-python v6, setup-uv v7,
  codeql-action v4, upload-pages-artifact v4.

### Changed
- **CLI reference docs**: Added `shoal handoff`, `handoff-ls`, `mode ls`, `done`,
  `incident` commands. AGENTS.md added to mkdocs nav. Workspace routing
  documented in LOCAL_TEMPLATES.md.

## [0.27.0] - 2026-03-31

### Added
- **Meta-repo workspace routing**: `.shoal/workspace.toml` manifest maps logical names
  to sub-repo paths for nested workspace support (SMORGASBORD §3.1). `--repo` CLI/API
  flag for explicit targeting. Auto-match by worktree hint or path prefix.
- **Structured handoff packets**: `HandoffArtifact` enriched with worktree path, git diff
  summary, and commit count. `to_dict()` for JSON serialization. Auto-generated on every
  `shoal kill` (before journal archival). New `shoal handoff <session>` command with
  `--json` and `--save` flags. `shoal handoff-ls` lists saved artifacts.
- **Operating modes**: Data-driven `MODE_REGISTRY` with `ModeSpec` replacing hardcoded
  if/elif chain. Three new modes: `planner`, `implementer`, `reviewer`. `shoal mode ls`
  command. Modes auto-tag sessions (e.g., reviewer → `review-ready` urgency tier).
- **Template `tags` and `mode` fields**: `SessionTemplateConfig` gains `tags: list[str]`
  (union-merged during inheritance) and `mode: str`. Auto-applied to sessions at creation.
- **Branch categories**: `plan`, `impl`, `review`, `batch` added to allowed branch prefixes.
- **Git helpers**: `diff_stat()`, `commit_count_since_main()` with async wrappers.
- **Cross-agent skills**: `.shoal/skills/<name>/SKILL.md` tool-agnostic skill format with
  transpilation to Claude Code (symlink), OpenCode (instructions), and omp (`@file`).
  Bundled `shoal-skill-sync.sh` script for `post_worktree_create` hook.
- **`claude-review` template**: Review-oriented Claude session with `review-ready` tagging.
- **Docs**: New "Handoffs & Modes" and "Cross-Agent Skills" mkdocs pages. Updated CLI
  reference, JOURNALS, LOCAL_TEMPLATES, operator playbooks, and AGENTS docs (Bedrock
  section, workspace.toml, missing commands).

### Fixed
- Template inheritance now merges `mode` and `tags` fields (previously dropped).
- Template TOML parser now extracts `mode` and `tags` from `[template]` section.
- Handoff generation runs before DB row deletion (was after, risking empty transitions).
- `generate_handoff()` wrapped in `asyncio.to_thread()` to avoid blocking event loop.
- Path traversal validation on workspace repo paths (rejects `..` and absolute paths).
- `shoal new <nonexistent-path>` no longer crashes with raw traceback; shows friendly
  error with `--name` hint (TheShoal/shoal-cli#7).

## [0.26.0] - 2026-03-30

### Added
- **Incident supervision workflow**: `shoal incident ingest/ls/show/spawn/resolve` commands
  for alert-driven multi-agent coordination. `ingest` accepts a JSON alert payload (file,
  string, or stdin), persists an `IncidentRecord` to SQLite, and auto-spawns a supervisor
  lane unless `--no-supervisor` is passed.
- **Incident roles**: five first-class roles (`incident-supervisor`, `incident-investigator`,
  `incident-repro`, `incident-comms`, `incident-reviewer`) with role-specific prompts and
  lifecycle env injection (`SHOAL_INCIDENT_ID`, `SHOAL_INCIDENT_ROLE`, `SHOAL_SESSION_ID`).
- **Incident REST API**: `GET /incidents`, `GET /incidents/{id}`, `POST /incidents`,
  `POST /incidents/{id}/lanes`, `POST /incidents/hooks/claude` — full programmatic access
  to incident state and lane spawning.
- **Claude hook integration**: `shoal incident hook-scaffold` writes example
  `TaskCreated`/`TaskCompleted`/`StopFailure` hook files; `shoal incident hook-report`
  (hidden) ingests hook events via `/incidents/hooks/claude`.
- **Remote incident commands**: `shoal remote incident ls/show/ingest/spawn` proxy to
  incident endpoints on remote hosts via existing SSH tunnel forwarding.
- **`post_worktree_create` template field**: `[template.worktree] post_worktree_create`
  executes a script after git worktree provisioning, before agent startup. Script receives
  the worktree absolute path as `$1`. Relative paths resolve against the git root.
- **Project-local lifecycle hooks** (`.shoal/hooks.toml`): `[[hooks]]` entries bind shell
  commands to lifecycle events with optional `when_status` filter. Executed via `asyncio.to_thread`
  with 30s timeout; injects `SHOAL_EVENT`, `SHOAL_SESSION_ID`, `SHOAL_SESSION_NAME`,
  `SHOAL_OLD_STATUS`, `SHOAL_NEW_STATUS`. Loaded at API startup from project git root.

### Fixed
- **Lifecycle hooks never fired in production**: `register_builtin_hooks()` was only
  called in tests, never at API startup — fish events and journal writes were silently
  broken since v0.18.0. Fixed by wiring both `register_builtin_hooks()` and
  `register_project_hooks()` into the API `lifespan` context.
- **Prompt file path traversal**: session names containing `/` (e.g. `repo/incident-worker`)
  would produce invalid file paths. Path separators are now replaced with `-` before
  constructing the prompt filename.

## [0.25.0] - 2026-03-18

### Changed
- **Session runtime model**: `SessionState` now stores a canonical nested `runtime` object instead of leaking tmux-specific fields (`tmux_session`, `tmux_session_id`, `tmux_window`, `nvim_socket`) at the top level
- **Runtime provider architecture**: added `services/runtime_provider.py` and `services/runtime_providers/tmux.py`; lifecycle, watcher, CLI, API, MCP, and robo flows now dispatch through the runtime provider seam instead of hard-coding tmux operations across the codebase
- **Batch/API/MCP runtime payloads**: session info and snapshot surfaces now return `runtime` metadata as a provider-tagged object rather than a flat `tmux_session` string

### Fixed
- **Legacy session migration**: SQLite-backed session blobs created before the refactor are eagerly migrated into the nested runtime shape on load/startup, so existing sessions survive the v0.25.0 cutover without manual cleanup
- **Robo and operator flows after abstraction**: `shoal info`, `shoal send`, `shoal robo send`, `shoal robo approve`, and related capture/attach flows now continue to work against live tmux-backed sessions through the provider boundary

## [0.24.1] - 2026-03-18

### Fixed
- **`shoal done` hangs on exit**: missing `with_db()` wrapper in CLI; aiosqlite background thread was never released, leaving the process hanging indefinitely after marking a session complete
- **`fin install <url>` raw traceback**: `httpx.ConnectError`, `HTTPStatusError`, and other network errors escaped uncaught from `_download_fin()`; now wrapped as `FinRuntimeError` with a clean one-line error message
- **`httpx` missing from core dependencies**: `models/fin.py` imports `httpx` unconditionally but it was only available via the `[mcp]` extra; added to `dependencies` so bare installs work
- **`__version__` stale at `0.22.0`**: hardcoded value not updated during v0.24.0 release; now correctly reports `0.24.1`

## [0.24.0] - 2026-03-18

### Added
- **Worker completion signals**: `session_completed` lifecycle event, `shoal done [--summary]` CLI command, `completed_at` on `SessionState`, `wait_for_completion` MCP tool
- **Git MCP tools**: `branch_status` and `merge_branch` backed by `services/git_tools.py` — robo supervisors no longer need raw `send_keys` for git ops
- **`fin install` remote source**: accepts HTTPS URLs and `fin:<name>[@<version>]` registry shorthand; `--registry-url` flag added

### Changed
- **`session_snapshot` default `pane_lines`**: 20 → 50
- **`create_session` validation**: `branch=True` without `worktree` now raises a clear error
## [0.23.0] - 2026-03-09

### Added
- **Urgency-based operator board**: Sessions now carry a `status_since: datetime` field tracking when they entered their current status. A new `core/urgency.py` module derives `UrgencyTier` (error → blocked → waiting → review → running → stale → idle → stopped) and a human-readable label from `status + status_since`. Thresholds are configurable via `[operator] blocked_after_minutes` and `stale_after_minutes` in `config.toml` (defaults: 5m / 30m). Existing sessions are backfilled from `status_transitions` history on first startup.
- **`shoal status` attention-first layout**: Output is now grouped into four tiers — **Needs attention** (error/blocked/waiting), **Ready for review**, **Active** (running), and **Background** (idle/stale/stopped). Each session shows an urgency label with age (`blocked 8m`, `stale 2h`). Sessions that need you appear first; stopped sessions are last.
- **`shoal popup` urgency sort**: Popup entries are pre-sorted by urgency tier before being piped to fzf, so the most urgent sessions appear at the top regardless of `--no-sort` being set. The status column shows the urgency label instead of the raw status value. `ctrl-w` attention filter now matches `error`, `blocked`, and `waiting` labels.
- **`shoal journal <session> --handoff`**: Generates a structured markdown handoff summary — session metadata, time in current status, last 5 status transitions with timestamps, up to 5 recent journal entries, and a suggested next action keyed to the urgency tier (attach, send keys, review diff, etc.). Pure function `generate_handoff()` in `core/journal.py` with full test coverage.

### Changed
- **`SessionResponse` and MCP `session_info`**: Both now include `status_since` in their output.

## [0.22.0] - 2026-03-07

### Added
- **`shoal init --refresh-tools`**: Re-downloads all built-in tool profiles to `~/.config/shoal/tools/` without touching custom profiles. Useful after upgrading to pick up revised defaults.
- **Auto-commit on kill**: New `general.auto_commit = true` in `config.toml`. When enabled, stages all changes and creates a conventional commit in the session worktree before teardown. Runs before optional worktree removal — a combined `auto_commit + remove_worktree` commits first then removes cleanly. Failures are logged and do not block the kill.
- **Dashboard fzf actions**: `ctrl-y` approves agent prompt, `ctrl-g` forks session into a new worktree, `ctrl-w` filters to waiting sessions, `ctrl-r` reloads the session list. Bindings avoid tmux leader (`ctrl-a`) and tmux fullscreen (`ctrl-f`) conflicts.
- **Fin local registration**: `shoal fin install` now registers fins in `~/.config/shoal/fins/` by default. `shoal fin ls` defaults to showing installed fins. Pass `--no-register` to `install` to skip registration, or `--path` to `ls` for path-based listing.

### Changed
- **`load_tool_config` now reads all tool fields**: `send_keys_delay`, `input_mode`, `prompt_flag`, and `prompt_file_prefix` from the `[tool]` TOML section were silently ignored. All four are now correctly propagated to `ToolConfig`. Built-in tool profiles updated with `send_keys_delay = 0.05`.

### Fixed
- **tmux pane targeting with non-default `base-index`**: Sessions on tmux configs with `base-index=1` saw every startup command fail — `send-keys -t session:0.0` targeted a non-existent pane. Shoal now queries the live tmux server and offsets all window/pane targets by the actual base-index. Affected: template setup loops, initial pane in `create_session`/`fork_session`, and the MCP `wait_for_ready` probe.
- **Kill guard blocking on untracked-only worktrees**: `DirtyWorktreeError` fired when a worktree had only untracked files (e.g. a stray `TASK.md`). The guard now checks tracked changes only (`??` lines excluded from `git status --porcelain`).
- **`shoal ls` ID column truncated to 1 char**: Compressed inside Rich panels on standard-width terminals. Fixed with `no_wrap=True`, `expand=True` on the table, and bounded `max_width` on name/status/path columns.

## [0.21.0] - 2026-03-07

### Changed
- **PyPI package name**: Project published as `shoal-cli` on PyPI. Install with `pipx install shoal-cli` or `uv tool install shoal-cli`. The CLI command remains `shoal`.
- **pyproject.toml metadata**: Added `authors`, `keywords`, `classifiers` (Development Status :: 4 - Beta), and `[project.urls]` (Homepage, Documentation, Repository, Issues, Changelog).
- **GitHub Actions release workflow**: Added `publish` job with OIDC trusted publisher support (`pypa/gh-action-pypi-publish`) — runs after GitHub Release is created.
- **Default backend docs**: CONTRIBUTING.md and ARCHITECTURE.md updated to document Pi as the primary reference backend; OpenCode referenced as compatibility mode.
- **Install docs**: README and getting-started.md now show `pipx install shoal-cli` / `uv tool install shoal-cli` as the primary install path; from-source instructions moved to secondary.

### Fixed
- **Flaky `test_post_success`**: `_MockHandler.do_POST` in `tests/test_remote.py` now reads the request body before responding, eliminating a connection-reset race that caused intermittent CI failures under parallel test execution.
## [0.20.0] - 2026-03-07

### Added
- **Template `setup_commands`**: New `setup_commands: list[str]` field on `SessionTemplateConfig` and `TemplateMixinConfig` — commands run via `send-keys` in the initial pane before the agent tool launches. Canonical use-case: venv activation (`uv sync`, `source .venv/bin/activate.fish`). Inheritance: `extends` replaces, `mixins` append. (+266 lines: `models/config.py`, `core/config.py`, `services/lifecycle.py`, 243 lines of tests).
- **Batch MCP session operations**: `capture_pane`, `send_keys`, `kill_session`, and `session_status` MCP tools now accept `session: str | list[str]`. String input returns the same shape as before (backwards-compatible); list input returns `{"results": {name: per-session-result}}` with per-session errors collected rather than raised.
- **Agent readiness signals**: Replaced `asyncio.sleep(1)` after session creation with `async_wait_for_ready(pane, tool_cfg, timeout=5.0)` in `core/tmux.py` — polls capture_pane every 100ms until the tool's busy/waiting detection patterns appear or timeout is reached. Returns `False` immediately when no patterns are configured.

### Fixed
- **Orphaned worktree detection**: `wt cleanup` now detects orphaned worktrees in `$CWD/.worktrees/` even when no sessions exist in the DB for the current repo — critical for post-kill cleanup flows where all sessions have been removed.
- **Test CWD isolation**: Pre-existing `test_wt_cleanup_no_orphans` and `test_wt_cleanup_with_orphans` now `monkeypatch.chdir(tmp_path)` to prevent the new CWD fallback from leaking real `.worktrees/` state into unit tests.
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

## [0.4.0] – [0.15.0] (2026-02-16 – 2026-02-22)

Foundation releases — SQLite + WAL migration, async-first core, lifecycle service with
rollback, git worktree isolation, fish shell integration, MCP pool with pure-Python bridge,
template inheritance and mixins, robo supervisor rename, pre-commit/CI framework,
mypy --strict, ruff lint expansion, FastMCP-based `shoal-orchestrator` MCP server.
Coverage grew from 52% (96 tests) to 82% (618 tests). See `git log v0.4.0..v0.15.0`
for full details.
