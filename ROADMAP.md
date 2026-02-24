# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

> **Release history**: See [CHANGELOG.md](CHANGELOG.md) for completed releases (v0.4.0–v0.17.0).

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

- [ ] `services/robo_supervisor.py` — async programmatic supervision loop
- [ ] Wire up `auto_approve`, `poll_interval`, `waiting_timeout` from robo config
- [ ] Pattern-based safe-to-approve detection (reads pane content, checks against patterns)
- [ ] LLM escalation: ambiguous cases escalated to robo agent session via MCP tools
- [ ] Robo journal: logs every decision (approved, escalated, timed out)
- [ ] `shoal robo watch` — start the supervision loop as a background daemon

### Design Decisions

- **Hook architecture**: Code-level async callbacks (internal) + fish event emission (external). Python hooks handle infrastructure (journal, DB, robo). Fish events let users customize behavior without writing Python — `notify-send`, ntfy webhooks, custom scripts via `--on-event`.
- **Status history**: Both SQLite table (programmatic queries, robo decision-making) and journal entries (human-readable narrative). Written by a single lifecycle hook.
- **Robo autonomy**: Layered — deterministic Python loop handles simple cases (auto-approve known-safe prompts, timeout escalation). Ambiguous cases escalated to LLM agent session. Programmatic layer uses Python API directly; LLM layer uses MCP tools (each interface used where it's designed for).
- **MCP interface principle**: MCP is the agent interface, Python is the infrastructure interface. They share the same underlying functions. Programmatic code calls Python directly; LLM agents call MCP tools.

## Backlog

- **Linux notifications**: Solved by fish event hooks — users wire `notify-send` or ntfy in their fish config
- **Dashboard actions**: Add fork, approve, send-keys, filter-by-status as fzf popup actions
- **Agent readiness signals**: Poll-until-pattern readiness check replacing `asyncio.sleep(1)` hack after session creation
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()` — investigated, no-go for now ([spike findings](docs/composition-gateway.md)). Revisit when robo supervisor needs unified cross-session MCP or FastMCP adds UDS transport
- **Oh-My-Pi (omp) Integration**: `omp.toml` tool definition and `omp-dev` session template; native MCP via `omp plugin`; detection pattern tuning for omp's extended TUI
- Remote status bar: Fish status bar polls remote WebSocket for session status
- **Robo merge/worktree workflow**: Document merge-back-to-main lifecycle for robo supervisor — concrete instructions in default `AGENTS.md` template and ROBO_GUIDE section covering: branch readiness checks, test verification before merge, safe auto-merge patterns vs. human review, worktree cleanup after merge, and post-session branch deletion. Consider dedicated MCP tools (`merge_branch`, `branch_status`) so robo doesn't need raw `send_keys` for git operations.
- **Per-session git practices**: Once template env vars are wired up (blocked by env var gap), support git identity and conventions per session via `[template.env]` (`GIT_AUTHOR_NAME`, `GIT_COMMITTER_EMAIL`). Longer-term: dedicated `[template.git]` section for commit conventions, hook profiles, and branch naming rules — enabling different practices for admin agents, robo supervisors, and task workers.

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-02-24 — v0.18.0 Phase 2+3 parallel implementation

**What we did:**

- Completed Phase 2 + Phase 3 in parallel via 2 Shoal sessions (`shoal-gateway-spike`, `shoal-session-graph`)
- **Phase 2 final item**: Composition Gateway spike — researched FastMCP `mount()`, decision no-go, wrote `docs/composition-gateway.md`
- **Phase 3 complete**: Session Graph — `parent_id`, `tags`, `template_name` on SessionState
- Added `shoal tag add/remove/ls` CLI subcommand group
- Added `shoal ls --tag` filtering and `--tree` fork-relationship display
- Added `shoal journal --search` for cross-session journal search
- Enhanced `shoal info` with parent, template, and tags display
- 24 new tests in `tests/test_session_graph.py`, 951 total passing
- 4 commits across 2 branches, merged cleanly into main, `just ci` all green

**What to do next:**

- Push to origin and tag release (carried over from previous sessions)
- Update CHANGELOG.md with session graph additions
- Start Phase 4: Robo Supervision Loop (`services/robo_supervisor.py`)
