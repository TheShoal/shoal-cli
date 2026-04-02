# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

> **Release history**: See [CHANGELOG.md](CHANGELOG.md) for completed releases (v0.4.0–v0.29.0).

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

## v0.27.0

Released 2026-03-31

- **Meta-repo workspace routing**: `.shoal/workspace.toml` manifest, `--repo` flag, auto-match by worktree hint or path prefix (SMORGASBORD §3.1)
- **Structured handoff packets (B2)**: `HandoffArtifact` with git context (diff stat, commit count), `to_dict()` JSON export, auto-generation on kill, `shoal handoff` command with `--json`/`--save`, `shoal handoff-ls`
- **Operating modes (B3)**: Data-driven `MODE_REGISTRY` with `ModeSpec`, 3 new modes (planner, implementer, reviewer), `shoal mode ls`, auto-tagging from modes and templates
- **Template `tags` and `mode` fields**: Union-merged during inheritance, auto-applied to sessions
- **Branch categories**: `plan`, `impl`, `review`, `batch` added
- **Docs**: New "Handoffs & Modes" mkdocs page, Bedrock section in AGENTS.md


## v0.28.0

Released 2026-03-31

- **Flagship fleet demo**: `shoal demo fleet` runs a 6-step scripted showcase — planner → implementer → reviewer → supervisor escalation → overnight progress → morning fleet summary
- **Shoal-native skills**: `SkillConfig` model, `discover_skills()` searches `.shoal/skills/` and `~/.config/shoal/skills/`, `shoal skill ls` command, auto-symlink into `.claude/skills/`
- **Project-level `.shoal.toml`**: Committed config at git root with `[env]`, `setup_commands`, `default_tool`, `default_template`. Precedence: project < template < CLI flags
- **Cross-agent skill setup**: OpenCode agents (`.opencode/agents/`), omp skills (`.omp/skills/`), and rules for both tools
- **`claude-review` template**: Review-oriented Claude session for reviewer mode
- **Docs**: CLI reference updated with incident, handoff, mode, and skill commands

## v0.29.0

Released 2026-03-31

- **MCP tools for robo workflows**: `mark_complete`, `read_worktree_file`, `list_worktree_files` — MCP server now exposes 18 tools
- **PyApp binary distribution**: Self-contained `shoal` binary via PyApp packaging. Homebrew formula at `TheShoal/tap/shoal-cli`
- **omp as default tool**: Replaced `pi` with `omp` (oh-my-pi) as the default tool across config, robo profiles, mode presets, and templates
- **Deferred CLI imports**: All subcommand modules now use lazy imports via thin wrappers in `cli/__init__.py`, improving `shoal --help` startup latency
- **Config model split**: Monolithic `models/config.py` refactored into focused submodules (`general.py`, `tools.py`, `templates.py`, `hooks.py`, `workspace.py`, `robo.py`)

## v0.30.0

Released 2026-04-01

- **Claw runtime provider**: Shoal now manages lobster-party Claw sessions via gRPC. `RuntimeKind.claw` with full `ClawRuntimeProvider` implementing all 13 Protocol methods
- **MCP ↔ A2A bridge**: 5 new `shoal-orchestrator` MCP tools for cross-system agent collaboration: `send_to_claw`, `claw_status`, `list_claws`, `claw_health`, `sync_claw_conversations`
- **Conversation/journal sync**: `core/claw_conversations.py` reads lobster-party QMD files. `import_claw_turns()` and `export_journal_to_qmd()` enable bidirectional sync. `shoal sync <session>` CLI command
- **Lobster Party proto stubs**: Generated protobuf/gRPC stubs in `src/shoal/core/proto/`. Regenerate with `just gen-protos`
- **Integration spec**: `INTEGRATION.md` documents the full Shoal × Lobster Party × Smorgasbord integration architecture

## v0.31.4

Released 2026-04-01

- **Fixed**: Broken mermaid markup on docs homepage

## Backlog

### Done (kept for reference)

- ~~**Structured handoff packets** (B2)~~ — v0.27.0
- ~~**Role/mode templates** (B3)~~ — v0.27.0
- ~~**Flagship secure-fleet demo** (B6)~~ — v0.28.0 (`shoal demo fleet`)
- ~~**Template `setup_commands`**~~ — v0.20.0
- ~~**Project-level `.shoal.toml`**~~ — v0.28.0
- ~~**Dashboard actions**~~ — v0.22.0
- ~~**Agent readiness signals**~~ — v0.20.0
- ~~**omp integration**~~ — v0.29.0 (default tool, tool profile, templates)
- ~~**Auto-commit on kill**~~ — v0.22.0 (`general.auto_commit`)
- ~~**Batch MCP commands**~~ — v0.20.0 (`session: str | list[str]`)
- ~~**Robo merge MCP tools**~~ — v0.24.0 (`merge_branch`, `branch_status`)
- ~~**Worker completion signals**~~ — v0.24.0 (`shoal done`) + v0.29.0 (`mark_complete`, `read_worktree_file`)
- ~~**Linux notifications**~~ — solved by fish event hooks
- ~~**Claw runtime + A2A bridge**~~ — v0.30.0 (gRPC runtime provider, 5 new MCP tools, journal↔QMD sync)

### Remaining

