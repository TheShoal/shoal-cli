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
- ~~**Remote status bar**~~: `shoal-status --remote <name>` now fetches `GET /status` from a remote Shoal API host configured under `[remote.<name>]`. Shipped this session.
- ~~**--sync-claw default from config**~~: `shoal handoff --sync-claw` now falls back to `config.claw.conversations_dir`; shipped previous session.
- **Live Claw gRPC validation**: End-to-end smoke test against a real Claw endpoint — `get_agent_card()` then `send_message()`. `shoal[claw]` extra and proto stubs are in place (v0.30.0); this is pure integration validation. Unblocked.
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()` — investigated, no-go for now ([spike findings](docs/composition-gateway.md)). Revisit when FastMCP adds UDS transport or robo needs unified cross-session MCP.
- **direnv/mise integration** (deferred): Opt-in `env_manager` field on templates. Explicit opt-in only, never auto-detect.

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-04-02 — Claw MCP modernization + remote status bar

**What we did:**

- Modernized Claw MCP tools in `mcp_shoal_server.py`: keyword-arg `ClawClient`, dict returns, `GRPC_AVAILABLE` guard unified, `send_to_claw` deprecated as wrapper for `send_a2a_message_tool`
- Fixed `sync_claw_conversations_tool` fallback: checks `cfg.claw.conversations_dir` first, then `~/conversations`
- Rewrote `tests/test_mcp_claw_tools.py` (25/25 pass); fixed `tests/test_a2a_grpc_roundtrip.py` collection guard (class nested under `if _grpc_for_test:`)
- Removed 3 stale `# type: ignore[attr-defined]` comments in `lobster_a2a.py`
- Added flow architecture view to dashboard (`/flow` route, `flow_context()`, `flow.html` template, CSS fonts)
- Shipped `shoal-status --remote <name>`: `generate_remote_status()` hits `GET /status` on configured remote API host; 9 new tests in `test_status_bar.py`
- CI: 1520 passed, 4 skipped (all 3 features clean through `just fmt-check lint typecheck test`)

**Current state:**

- Branch: `main`, all commits pushed (3 new commits since `v0.34.0`)
- `shoal-status --remote <name>` requires `[remote.<name>]` in `config.toml` with `host` and `api_port` (default 8080)
- Remote status bar backlog item marked done

**What to do next:**

- Connect to a production Claw endpoint and run `get_agent_card()` / `send_message()` for real traffic validation (live Claw gRPC smoke test — unblocked)
- **Fins polish**: registry/remote install semantics, subprocess timeout controls, contract version support window policy
- **Per-session git practices**: `[template.git]` section with commit conventions, branch naming, and per-session identity vars
### Session: 2026-04-02 — conversations_dir config default + gRPC round-trip tests

**What we did:**

- Added `conversations_dir: Path | None` to `ClawConfig` — maps to `[claw] conversations_dir` in `config.toml`
- `shoal handoff <session>` now falls back to `config.claw.conversations_dir` when `--sync-claw` is absent; explicit flag still takes priority
- Added 2 new tests: `test_handoff_show_without_sync_claw` patched to mock config; `test_handoff_show_sync_claw_from_config` asserts config fallback runs sync
- Wrote `tests/test_a2a_grpc_roundtrip.py`: 5 in-process gRPC tests using `grpc.aio.server()` + `_TestAgentLoopServicer`; skipped in standard CI, run with `uv run --extra claw pytest`
- Validated full round-trip: GetAgentCard → AgentCard Pydantic model; SendMessage echo; ListTasks empty; channel reuse; explicit task_id preservation
- Fixed descriptor pool load order in test file: `# noqa: I001` on first try-block import preserves `a2a_core_pb2` before `a2a_claw_pb2_grpc`
- CI: 1516 passed, 2 skipped (6 new tests vs prior 1510)

**Current state:**

- Branch: `main`, tagged `v0.34.0` (dashboard release); pending push to remote for prior session
- `ClawConfig.conversations_dir` defaults to None; set in `config.toml` to enable auto-sync without flag
- gRPC round-trip tests: 5/5 pass under `uv run --extra claw pytest tests/test_a2a_grpc_roundtrip.py`

**What to do next:**

- `git push origin main && git push origin v0.34.0` to publish the v0.34.0 release
- Connect to a production Claw endpoint and run `get_agent_card()` / `send_message()` for real traffic validation
- **Remote status bar**: Fish status bar polling remote WebSocket (`/ws` on main API) for session status — backlog item

- Pick up any of the three newly formalized backlog items above