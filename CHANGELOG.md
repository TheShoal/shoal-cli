# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.41.0] "Toolchain Consolidation" - 2026-04-09

**Drop Pisces + Dreamer, adopt upstream omp + Hermes as the integration layer.**

### Removed
- **Dreamer LLM service** (`services/dreamer.py`, `services/ai_client.py`): Bedrock/HTTP LLM wrapper and background summarizer removed. Session summaries now read directly from journal entries with `source="dreamer"`. The `dreamer_summary` / `workflow_summary` fields on `HandoffArtifact` are kept as empty defaults for serialization compatibility.
- **QMD / ConversationIndex** (`core/qmd.py`, `core/conversation_index.py`, `core/conversations.py`): Dual-plane markdown+JSON conversation memory removed. `ConversationIndex` teardown removed from `db.py` `with_db()`.
- **Fin plugin system** (`cli/fin.py`, `models/fin.py`, `services/fin_runtime.py`, `services/fin_repo.py`): Entire extension lifecycle — install/configure/run, contract-v1 adapter, registry — removed. `fins_dir()` removed from `core/config.py`. `shoal fin` subcommand removed from CLI.
- **`_normalize_legacy_root_config()`** (`core/config.py`): Legacy `[claw]` → `[lobster]` config translation shim removed. Configs with a `[claw]` key now raise `ConfigLoadError` via `extra="forbid"`.
- **Dead mypy overrides** (`pyproject.toml`): Removed stale overrides for `boto3`, `botocore.*`; retained `shoal.services.ai_client` override for the lazy-import fallback pattern in `services/report.py`.
- **Dead ruff rule** (`pyproject.toml`): Removed `[tool.ruff.lint.extend-per-file-ignores]` block that targeted the now-deleted `src/shoal/core/proto/*.py` files.

### Added
- **Hermes plugin** (`~/.hermes/plugins/shoal/`): Six tools registered via Hermes `PluginContext` — `shoal_list_sessions`, `shoal_session_status`, `shoal_create_session`, `shoal_kill_session`, `shoal_send_keys`, `shoal_heartbeat` — all gated behind `check_fn=_check_shoal_available` so they only appear when the Shoal API is reachable. `pre_llm_call` hook injects session name, tool, status, branch, and worktree into each turn when `SHOAL_SESSION` is set.
- **omp heartbeat extension** (`integrations/hooks/omp_heartbeat.ts`): TypeScript omp Extension (default export `ShoalHeartbeatExtension` with `onTurnEnd` / `onAgentEnd`) plus backward-compatible named exports (`turnEnd`, `agentEnd`). Default port `8080` (Shoal API). Install via `~/.omp/agent/extensions/` or `~/.config/shoal/hooks/`.

### Changed
- **`omp.toml` tool profile**: `status_provider` corrected from `"pi"` to `"omp_compat"`.
- **`pisces.toml` tool profile**: Deprecation header added — pisces is no longer the primary tool; use upstream omp.
- **Demo tour**: Reduced from 9 to 8 feature areas (Journal Dreaming step removed).
- **`services/report.py`**: `_latest_dreamer_summary()` replaced with `_latest_journal_summary()` (journal-only, no singleton). LLM calls remain as lazy imports inside `try/except` blocks — reports always use the text fallback now.
- **`services/status_bar.py`**: `generate_status_extended()` simplified to journal-only summary lookup (single tier instead of three).
- **`services/mcp_shoal_server.py`**: `session_summary` tool simplified to journal-only lookup.
- **Hooks README**: Renamed from "Pisces Heartbeat Hook" to "Shoal Heartbeat Hooks"; documents omp and Claude Code hooks, `SHOAL_PORT` env var, and legacy pisces variant.

### Stats
- 1530 tests, 1 skipped

## [0.40.0] "Ticket Workflow & MCP Hardening" - 2026-04-08

**Linear ticket workflows from the CLI and critical MCP dogfooding fixes for production use.**

