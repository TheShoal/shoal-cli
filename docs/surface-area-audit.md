# Shoal Surface Area Audit

> **Purpose**: Identify opportunities to reduce surface area, abandon loose ends, and consolidate core features.
> **Date**: 2026-04-03
> **Scope**: Source code (`src/shoal/`), tests, docs, mkdocs nav

---

## TL;DR

Shoal's core is solid — lifecycle, MCP pooling, worktrees, status detection, journals. The problems are around the edges: a dead `CoordinatorService`, a fin ecosystem that doesn't exist yet, a Lobster integration that might belong in its own package, ~18 test files for gRPC/Claw/Lobster features that require external endpoints, and docs that have drifted from the current defaults and feature set.

There are no architecture issues. There is feature accumulation.

---

## 1. Dead Code

### `services/coordinator.py` — 302 LOC, never instantiated

The `CoordinatorService` class polls agent sessions for completion and manages squash-merge of worktree commits. It's fully implemented. It is referenced in zero non-test files — no CLI command, no API endpoint, no lifecycle wiring.

- **Evidence**: `grep -r "CoordinatorService" src/` returns only `coordinator.py` itself.
- **Changelog claim**: v0.32.0 says "Agent Teams: Create sessions that spawn nested parallel agent sub-sessions." No `shoal team` command exists. No `--team` flag exists anywhere in the CLI.
- **Action**: Delete `coordinator.py` and the associated tests, or commit to wiring it — pick one. The "Agent Teams" entry in CHANGELOG is inaccurate as written.

### Unused `EscalationConfig` fields

`src/shoal/models/config/robo.py`:

```python
class EscalationConfig(BaseModel):
    notify: bool = True          # never read anywhere outside this model
    auto_respond: bool = False   # same
```

Neither field is consumed by `robo_supervisor.py`, the CLI, or any hook. They are configuration surface with no behavior attached.

- **Action**: Remove both fields. If `notify` is intended for a future notification hook, document it clearly as reserved.

### `TasksConfig.log_file`

`src/shoal/models/config/robo.py`:

```python
class TasksConfig(BaseModel):
    log_file: str = "task-log.md"   # never read
```

`TasksConfig` is exported from `models/config/__init__.py` and held as `RoboProfileConfig.tasks`, but `log_file` is never accessed in any code path.

- **Action**: Remove `log_file` from `TasksConfig`, or remove `TasksConfig` entirely if it has no other purpose.

---

## 2. Features That Are Wired but Not Discoverable

### `Dreamer` LLM summarizer — off by default, no CLI to enable

`DreamerConfig` lives in `models/config/general.py` with `enabled: bool = False`. There is no `shoal config dreamer enable` or equivalent command. Users must hand-edit `config.toml` to activate it, then discover there's a `session_summary` MCP tool. The feature is real and useful but invisible.

- **Docs gap**: No "Prerequisites" section on any Dreamer-related docs.
- **Action**: Either add a `shoal dreamer` CLI sub-group (enable/disable/status), or add a prominent callout in relevant docs showing the required config.

### `ProactiveSupervisor` (Scout) — gated, undiscoverable

Wired into lifecycle bootstrap (v0.37.1 fix), but guarded by `cfg.proactive.enabled`. No CLI command to check or manage proactive state beyond `shoal proactive fs-watch start/status` and `shoal proactive message send/list`. The config path to enable it is undocumented in any user-facing doc.

- **Action**: Add a short "Enabling proactive supervision" section to `ROBO_GUIDE.md` showing the required `config.toml` entries.

### Web dashboard — not linked from CLI

The dashboard (HTMX, WebSocket fleet view) is real and ships with the API. It lives at `/ui` when `shoal api start` is running. There is no `shoal dashboard` command that opens it. `docs/cli-reference.md` does not mention it.

- **Action**: Add `shoal dashboard` as an alias for `shoal api start` (or a command that prints the URL), and add a one-liner to the CLI reference.

---

## 3. Scope Creep Candidates

These features are real and working but extend well beyond "terminal-first orchestration for parallel AI agents on one machine."

### Lobster Party integration

Introduced in v0.30.0, renamed in v0.37.0. Adds:

- Proto stubs: `src/shoal/core/proto/` (~600 LOC generated)
- `LobsterRuntimeProvider` in `services/runtime_providers/lobster.py`
- `shoal[lobster]` optional extra (grpcio + protobuf)
- 5 MCP tools (`send_a2a_message`, `get_agent_card`, `list_a2a_tasks`, `approve_session_action`, `deny_session_action`)
- `shoal lobster` CLI subgroup
- 18 test files for claw/a2a/lobster features (see §5 below)

The integration is complete but the smoke tests against a real Lobster endpoint remain in the backlog. The feature is hidden behind an extra and never runs in CI.

