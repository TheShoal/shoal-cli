# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

> **Release history**: See [CHANGELOG.md](CHANGELOG.md) for completed releases (v0.4.0–v0.20.0).

## v0.15.0: FastMCP Integration

**Priority: expose Shoal orchestration as MCP tools so agents can call Shoal natively.**

### Phase 1 — Shoal MCP server

- [x] Add `fastmcp>=3.0.0` as optional dependency
- [x] Create `mcp_shoal_server.py` with tools: list_sessions, send_keys, create_session, kill_session, session_status, session_info
- [x] Register `shoal-orchestrator` in default MCP server registry
- [x] Template support for robo workflows

### Phase 2 — Protocol-aware health checks

- [x] Replace manual JSON-RPC probe in `mcp doctor` with FastMCP Client
- [x] Better error diagnostics from protocol-level failures

### Phase 3 — Transport evaluation (spike)

- [x] Investigate FastMCP UDS transport support
- [x] Measure HTTP vs UDS performance for MCP traffic
- [x] Decide go/no-go for byte bridge replacement
- See [docs/transport-spike.md](docs/transport-spike.md) for full findings

## v0.16.0: Remote Sessions

**Priority: monitor and control agents running on remote machines via SSH tunnel + HTTP client.**

### Phase 1 — Documentation + fish wrapper

- [x] Ship `shoal-remote` fish function wrapping SSH
- [x] Document remote usage patterns

### Phase 2 — `shoal remote` subcommand group

- [x] `shoal remote connect/disconnect` — SSH tunnel management
- [x] `shoal remote status/ls` — HTTP GET via tunnel, Rich-formatted
- [x] `shoal remote send/attach` — interact with remote sessions
- [x] Remote host config in `~/.config/shoal/config.toml`

### Phase 3 — Status bar integration (deferred)

- [ ] Fish status bar polls remote WebSocket for session status

## v0.17.0: Demo Overhaul, Diagnostics & Observability

**Priority: onboarding experience, operational visibility, and developer ergonomics.**

- [x] Demo & onboarding overhaul — split monolithic `demo.py` into `cli/demo/` package
- [x] `shoal demo tutorial` — interactive 7-step guided walkthrough
- [x] Redesigned `shoal demo tour` — 7 user-facing feature steps
- [x] `shoal config show` and `shoal mcp registry` — config introspection commands
- [x] `shoal diag` — diagnostics command (DB, watcher, tmux, MCP sockets)
- [x] Logging infrastructure — named loggers for 8 modules, structured JSON output
- [x] Context propagation — `ContextVar`-based session/request ID threading
- [x] Request ID middleware — `X-Request-ID` on all API requests
- [x] Journal frontmatter — Obsidian-compatible YAML metadata on creation
- [x] Project-local templates — `.shoal/templates/` search path in git root
- [x] Structured session journals — append-only markdown with archive on kill
- [x] FastMCP HTTP transport default for `shoal-orchestrator`
- [x] Remote sessions — `shoal remote` subcommand group (7 commands via SSH tunnel)
- [x] XDG Base Directory compliance across config/state/runtime paths
- [x] `extra="forbid"` on config models; `ConfigLoadError` for TOML parse errors

## v0.18.0: Lifecycle Hooks, Observability & Robo Supervisor

**Priority: event-driven architecture, agent observability, and autonomous supervision.**

### Phase 1 — Lifecycle Hooks (foundation)

- [x] `LifecycleEvent` enum: `session_created`, `session_killed`, `session_forked`, `status_changed`
- [x] Async callback registry on lifecycle service (`lifecycle.on()` / `lifecycle.emit()`)
- [x] Fish event emission — `emit shoal_status_changed <name> <status>` after Python hooks fire
- [x] Built-in hooks: auto-journal entry on session create, status transition logging
- [x] `shoal setup fish` installs example hook templates (`__shoal_on_waiting`, etc.)
- [x] Fix `send_keys` in MCP server to auto-append Enter for Claude Code tool profile
- [x] Pre-commit hook bypass strategy for Shoal-spawned agent sessions