### Added
- **`shoal ticket sync`**: Sync Linear issues to local SQLite cache for fast offline queries.
- **`shoal ticket pick`**: Interactive multi-team ticket picker using fzf. Supports `--json` for scripting.
- **Linear cache service** (`services/linear_cache.py`): SQLite-backed issue cache with `get_cached_issues()`, `get_issue()`, `invalidate()`, `last_sync_at()`.
- **`TeamConfig.repos` field**: Repository routing per team in `workspace.toml`, replacing repos.txt manifest concept.
- **`model` parameter on `create_session` MCP tool**: Pass a model identifier through to sessions; sets `OMP_MODEL` env var.
- **Fish shell prompt escaping** (`integrations/fish/prompt.py`): `escape_for_fish()` escapes special chars (`? & $ ( ) \ " ' ; | < >`) before sending to tmux.
- **Long prompt file-based delivery**: Prompts >500 chars are written to a temp file and sourced in fish, preventing tmux line mangling.

### Fixed
- **Undefined `db_backfill` fixture**: Removed from `test_linear_cache.py`; tests rewritten as proper model validation.
- **Hardcoded tmux prefix in tests**: `test_state.py` now uses `build_tmux_session_name()` instead of asserting `startswith("_")`, respecting the configurable prefix.
- **GraphQL `orderBy` enum**: Removed invalid `orderBy` clause from Linear team issues query.

### Docs
- **MCP dogfooding findings**: Documented Issues 1–3 from live Hermes-over-Shoal session.

### Stats
- 1615 tests, 2 skipped

## [0.39.0] "Reports & Experimental Autonomy" - 2026-04-06

**Team reporting, ticket routing, and a documented Hermes-over-Shoal experimental supervisor path.**

### Added
- **`shoal ticket` workflows**: Start, inspect, and finish Linear-linked sessions from the CLI.
- **`shoal report` workflows**: Generate session, team, and sprint summaries; optionally post sprint updates to Linear.
- **Team report-target visibility**: `shoal team ls` now surfaces configured report destinations from `.shoal/workspace.toml`.

### Changed
- **Experimental Hermes-over-Shoal path**: Documented a local-only HTTP/MCP profile where Hermes owns scheduling and cron while Shoal remains the execution control plane. Read-only fleet health checks are verified; bounded team spawning remains experimental and in development.
- **Claw scheduler removal**: Removed the built-in Claw scheduler from Shoal core, kept legacy `[claw]` config as a warning-only compatibility shim, and moved future autonomy guidance toward external supervisors over MCP.
- **Supervisor profile split**: Separated general robo profiles from dedicated supervisor templates to clarify setup and defaults.

### Fixed
- **Project defaults**: Aligned project-local defaults with the current config schema to avoid invalid `.shoal.toml` surprises.
- **Skill link refresh**: Hardened generated skill-link updates so local skill docs stay in sync without clobbering paths.

### Docs
- **Operator docs**: Expanded the docs site for team/ticket/report workflows and documented the experimental Hermes-over-Shoal HTTP transport profile.

### Stats
- 1620 tests, 1 skipped


## [0.38.0] "Agentic Teams" - 2026-04-03

**Agents can now spawn and coordinate worker teams from within a session.**

### Added
- **`fork_session` MCP tool**: Agents self-spawn a worker session with its own git worktree and branch. Returns `id`, `name`, `branch`, `worktree`, `parent_id`.
- **`spawn_team` MCP tool**: Fan-out primitive — takes a list of worker specs (`name`, optional `prompt`), spawns each as a forked session, sends a `handoff` message with a shared `correlation_id`. Returns `{correlation_id, spawned, failed}` with per-worker error isolation.
- **`wait_for_team` MCP tool**: Poll-based collective completion — waits for all named workers to reach a terminal state (`completed`, `error`, or `stopped`). Single `list_sessions()` call per poll cycle instead of N individual lookups.
- **Worker completion signals to coordinator**: New `_hook_coordinator_on_complete` lifecycle hook fires on `session_completed`; if the session has a `parent_id`, sends a `worker_completed` event message to the parent session automatically.
- **`_resolve_template_and_mcp` helper**: Extracted shared template-load + MCP merge logic used by `create_session_tool`, `fork_session_tool`, and `spawn_team_tool`.
- **`_create_worker_worktree` helper**: Extracted shared worktree + branch creation logic used by both fork tools.
- **`MessageKind` type on `send_message`**: `message_bus.send_message(kind=...)` now typed as `MessageKind` Literal instead of bare `str`.