- **Assessment**: Lobster integration is a separate concern from local orchestration. It's more `shoal-lobster` than `shoal`.
- **Action (medium-term)**: Extract to a `shoal-lobster` plugin package that installs the extra and the runtime provider. Or formally declare it a supported integration tier and add it to the CI matrix with a mock endpoint.

### Incident supervision

Introduced in v0.26.0. Adds `shoal incident ingest/ls/show/spawn/resolve`, JSON alert ingestion, incident roles, SQLite `incidents` table, 5 REST endpoints. It's a real feature but solves an ops-on-call problem, not the core "run parallel coding agents" problem.

- **Assessment**: Functional but niche. Adds ~500 LOC and 5 CLI commands for a workflow most users will never encounter.
- **Action**: Keep but move to a dedicated "Advanced / Incident Response" section in the docs so it doesn't crowd the getting-started surface.

### Fin extension system

Introduced in v0.19.0. Adds `shoal fin install/inspect/validate/run/ls`, contract v1, `fin_runtime.py`, `fin_repo.py`. No fins ship with the distribution. No fin registry exists. The contract-v1 spec is documented in `docs/EXTENSIONS.md` but `EXTENSIONS_REVIEW.md` is a draft that hasn't landed in the nav.

- **Assessment**: Building an extension system before the ecosystem exists is premature. Currently adds CLI surface and maintenance burden for zero user value.
- **Action**: Either ship one built-in fin that demonstrates real value, or soft-deprecate the `shoal fin` commands in the CLI (`[EXPERIMENTAL]` marker) to signal maturity level honestly.

---

## 4. Config Model Issues

### Duplication: `ProactiveConfig` vs `ProactiveSupervisorConfig`

Two separate config models for proactive supervision:

- `GeneralConfig.proactive: ProactiveConfig` (top-level, `watch_paths`, `enabled`)
- `RoboProfileConfig.proactive: ProactiveSupervisorConfig` (robo-scoped, `auto_enqueue`, `failure_ttl_seconds`, `trigger_topics`)

These serve different scopes (global vs per-profile), which is defensible, but the split is not documented and the naming is nearly identical.

- **Action**: Add inline comments in `robo.py` and `general.py` explaining the distinction. Consider renaming `ProactiveSupervisorConfig` to `RoboProactiveConfig` to make the scoping obvious.

### `prompt_flag` field on `ToolConfig` — unused in all shipped configs

`src/shoal/models/config/tools.py` has `prompt_flag: str = ""` for `input_mode="flag"`. All shipped tool configs (omp, claude, opencode, pisces, pi) use either `input_mode="keys"` or `"arg"`. No tool config sets `prompt_flag`.

- **Not a bug**: The field is correctly wired in `core/prompt_delivery.py`. It's just that no tool uses `"flag"` mode.
- **Action**: Either add a comment "Used by tools with a `--prompt` flag (none currently shipped)" or add an example tool that uses it, so it doesn't look like dead config.

---

## 5. Test File Proliferation

104 test files. 18 relate to Lobster/Claw/A2A features:

```
test_a2a_bridge.py
test_a2a_grpc_roundtrip.py
test_a2a_live.py             ← requires live endpoint, rarely run
test_claw_bootstrap.py
test_claw_conversations.py
test_claw_db.py
test_claw_mcp.py
test_claw_provider.py
test_claw_scheduler.py
test_claw_summarizer.py
test_clawplexer_sync.py
test_mcp_claw_tools.py
test_runtime_lobster.py
test_services_runtime_providers_lobster.py
```

Plus:

```
test_coverage_boost.py       ← exists to hit coverage threshold, not validate behavior
test_coverage_session.py     ← same
test_session_coverage_gaps.py ← same
test_v080_features.py        ← historical feature snapshot, not regression-focused
```

The Lobster test files collectively test a feature that runs in CI with no real endpoint. The coverage-boost files add noise without adding confidence.

- **Action**:
  - Mark `test_a2a_live.py` explicitly `@pytest.mark.lobster_live` and gate behind an env var (may already be done — worth confirming)
  - Consolidate `test_coverage_boost.py`, `test_coverage_session.py`, `test_session_coverage_gaps.py` into the modules they cover, or delete if they duplicate existing tests
  - Consider merging `test_a2a_bridge.py` + `test_a2a_grpc_roundtrip.py` since they test the same boundary

---

## 6. Docs vs. Reality Gaps

### Docs in the repo but not in `mkdocs.yml` nav

These files exist and are maintained but aren't surfaced to users:

| File | Status |
|------|--------|
| `docs/OMP_INTEGRATION_FIXES.md` | Post-mortem from v0.29.0 era. No longer actionable. |
| `docs/python-improvements.md` | Startup performance spike. Partially shipped (lazy imports). |
| `docs/rewrite-evaluation.md` | Go/Rust rewrite evaluation from 2026-03-31. Decision made (stay Python). |
| `docs/EXTENSIONS_REVIEW.md` | Draft review of the fin system. Never published. |
| `docs/implementation-audit.md` | In the nav under "Design the Loop" — but it's a development artifact, not user-facing. |