### Phase 2 — Agent Observability

- [x] `capture_pane` MCP tool + underlying Python function (read last N lines from a session's terminal)
- [x] `status_transitions` SQLite table — `(session_id, from_status, to_status, timestamp, pane_snapshot)`
- [x] Journal auto-entries for status changes (written via lifecycle hook)
- [x] `shoal history <session>` CLI command — status timeline with durations
- [x] New MCP tools: `capture_pane`, `read_history`
- [x] Server Composition Gateway investigation (FastMCP `mount()`) — no-go, deferred to backlog. See [docs/composition-gateway.md](docs/composition-gateway.md)

### Phase 3 — Session Graph

- [x] `parent_id`, `tags`, `template_name` fields on `SessionState`
- [x] `shoal tag <session> add/remove <tag>` command
- [x] `shoal ls --tag <tag>` and `shoal ls --tree` (fork relationships)
- [x] `shoal journal search <query>` across all session journals
- [x] Fork tracking: `fork_session_lifecycle` records `parent_id`

### Phase 4 — Robo Supervision Loop

- [x] `services/robo_supervisor.py` — async programmatic supervision loop
- [x] Wire up `auto_approve`, `poll_interval`, `waiting_timeout` from robo config
- [x] Pattern-based safe-to-approve detection (reads pane content, checks against patterns)
- [x] LLM escalation: ambiguous cases escalated to robo agent session via MCP tools
- [x] Robo journal: logs every decision (approved, escalated, timed out)
- [x] `shoal robo watch` — start the supervision loop (foreground + background daemon mode)

### Design Decisions

- **Hook architecture**: Code-level async callbacks (internal) + fish event emission (external). Python hooks handle infrastructure (journal, DB, robo). Fish events let users customize behavior without writing Python — `notify-send`, ntfy webhooks, custom scripts via `--on-event`.
- **Status history**: Both SQLite table (programmatic queries, robo decision-making) and journal entries (human-readable narrative). Written by a single lifecycle hook.
- **Robo autonomy**: Layered — deterministic Python loop handles simple cases (auto-approve known-safe prompts, timeout escalation). Ambiguous cases escalated to LLM agent session. Programmatic layer uses Python API directly; LLM layer uses MCP tools (each interface used where it's designed for).
- **MCP interface principle**: MCP is the agent interface, Python is the infrastructure interface. They share the same underlying functions. Programmatic code calls Python directly; LLM agents call MCP tools.

## v0.19.0

Released 2026-03-07

- **`--version` flag**: Added `shoal --version` / `shoal version` CLI command
- **XDG directory naming**: Renamed `state_dir()` → `data_dir()` and `runtime_dir()` → `state_dir()` to match XDG spec; updated all callers
- **Archived journal lookup**: `shoal journal <name>` now searches archived sessions too; added `shoal history <name>` command for status transition history
- **Branch naming**: Extracted `infer_branch_name()`, `validate_branch_name()`, `ALLOWED_BRANCH_CATEGORIES` to `core/git.py`; fixed double `feat/` prefix bug

## v0.20.0

Released 2026-03-07

- **Template `setup_commands`**: New `setup_commands: list[str]` field on `SessionTemplateConfig` and `TemplateMixinConfig`; commands run via `send-keys` before agent launch
- **Orphaned worktree detection**: `wt cleanup` now detects orphaned worktrees in CWD even when no sessions exist for that repo in the DB
- **Agent readiness signals**: Replace `asyncio.sleep(1)` hack with poll-until-pattern readiness check; new `async_wait_for_ready()` helper in `core/tmux.py`
- **Batch MCP operations**: `send_keys`, `capture_pane`, `session_status`, `kill_session` now accept `session: str | list[str]`; batch input returns `{"results": {name: data}}`


## v0.21.0

Released 2026-03-07

- **PyPI publish**: Package name `shoal-cli` on PyPI; `pipx install shoal-cli` / `uv tool install shoal-cli` as primary install path
- **pyproject.toml metadata**: Added `authors`, `keywords`, `classifiers` (Development Status :: 4 - Beta), and `[project.urls]`
- **PyPI trusted publisher**: `.github/workflows/release.yml` publish job using OIDC via `pypa/gh-action-pypi-publish`
- **README badge/copy refresh**: Version badge v0.21.0-beta, test count 1087, ecosystem note removed, status table updated through v0.21.0
- **Docs copy fixes**: CONTRIBUTING.md and ARCHITECTURE.md stack reference updated to Pi as primary; getting-started.md PyPI install as primary

## Backlog

### Worktree & Environment Initialization

> Full design: [docs/WORKTREE_ENV_INIT.md](docs/WORKTREE_ENV_INIT.md)

- **Template `setup_commands`** (feature): New `setup_commands: list[str]` field on `SessionTemplateConfig` and `TemplateMixinConfig`. Commands run via `send-keys` in the initial pane before the agent launches. Canonical answer for venv activation (`uv sync`, `source .venv/bin/activate.fish`). Inheritance: extends=replace, mixins=append. Files: `models/config.py`, `services/lifecycle.py`, `docs/LOCAL_TEMPLATES.md`
- **Project-level `.shoal.toml`** (feature, lower priority): Committed config at project root with `[env]` and `[setup]` sections. Precedence: `.shoal.toml` < `template.env` < CLI flags. Discovered via `git_root`. Files: `core/config.py`, `services/lifecycle.py`
- **direnv/mise integration** (deferred): Opt-in `env_manager` field on templates. NEVER auto-detect `.envrc`/`mise.toml` — explicit opt-in only.

### Other

- **Linux notifications**: Solved by fish event hooks — users wire `notify-send` or ntfy in their fish config
- **Dashboard actions**: Add fork, approve, send-keys, filter-by-status as fzf popup actions
- **Agent readiness signals**: Poll-until-pattern readiness check replacing `asyncio.sleep(1)` hack after session creation
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()` — investigated, no-go for now ([spike findings](docs/composition-gateway.md)). Revisit when robo supervisor needs unified cross-session MCP or FastMCP adds UDS transport
- **Oh-My-Pi (omp) Integration**: `omp.toml` tool definition and `omp-dev` session template; native MCP via `omp plugin`; detection pattern tuning for omp's extended TUI
- Remote status bar: Fish status bar polls remote WebSocket for session status
- **Auto-commit on session idle/kill**: Workers should automatically commit their changes when they finish working. Implement as a lifecycle hook (`session_killed`, `status_changed → idle`) that runs `git add -A && git commit` in the session's worktree. Should be user-configurable — `auto_commit` bool in `[template.git]` or `GeneralConfig` (default on in templates, off globally). Consider: commit message generation (conventional commit from diff summary vs. agent-provided), dirty worktree guard on kill already exists (`DirtyWorktreeError`), opt-out for sessions where manual review is preferred. Related to robo merge workflow and per-session git practices below.
- **Robo merge/worktree workflow**: Document merge-back-to-main lifecycle for robo supervisor — concrete instructions in default `AGENTS.md` template and ROBO_GUIDE section covering: branch readiness checks, test verification before merge, safe auto-merge patterns vs. human review, worktree cleanup after merge, and post-session branch deletion. Consider dedicated MCP tools (`merge_branch`, `branch_status`) so robo doesn't need raw `send_keys` for git operations.
- **Batch MCP commands**: Adapt existing MCP tools (`send_keys`, `session_status`, `kill_session`, `capture_pane`, etc.) to accept lists of sessions for batch operations. Add batch variants or overload existing tools to handle `session: str | list[str]` — enables robo supervisors and orchestrators to approve/kill/query multiple sessions in a single MCP call instead of N sequential calls. Consider a `batch_execute` meta-tool that takes `[(tool, params), ...]` for arbitrary batching.
- **Per-session git practices**: Unblocked once template env gap is fixed — support git identity and conventions per session via `[template.env]` (`GIT_AUTHOR_NAME`, `GIT_COMMITTER_EMAIL`). Longer-term: dedicated `[template.git]` section for commit conventions, hook profiles, and branch naming rules — enabling different practices for admin agents, robo supervisors, and task workers.
- **Fins (extension system)**: Plugin/extension architecture for Shoal — let users and third parties extend functionality without modifying core. Consider: custom tool profiles, lifecycle hook packages, MCP server bundles, CLI subcommand plugins, and template libraries as installable Fins. Design decisions: discovery mechanism (entry points vs config registry), sandboxing, API surface contract, naming (`shoal fin install`, `shoal fin ls`). Look at FastMCP's plugin patterns and Click's plugin system for inspiration.

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-03-07 — Onboarding docs refresh + send_keys_delay defaults

**What we did:**

- `docs/index.md`: added `pipx install shoal-cli` as the first step in the sixty-second workflow; switched example agents to `omp`
- `docs/getting-started.md`: fixed step-grid install hint (was `uv tool install .` local path); removed duplicate `fish` entry from optional prereqs
- `CONTRIBUTING.md`: replaced stale `uv pip install -e ".[dev]"` with `uv sync --extra dev --extra mcp`
- `docs/TROUBLESHOOTING.md`: `pip install neovim-remote` → `pipx install neovim-remote`
- `examples/config/tools/*.toml`: added `send_keys_delay = 0.05` to all six bundled tool profiles (omp, pi, claude, opencode, gemini, codex)
- `justfile`: added `fmt-check` to the `ci` recipe — local `just ci` now has full parity with GitHub Actions CI
- Confirmed `shoal-cli 0.21.0` live on PyPI; `pipx install shoal-cli` works end-to-end

**Current state:**

- Branch: `main` at `188c6cc`
- CI: 1082 passed / 1 skipped, `just ci` fully green (includes `fmt-check` parity)
- v0.21.0 tag at `c96a0d9`; no new version bump needed for this batch of changes

**What to do next:**

- Decide fin contract version support window policy (v1-only vs N/N-1 overlap) — blocks `shoal fin install` registry semantics
- Scope v0.22.0 milestone: top candidates are auto-commit lifecycle hook, `shoal fin install` registry/local-source, dashboard fzf actions
- Existing users who ran `shoal init` before this commit won't pick up `send_keys_delay = 0.05` automatically; a `shoal init --refresh-tools` flag or a note in the v0.22.0 release notes would address this


### Session: 2026-03-07 — v0.21.0 public beta ship

**What we did:**

- Published `shoal-cli` to PyPI (trusted publisher via GitHub Actions OIDC)
- Updated pyproject.toml: name=`shoal-cli`, version=0.21.0, classifiers, authors, project URLs
- Added PyPI publish job to `.github/workflows/release.yml`
- README: version badge v0.21.0-beta, test count 1087, removed ecosystem note, updated install section and status table
- CONTRIBUTING.md + ARCHITECTURE.md: Pi as primary default backend (replaces OpenCode/Neovim references)
- docs/getting-started.md: PyPI as primary install path
- ROADMAP.md: v0.20.0 marked complete, v0.21.0 section added
- CHANGELOG.md: v0.21.0 release entry

**Current state:**

- Branch: `main` at HEAD
- v0.21.0 tagged, pushed, PyPI publish triggered via GitHub Actions

**What to do next:**

- Verify `pipx install shoal-cli` works from PyPI
- Decide fin contract version support window policy
- Consider `send_keys_delay` non-zero default for TUI tools (0.05s)


### Session: 2026-03-07 — Roadmap cleanup + v0.19.0 milestone

**What we did:**

- Removed 4 resolved backlog items (Fix template env gap, `state_dir`/`runtime_dir` naming, `send_keys` submission bug, double `feat/` prefix) — shipped in v0.18.0/v0.19.0
- Added `## v0.19.0` section documenting version flag, XDG naming, archived journal lookup, branch naming fix
- Added `## v0.20.0` in-progress section (setup_commands, orphan worktrees, readiness signals, batch MCP)
- v0.19.0 tagged at `4b1daa9`, pushed to origin; `main` at `03fc750`

**Current state:**

- Branch: `main` at `03fc750`
- v0.20.0 in progress — 4 parallel worktrees: `fix/setup-commands`, `fix/orphan-worktrees`, `fix/mcp-readiness-batch`, `fix/roadmap-cleanup`

**What to do next:**

- Merge all four v0.20.0 worker branches
- Run `just ci` to verify
- Cut v0.20.0 release

### Session: 2026-03-07 — CI green-up + send_keys reliability

**What we did:**

- Fixed RET501 lint regression in `tests/test_cli_robo.py` (removed explicit `return None`)
- Fixed mypy assignment error in `fin_runtime.py` (`manifest` → `child_manifest`, `Path` vs `FinManifest` type conflict)
- Extracted `infer_branch_name()`, `validate_branch_name()`, and `ALLOWED_BRANCH_CATEGORIES` to `core/git.py`; fixed double `feat/` prefix bug in API server and MCP server; added 27 branch-naming tests
- Added `send_keys_delay: float = 0.0` to `ToolConfig`; updated `async_send_keys` to split paste + Enter with configurable sleep; wired through `send_keys_tool` and `create_session` prompt dispatch; added 4 new tests

All four fixes committed atomically; CI is fully green (1040 passed, 1 skipped).

**What to do next:**

- Decide fin contract version support window policy (v1-only vs N/N-1 overlap)
- Add registry/local-source install semantics for `shoal fin install`
- Add optional subprocess timeout controls for fin lifecycle commands
- Consider setting `send_keys_delay` to a non-zero default (e.g. `0.05`) for TUI tools in built-in tool profiles

### Session: 2026-02-27 — Fin adapter Iteration 2 (lifecycle + discovery + parity)

**What we did:**

- Added first-class fin lifecycle commands: `shoal fin install` and `shoal fin configure`
- Added path-based discovery command: `shoal fin ls [--path <dir-or-fin.toml>]`
- Added valid/invalid manifest reporting in `fin ls` with actionable parse errors
- Added `SHOAL_LOG_LEVEL` handshake propagation for fin subprocesses
- Added cross-repo integration guard test using a scaffold generated by `fins-template`
- Updated extension docs with run-policy note (`run` does not require prior `validate`)

**What to do next:**

- Decide and document contract version support window policy (v1 only vs N/N-1 overlap)
- Add registry/local-source install semantics for `shoal fin install` (currently lifecycle execution only)
- Add optional subprocess timeout controls for fin lifecycle commands
- Consider richer `fin ls` output modes (table/json) and recursive discovery options

### Session: 2026-02-26 — Fin contract-v1 adapter (inspect/validate/run)

**What we did:**

- Implemented `shoal fin` command group with `inspect`, `validate`, and `run`
- Added `models/fin.py` and `services/fin_runtime.py` for manifest parsing, contract-v1 validation, entrypoint resolution, subprocess execution, and exit-code propagation
- Added tests for CLI and service behavior (`tests/test_cli_fin.py`, `tests/test_services_fin_runtime.py`)
- Added extension capability and boundary doc: `docs/EXTENSIONS.md`
- Updated README command/docs sections and SHOAL next-work status to reflect fin adapter progress

**What to do next:**

- Add first-class `shoal fin install` and `shoal fin configure` commands
- Add basic discovery (`shoal fin ls`) and local fin source management
- Define explicit contract version support window policy (v1 now, migration policy for v2)
- Decide hook package loading model for fins with isolation guarantees

### Session: 2026-02-25 — Pi-first defaults + status-provider abstraction

**What we did:**

- Switched defaults to Pi across config and CLI surfaces (`GeneralConfig.default_tool`, robo defaults, template defaults, demo fallback, example config)
- Added explicit status-provider architecture: `core/status_provider.py` with providers `pi`, `opencode_compat`, and `regex`; `core/detection.py` now delegates through provider resolution
- Extended tool schema with `tool.status_provider` and wired config loader defaults (`pi` for Pi, `opencode_compat` for OpenCode, `regex` otherwise)
- Hardened watcher pane resolution when pane titles drift (fallback to tool executable, active pane, then single-pane session)
- Updated docs for degraded compatibility behavior (README + TROUBLESHOOTING), and added `Detection` display in `shoal info`
- Added/updated tests for provider selection, watcher fallback behavior, and config defaults
- Fixed CI flakiness surfaced during this work (`test_mcp_pool` AF_UNIX path length, `test_api_load` concurrent DB lock race) and remote API connection-reset normalization
- Full validation passed: `just ci` green (990 passed, 1 skipped)

**What to do next:**

- Implement the first non-regex Pi provider path once explicit Pi event contracts are available (keep current adapter seam)
- Decide whether to expose provider selection directly in `shoal config`/template docs (currently in tool TOML docs + `shoal info` visibility)
- Continue extension-system backlog work (Fins capability map + CLI/core boundary recommendation)

### Session: 2026-02-24 — v0.18.0 Phase 4 complete + env fix

**What we did:**

- Fixed template env gap — `lifecycle.py` now applies `template_cfg.env` to initial pane via fish `set -gx` before agent launch (`75a2434`, +31 lines)
- Added background daemon mode for `shoal robo watch` — `--daemon` flag, `watch-stop`/`watch-status` commands, profile-specific PID files (`3aa15f5`, +290 lines, 6 files)
- Added LLM escalation for robo supervisor — `_escalate_to_llm()`, `_build_escalation_prompt()`, journal-based polling via `_wait_for_escalation_response()`, `EscalationConfig` with `escalation_session`/`escalation_timeout` (`72cf876`, +288 lines)
- v0.18.0 Phase 4 now fully complete (all checkboxes done)
- 986 tests passing (was 967), CI green — 3 parallel Shoal sessions used
- Added backlog items: Fins extension system, `send_keys` submission bug, auto-commit on idle/kill

**What to do next:**

- Push to origin and tag v0.18.0 release
- Fix `send_keys` prompt submission reliability (text pastes but Enter doesn't always submit in Claude Code)
- Fix double `feat/` branch prefix bug
- Add `setup_commands` template feature (Iteration 2 from `docs/WORKTREE_ENV_INIT.md`)
- Update CHANGELOG.md `[Unreleased]` section with all v0.18.0 changes before tagging

### Session: 2026-02-24 — v0.18.0 Phase 4 Robo Supervisor

**What we did:**

- Implemented `services/robo_supervisor.py` (248 lines) — async `RoboSupervisor` class with poll loop, `_safe_to_approve()` pattern detection, `_auto_approve()` via tmux, `_escalate()` with journal logging, `_waiting_duration_seconds()` from status_transitions DB
- Added `shoal robo watch` CLI command in `cli/robo.py` — loads robo profile, prints config summary, runs supervisor loop; fish completions updated
- 15 new tests (11 supervisor + 4 CLI), 967 total passing
- Added `-n auto` to justfile test recipes — parallel test execution (5min+ → 21s)

**What to do next:**

- LLM escalation for ambiguous cases (remaining Phase 4 item)
- Background daemon mode for `shoal robo watch`
- Fix template env gap