### Docs
- **`docs/features.md` rewrite**: Full feature reference covering all capabilities with tables, config examples, and links. Replaces the old vague marketing copy.
- **`docs/project/` stubs** (7 new files): Resolves broken nav links in mkdocs.yml — roadmap, changelog, release-process, commit-guidelines, contributing, security, architecture-guide.
- **`docs/cli-reference.md`**: Added `shoal proactive`, `shoal sync`, web dashboard, and MCP tools table (including new team tools). Fixed broken `lobster-integration.md` reference.

### Stats
- 1572 tests, 1 skipped

## [0.37.2] - 2026-04-03

### Added
- **Pre-commit hook profile** (`models/config/templates.py`, `services/lifecycle.py`):
  New `[template.git].pre_commit_config` field accepts a path to a
  ``.pre-commit-config.yaml`` file.  At session creation time the path is
  symlinked as ``<worktree>/.pre-commit-config.yaml`` so ``pre-commit`` picks it
  up automatically.  Silently skipped if the source path does not exist.
  Added ``_symlink_pre_commit_config`` helper; example commented in
  ``examples/config/templates/base-dev.toml`` and ``mixins/git-identity.toml``.
  7 new tests: symlink creation, noop-on-missing-source, idempotent-replace,
  tilde expansion, field defaults, TOML parsing, no tmux calls when pre_commit_config
  is the only git field set.


## [0.37.1] - 2026-04-03

### Fixed
- **`_handle_command_failed` missing `event` positional parameter** (`services/proactive_supervisor.py`):
  The inner hook callback passed to `lifecycle.on()` was declared as `(**kwargs)`, but
  `lifecycle.emit()` calls hooks as `cb(event, **kwargs)`. The missing `event` parameter caused
  `command_failed` events to be silently swallowed (hook raised `TypeError`, caught by emit's
  exception guard). Fixed to `(event: LifecycleEvent, **kwargs: object)`.

### Added
- **Tests for `FsWatcher`** (`tests/test_fs_watcher.py`): 20 tests covering singleton helpers,
  path add/remove/replace, start/stop idempotency, `_should_ignore`, `_WatchFilter`,
  `_dispatch_changes` event emission and error isolation.
- **Tests for `ProactiveSupervisor`** (`tests/test_proactive_supervisor.py`): 18 tests covering
  `on_command_failed`, `get_failure_context` (consumed/unconsumed), `consume_failure_context`,
  TTL expiry dispatch, singleton lifecycle, `register_proactive_hook` wiring, and
  `_init_proactive_hooks` enabled/disabled/idempotent paths.


## [0.37.0] – [0.37.2] "Agent Bus & Memory" (2026-04-03)

**Inter-Agent Communication + Conversation Memory** — enriched message bus, Lobster scheduler, QMD memory, pre-commit hook profile.

### v0.37.2 — Pre-Commit Hook Profile
- **`[template.git].pre_commit_config`**: Symlinks `.pre-commit-config.yaml` into worktrees at session creation

### v0.37.1 — Scout Hotfix + Test Coverage
- Fixed `_handle_command_failed` missing `event` parameter (Scout was silently broken)
- Added 20 `FsWatcher` tests, 18 `ProactiveSupervisor` tests

### v0.37.0 — Agent Bus, Memory, Scheduler
- **Agent Bus enhancements**: `watch_messages`, `watch_pending_actions` async generators; enriched message envelope (typed `kind`, `priority`, `correlation_id`, `requires_ack`)
- **Lobster scheduler**: Fair-scheduling async tick loop for background/agent tasks; recurring/cron support; `TaskHandler` protocol
- **SOUL.md integration**: Auto-loads repo SOUL into MCP instructions + fin env
- **Dual-plane QMD**: Structured conversation memory (Markdown full-text + JSON sidecar); `ConversationIndex` for fast lookup; 3-tier handoff chain (Dreamer → index → prose)
- **Claw → Lobster rename**: Completed across all user surfaces
- 1673 tests (1669 passed, 4 skipped)

## [0.36.0] "Scout" (2026-04-02)