- **Fins polish**: Registry/remote install semantics, subprocess timeout controls, contract version support window policy (v1-only vs N/N-1). Core adapter shipped v0.19.0; local install shipped v0.22.0; remote install shipped v0.24.0.
- **Per-session git practices**: `[template.git]` section for commit conventions, hook profiles, branch naming rules, and per-session identity (`GIT_AUTHOR_NAME`, `GIT_COMMITTER_EMAIL`). Template env gap (prerequisite) fixed in v0.18.0.
- **Remote status bar**: Fish status bar polls remote WebSocket for session status.
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()` — investigated, no-go for now ([spike findings](docs/composition-gateway.md)). Revisit when FastMCP adds UDS transport or robo needs unified cross-session MCP.
- **direnv/mise integration** (deferred): Opt-in `env_manager` field on templates. Explicit opt-in only, never auto-detect.

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-04-02 — Web dashboard + v0.34.0 release

**What we did:**

- Built and committed the Shoal web dashboard sub-app (`src/shoal/dashboard/`): HTMX 2.0.4 + htmx-ext-ws 2.0.2 (vendored), Jinja2 templates, dark design system with urgency-tier colors, fleet grid + session detail, live WS OOB push of session cards, `/` search shortcut, 20-test coverage of context builders
- Routes: `GET /ui/` (fleet), `GET /ui/sessions/{id}` (detail), partials for status-bar/session-list/journal/pane, `WS /ui/ws`
- Status poller in `server.py` calls `notify_status_change()` on every status change to push HTML fragments to all connected WS clients
- Switched pane capture in routes to `async_capture_pane()` (was manual `asyncio.to_thread` wrapper)
- Cut **v0.34.0**: bumped `pyproject.toml` + `__init__.py`, updated CHANGELOG, tagged `v0.34.0`
- CI: 1510 passed, 2 skipped (all checks green)

**Current state:**

- Branch: `main`, tagged `v0.34.0`, not yet pushed to remote
- Dashboard mounted at `/ui` — serve with `shoal serve` and open `http://localhost:<port>/ui`
- `jinja2>=3.1.0` added to core dependencies (no extra required)

**What to do next:**

- `git push origin main && git push origin v0.34.0` to publish the release
- Connect to a live Claw gRPC endpoint and run `get_agent_card()` / `send_message()` for real end-to-end validation
- Consider `--sync-claw` accepting a default from `config.claw.conversations_dir` (avoids requiring explicit path)
- **Remote status bar**: Fish status bar polling remote WebSocket (`/ws` on main API) for session status — backlog item

### Session: 2026-04-02 — Lobster integration: --sync-claw, proto compat, dashboard WIP

**What we did:**

- Wired `sync_for_handoff` into `shoal handoff --sync-claw PATH`: imports Claw QMD turns before generating the handoff artifact
- Dogfooded `shoal[claw]` with `uv run --extra claw`: `GRPC_AVAILABLE = True`, `ClawClient` patched, `proto_to_agent_card()` round-trip verified
- Fixed protobuf 6.x descriptor pool compat in three pb2 files (`lobster_loop_pb2`, `a2a_claw_pb2`, `a2a_core_pb2`): added `timestamp_pb2` pre-import
- Fixed all four `*_grpc.py` files: changed bare `import a2a_claw_pb2` → `from shoal.core.proto import ...` so they work inside a package
- Added `E402, I001` to pyproject.toml per-file-ignores for `proto/*.py` (generated files)
- Committed pre-existing dashboard WIP: `src/shoal/dashboard/` (context, routes, ws, static, templates, test)
- CI green: 1510 passed, 2 skipped

**Current state:**

- Branch: `main`, all commits pushed; last tag: `v0.33.0`
- `shoal handoff <session> --sync-claw <dir>` works end-to-end
- `shoal[claw]` extra verified with grpcio 1.80.0; ready for live Claw endpoint testing
- Dashboard sub-app committed but not in a release yet

**What to do next:**

- Connect to a live Claw gRPC endpoint and run `get_agent_card()` / `send_message()` for real
- Cut v0.34.0: lobster integration + dashboard
- Consider `--sync-claw` accepting a default from `config.claw.conversations_dir` (avoids requiring explicit path)

### Session: 2026-03-07 — Dashboard fzf actions

**What we did:**

- Extracted `_build_fzf_args() -> list[str]` from `run_popup()` for testability
- Added `ctrl-y`: `shoal send {1} ""` — sends Enter to approve agent prompts
- Added `ctrl-g`: `shoal fork {1}` — forks session into a new worktree
- Added `ctrl-r`: reload session list
- Added `ctrl-w`: filter to waiting sessions via awk
- Updated dashboard header to document all keybindings
- Added hidden top-level `shoal send <session> <keys>` command in `src/shoal/cli/session.py`
- Created `tests/test_dashboard.py` with 12 unit tests for `_build_fzf_args()`
- Key choices: `ctrl-y`/`ctrl-g` to avoid conflicts with tmux leader (`ctrl-a`) and tmux fullscreen (`ctrl-f`)

**Current state:**

- Branch: `feat/dashboard-actions`, 2 commits ahead of `main`, CI green
- Backlog item for dashboard actions is complete

**What to do next:**

- Merge `feat/dashboard-actions` → `main` and cut a release