- **Action**: Move `OMP_INTEGRATION_FIXES.md`, `python-improvements.md`, `rewrite-evaluation.md`, and `EXTENSIONS_REVIEW.md` to `docs/archive/` (or delete). Update `implementation-audit.md` scope comment to clarify it's internal.

### Tool default drift

v0.29.0 changed the default tool from `pi` to `omp`. Several docs still reference `pi` as primary:

- `docs/AGENTS.md` — references Pi as "primary reference backend"
- `docs/getting-started.md` — `pi` in code examples
- `docs/ROBO_GUIDE.md` — `pi` in robo profile examples
- `ARCHITECTURE.md` — "Pi is the primary reference backend for status detection"

- **Action**: Global replace of `pi` → `omp` in all user-facing examples, add a "Supported tools" table that lists omp (primary), claude, opencode, pisces (secondary).

### CLI reference is incomplete

`docs/cli-reference.md` is missing:

- `shoal incident` subgroup (ingest, ls, show, spawn, resolve)
- `shoal proactive` subgroup (fs-watch start/status, message send/list)
- `shoal fin` subgroup (install, inspect, validate, run, ls)
- `shoal session` alias subgroup (added v0.36.0)
- `shoal dashboard` (once added)

- **Action**: Either generate the reference from typer introspection, or add a quarterly "sync CLI reference" task.

### `ROBO_GUIDE.md` predates Scout and Agent Bus

`ROBO_GUIDE.md` covers the basic supervision loop but doesn't mention:

- `ProactiveSupervisor` (added v0.36.0)
- Agent Bus messaging (`send_session_message` / `receive_session_messages`)
- `FsWatcher` and `file_changed` events
- `get_failure_context` MCP tool

- **Action**: Add a "Proactive Supervision" section to `ROBO_GUIDE.md` covering Scout configuration and the failure-context workflow.

---

## 7. Priority Matrix

| Issue | Impact | Effort | Recommendation |
|-------|--------|--------|----------------|
| Delete `CoordinatorService` | Medium (dead code misleads) | Low | Do it |
| Remove `notify`, `auto_respond`, `log_file` from config models | Low | Low | Do it |
| Archive stale docs (`OMP_INTEGRATION_FIXES`, `python-improvements`, `rewrite-evaluation`, `EXTENSIONS_REVIEW`) | Low | Low | Do it |
| Fix tool default in all docs (`pi` → `omp`) | Medium (confuses new users) | Low | Do it |
| Add `shoal dashboard` command + CLI reference entry | Medium (discoverability) | Low | Do it |
| Add proactive supervision docs to `ROBO_GUIDE.md` | Medium | Low | Do it |
| Mark `shoal fin` as `[EXPERIMENTAL]` in CLI help | Medium (sets expectations) | Low | Do it |
| Consolidate coverage-boost test files | Low | Low | Do it |
| Extract Lobster to plugin or add CI mock endpoint | High (ongoing maintenance) | High | Decide: in or out |
| Complete `CoordinatorService` wiring (if keeping) | Medium | High | Defer or delete |
| Add `shoal dreamer` CLI command | Low | Medium | Defer |
| Fix CHANGELOG v0.32.0 "Agent Teams" claim | Low (misleads future contributors) | Low | Fix the text |

---

## 8. What to Leave Alone

These are sometimes flagged in surface-area audits but are correct here:

- **Runtime provider abstraction** (`services/runtime_providers/`) — one implementation today, but the seam is correct and lobster.py already uses it. Keep.
- **3-level config nesting** — reflects genuine scoping (global < profile < template < CLI). Correct, just needs better docs.
- **18 lifecycle hooks** — the hook architecture is clean; adding hooks is cheap. Not over-engineered.
- **SQLite schema complexity** — 8+ tables, but all tables have active code paths. None are orphaned.
- **MCP tool count (47)** — high, but MCP is the agent interface; richness here directly serves the core purpose.

---

## Summary

The core of Shoal is healthy. The surface-area issues break into three buckets:

1. **Trash to collect** (low effort, clear win): dead `CoordinatorService`, unused config fields, stale docs, tool-default drift in examples. None of these require design decisions — just delete or fix.

2. **Features that need a label** (low effort, sets honest expectations): mark `shoal fin` as experimental, add a proactive/dreamer enabling guide, link the dashboard from somewhere discoverable.

3. **One real strategic question**: Does Lobster Party integration belong in shoal-cli, or in a `shoal-lobster` plugin? It's complete and tested, but it's a different problem domain (federation vs local orchestration) and it's dragging 18 test files and 600 LOC of proto stubs into the core. Making this call would clean up the largest remaining complexity cluster.