**Proactive Agent Assistance** — full autonomous monitoring stack with Dreamer LLM, FsWatcher, Agent Bus, and Scout supervisor.

### Added
- **Dreamer LLM**: AWS Bedrock/HTTP gateway wrapper, persists session summaries to journal
- **FsWatcher**: `watchfiles`-backed async watcher, `file_changed` lifecycle events, `shoal proactive fs-watch`
- **Agent Bus**: Session-to-session SQLite messaging, `messages` + `failure_contexts` tables, 3 new MCP tools
- **Scout Supervisor**: Subscribes to `command_failed`, stores failure contexts, `get_failure_context` MCP tool
- **`shoal session` subcommand**: Ergonomic aliases (list/info/logs/status/attach/detach/kill/prune)
- **`branch_prefix` in MCP**: `create_session_tool` now honors `template_cfg.git.branch_prefix`
- **`--extended` status**: Emits `dreamer_summaries` dict

### Fixed
- MCP socket env injection (3 bugs: pane-dict key, pane target, TUI vs shell)
- `mcp_configure` parent-dir creation
- `kill_session` implicit list-expansion removed

### Changed
- Dynamic versioning via `hatch.version`
- 1533 tests (1529 passed, 4 skipped)

## [0.35.0] "Dashboard API" (2026-04-02)

**JSON API + Pisces** — dashboard JSON endpoints, Pisces tool support, socket env injection.

### Added
- **Dashboard JSON API**: All partial endpoints accept `?format=json` for structured data
- **Dashboard schemas**: Pydantic models (`FleetResponse`, `SessionDetailResponse`, `JournalEntryResponse`, `PaneResponse`)
- **Pisces tool**: `omp_compat` status provider, example configs (tool/robo/template)
- **MCP socket env injection**: `socket_env` field injects Unix socket paths into agent shell

### Fixed
- Dashboard WS broadcast debounce (100ms batching)
- Dashboard XSS (`html.escape()` before markdown)
- Dashboard status counts (single `Counter` pass)
- Pane capture ANSI stripping
- `template_cfg.git is None` guard
## [0.34.0] "Web Dashboard" (2026-04-02)

**Live Operator UI** — HTMX-powered web dashboard with real-time updates.

### Added
- **Web dashboard**: `/ui` operator board with fleet overview, status bar, filter pills, WebSocket live updates
- **Session detail page**: Identity/runtime/MCP panel + Journal/Terminal/History tabs
- **Dark theme**: Urgency-tier color coding (error → waiting → running → idle → completed)
- **`shoal handoff --sync-claw`**: Import Lobster QMD turns before handoff generation

### Fixed
- Proto pb2 compat for protobuf 6.x / grpcio 1.80 (descriptor pool collision)

## [0.30.0] – [0.32.0] "Lobster Integration" (2026-04-01)

**Cross-System A2A Bridge** — Claw runtime provider, MCP ↔ A2A bridge, conversation sync, agent teams.

### v0.32.0 — Agent Teams & Journal Dreaming
- **Agent teams**: `shoal create --team` spawns nested parallel sub-sessions; `CoordinatorSession` abstraction
- **Journal dreaming**: Sessions compress past findings into agent loop

### v0.31.4 — Hotfix
- Fixed mermaid markup on docs homepage

### v0.30.0 — Claw Runtime + A2A Bridge
- **Claw runtime**: `RuntimeKind.claw`, `ClawRuntimeProvider` (13 Protocol methods), `ClawRuntimeState`, gRPC session lifecycle
- **MCP ↔ A2A bridge**: 5 new tools (`send_to_claw`, `claw_status`, `list_claws`, `claw_health`, `sync_claw_conversations`); 23 total MCP tools
- **Conversation sync**: QMD ↔ journal import/export; `shoal sync <session>` CLI
- **Proto stubs**: Lobster Party protobuf/gRPC stubs in `src/shoal/core/proto/`
- **Integration spec**: `INTEGRATION.md` documents Shoal × Lobster Party × Smorgasbord architecture

## [0.29.0] "Binary Release" (2026-03-31)

**Distribution + Performance** — PyApp self-contained binary, Homebrew tap, omp as default tool.

### Added
- **MCP robo tools**: `mark_complete`, `read_worktree_file`, `list_worktree_files` (18 total tools)
- **PyApp binary**: Self-contained `shoal` binary; Homebrew formula at `TheShoal/tap/shoal-cli`
- **omp default**: Replaced `pi` as default tool across config/robo/templates

### Changed
- **Deferred CLI imports**: Lazy loading via thin wrappers improves `shoal --help` latency
- **Config model split**: `models/config.py` → focused submodules (general/tools/templates/hooks/workspace/robo)

## [0.28.0] "Fleet Showcase" (2026-03-31)

**Demo Maturity + Skill Ecosystem** — flagship 6-step fleet demo, skill discovery, and project-level config.

### Added
- **`shoal demo fleet`**: 6-step showcase (planner → implementer → reviewer → escalation → overnight → summary) with real sessions/worktrees/journals
- **Skill discovery**: `discover_skills()` searches `.shoal/skills/` + `~/.config/shoal/skills/`; `shoal skill ls`; auto-symlink for Claude Code
- **Project-level `.shoal.toml`**: Git-root config with `[env]`, `setup_commands`, `default_tool`, `default_template` (precedence: project < template < flags)
- **Cross-tool skill parity**: OpenCode (`.opencode/agents/`), omp (`.omp/skills/`), Claude Code (`.claude/skills/`)

### Fixed
- `send_keys` pane targeting in multi-pane templates (was active pane, now first pane)
- GitHub Actions Node.js 24 compatibility

## [0.27.0] "Workspaces & Modes" (2026-03-31)

**Meta-Repo Support + Agent Roles** — nested workspace routing, structured handoffs, and operating modes for multi-agent workflows.

### Added
- **Meta-repo workspaces**: `.shoal/workspace.toml` maps logical names to sub-repos (SMORGASBORD §3.1); `--repo` flag + auto-match
- **Structured handoffs**: `HandoffArtifact` with git stats, JSON export, auto-generation on kill; `shoal handoff` + `handoff-ls` commands
- **Operating modes**: `MODE_REGISTRY` with `planner`, `implementer`, `reviewer` specs; `shoal mode ls`; auto-tagging
- **Template `mode` + `tags`**: Union-merged during inheritance, auto-applied to sessions
- **Branch categories**: `plan`, `impl`, `review`, `batch` prefixes
- **Cross-agent skills**: `.shoal/skills/` with transpilation to Claude/OpenCode/omp; `shoal-skill-sync.sh` hook
- **`claude-review` template**: Review-oriented session

### Fixed
- Template inheritance now merges `mode`/`tags` (were dropped)
- Handoff generation race (now before DB deletion)
- Workspace path traversal validation
- `shoal new <nonexistent-path>` friendly error (TheShoal/shoal-cli#7)

## [0.26.0] "Incident Response" (2026-03-30)

**Alert-Driven Multi-Agent Ops** — first-class incident workflows with role-based lanes, Claude hook integration, and remote ops.

### Added
- **Incident workflows**: `shoal incident ingest/ls/show/spawn/resolve` for alert ingestion and multi-lane coordination
- **Five incident roles**: supervisor, investigator, repro, comms, reviewer — role-specific prompts + env injection
- **Incident REST API**: Full programmatic access (`GET /incidents`, `POST /incidents`, lane spawning)
- **Claude hook integration**: `hook-scaffold` writes `TaskCreated`/`TaskCompleted`/`StopFailure` templates; `hook-report` ingests events
- **Remote incident ops**: `shoal remote incident` commands proxy to remote hosts via SSH tunnel
- **`post_worktree_create` hook**: Template field executes script after worktree provisioning
- **Project-local hooks**: `.shoal/hooks.toml` binds shell commands to lifecycle events with status filters

### Fixed
- **Lifecycle hooks silently broken**: `register_builtin_hooks()` never called at API startup since v0.18.0
- **Path traversal in prompt files**: Session names with `/` now sanitized

## [0.24.0] – [0.25.0] "Runtime Abstraction" (2026-03-18)

**Backend Flexibility** — runtime provider architecture enables future multi-backend support (tmux today, potentially Docker/K8s/SSH later).

### v0.25.0 — Runtime Provider Seam
- **Session runtime model**: Canonical nested `runtime` object replaces tmux-specific top-level fields
- **Runtime provider dispatch**: `services/runtime_provider.py` + `runtime_providers/tmux.py` abstracts lifecycle, watcher, CLI, API, MCP flows
- **Legacy migration**: Automatic DB migration for pre-v0.25.0 sessions
- **Type-safe payloads**: Session info/snapshot surfaces return provider-tagged runtime metadata

### v0.24.1 — Hotfixes
- Fixed `shoal done` hanging on exit (missing `with_db()` wrapper)
- Fixed `fin install <url>` raw tracebacks (network errors now wrapped as `FinRuntimeError`)
- Fixed `httpx` missing from core dependencies
- Fixed stale `__version__` (was `0.22.0`, now correct)

### v0.24.0 — Worker Completion & Git MCP
- **Worker completion signals**: `session_completed` event, `shoal done`, `completed_at` field, `wait_for_completion` MCP tool
- **Git MCP tools**: `branch_status`, `merge_branch` for robo supervisors
- **Fin remote install**: HTTPS URLs + `fin:<name>[@<version>]` registry shorthand
- **Validation**: `branch=True` without `worktree` now raises clear error
## [0.17.0] – [0.23.0] (2026-02-24 – 2026-03-09)

**Observability, Operator Workflows & Automation** — seven releases focused on production operations, remote management, and autonomous supervision.

### Major Features
- **Demo & Onboarding** (v0.17.0): Interactive `shoal demo tutorial`, redesigned tour, onboarding prompts
- **Logging & Diagnostics** (v0.17.0): Named loggers, context propagation, `shoal diag`, structured JSON logs, operation timing
- **Remote Sessions** (v0.17.0): `shoal remote` subcommand group, SSH tunnel lifecycle, HTTP client
- **Lifecycle Hooks** (v0.18.0): Event system, fish event emission, built-in hooks, MCP tools (`capture_pane`, `read_history`)
- **Session Graph** (v0.18.0): `parent_id`, `tags`, `template_name` tracking, fork/tag commands, `--tree` view
- **Robo Supervision** (v0.18.0): Async supervision loop, pattern-based auto-approve, LLM escalation, daemon mode
- **Tool-Native Prompts** (v0.19.0): `input_mode` (arg/flag/keys), file-based prompt delivery, status provider abstraction
- **Fin Extensions** (v0.19.0): `shoal fin` commands, contract-v1 adapter, install/configure/run lifecycle
- **Template Setup** (v0.20.0): `setup_commands` field, batch MCP operations, agent readiness signals
- **PyPI Release** (v0.21.0): Published as `shoal-cli` on PyPI with OIDC trusted publisher
- **Dashboard & Automation** (v0.22.0): fzf actions, auto-commit on kill, fin registration
- **Urgency Board** (v0.23.0): `status_since` tracking, attention-first layout, urgency tiers, handoff summaries

### Key Changes
- **XDG compliance**: Corrected `data_dir`, `state_dir`, `runtime_dir` naming
- **Remote API**: SSH tunnel management, HTTP transport evaluation
- **Journal features**: YAML frontmatter, archived lookup, search, size warnings
- **Test infrastructure**: Parallel execution (pytest-xdist), 1100+ tests by v0.23.0

### Notable Fixes
- tmux pane targeting with non-default `base-index`
- Lifecycle hooks never fired in production (v0.18.0)
- Double `feat/` branch prefix
- Async-unsafe operations in prune/archive
- MCP proxy Python 3.13 compatibility

## [0.4.0] – [0.15.0] (2026-02-16 – 2026-02-22)

Foundation releases — SQLite + WAL migration, async-first core, lifecycle service with
rollback, git worktree isolation, fish shell integration, MCP pool with pure-Python bridge,
template inheritance and mixins, robo supervisor rename, pre-commit/CI framework,
mypy --strict, ruff lint expansion, FastMCP-based `shoal-orchestrator` MCP server.
Coverage grew from 52% (96 tests) to 82% (618 tests). See `git log v0.4.0..v0.15.0`
for full details.
