# Flows: Declarative Multi-Agent Coordination

!!! warning "Proposal — not yet implemented"
    This is a design document, not a shipped feature. None of the `shoal flow` commands described here exist yet. For the current multi-agent coordination primitives see [Agent Teams](features.md#agent-teams) and [Robo Supervisor](ROBO_GUIDE.md).

**Date**: 2026-03-31
**Status**: Design (not yet implemented)

## Summary

Flows are a declarative, TOML-defined way to launch and manage a group of related sessions as a single unit. A flow is to Shoal sessions what `docker-compose.yml` is to containers: a named topology of lanes (sessions) with optional dependency ordering, shared context, and group-level operations.

Flows compose — they don't replace — templates, modes, tags, worktrees, robo supervision, and lifecycle hooks.

---

## 1. Problem Statement

Shoal has strong primitives for individual sessions: templates, modes, tags, worktrees, MCP sharing, handoff artifacts, and lifecycle events. Multi-agent coordination works today through implicit conventions:

- Naming (`feat/auth`, `review/auth`) implies relationships
- Tags (`implementer`, `review-ready`) imply roles
- `parent_id` tracks forks but nothing broader
- Robo supervision discovers workers by polling status, not by team membership
- Batch MCP ops require enumerating session names manually

This means:

1. **No declarative topology** — Every multi-agent run is hand-assembled via sequential `shoal new` calls
2. **No group identity** — "These 4 sessions are one effort" exists only in the operator's head
3. **No dependency sequencing** — Launching a reviewer before the implementer finishes requires manual timing
4. **No group operations** — Killing a multi-session effort means N individual kills
5. **No automatic handoff flow** — Context from upstream sessions doesn't auto-propagate downstream

---

## 2. Design

### 2.1 Flow Spec (TOML)

```toml
[flow]
name = "auth-rework"
description = "Rework auth middleware for compliance"

[[flow.lanes]]
role = "planner"
template = "claude-dev"
mode = "planner"
branch = "plan/auth-rework"
prompt = "Review the auth middleware and produce a compliance rework plan"

[[flow.lanes]]
role = "impl-tokens"
template = "pi-dev"
mode = "implementer"
depends_on = "planner"
branch = "impl/auth-tokens"
prompt = "Implement token storage changes per the plan"

[[flow.lanes]]
role = "impl-sessions"
template = "pi-dev"
mode = "implementer"
depends_on = "planner"
branch = "impl/auth-sessions"

[[flow.lanes]]
role = "reviewer"
template = "claude-review"
mode = "reviewer"
depends_on = ["impl-tokens", "impl-sessions"]
branch = "review/auth-rework"
```

**Flow-level fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | yes | Unique flow identifier |
| `description` | str | no | Human-readable purpose |

**Lane fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | str | yes | Unique within flow; becomes session name suffix |
| `template` | str | yes | Session template to use |
| `mode` | str | no | Operating mode override |
| `branch` | str | no | Git branch name |
| `prompt` | str | no | Initial prompt sent after agent launch |
| `depends_on` | str or list[str] | no | Role name(s) that must reach idle/done before this lane launches |
| `tags` | list[str] | no | Additional tags (merged with template + mode tags) |
| `env` | table | no | Extra env vars for this lane |

**Session naming**: `{flow.name}/{lane.role}` — e.g., `auth-rework/planner`, `auth-rework/impl-tokens`.

### 2.2 Discovery & Storage

**Flow specs** live in:
1. `~/.config/shoal/flows/*.toml` (user-global)
2. `.shoal/flows/*.toml` (project-local, git root)
3. Inline via `shoal flow start --file path/to/flow.toml`

**Flow state** is stored in SQLite:

```sql
CREATE TABLE flows (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    spec_path TEXT,
    status TEXT NOT NULL DEFAULT 'active',  -- active, completed, killed
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

Sessions gain a nullable `flow_id` foreign key:

```sql
ALTER TABLE sessions ADD COLUMN flow_id TEXT REFERENCES flows(id);
ALTER TABLE sessions ADD COLUMN flow_role TEXT;  -- lane role within the flow
```

### 2.3 CLI Surface

```bash
# Flow lifecycle
shoal flow start <name|file>     # Launch a flow (create lanes per spec)
shoal flow status [name]         # Show lane states + dependency progress
shoal flow kill <name>           # Kill all lanes, mark flow completed
shoal flow ls                    # List active flows

# Operating on flow lanes
shoal flow attach <name> <role>  # Attach to a specific lane
shoal flow log <name>            # Aggregate journal entries across lanes

# Discovery
shoal flow list-specs            # Show available flow definitions
shoal flow show <name>           # Print resolved flow spec
```

**Example `shoal flow status auth-rework` output:**

```
auth-rework — Rework auth middleware for compliance
  planner        idle     plan/auth-rework       done (14m)
  impl-tokens    running  impl/auth-tokens       12m active
  impl-sessions  waiting  impl/auth-sessions     needs approval
  reviewer       pending  —                      blocked on: impl-tokens, impl-sessions
```

Status meanings:
- Lane statuses map directly to `SessionStatus` (running, waiting, idle, error, stopped)
- `pending` = not yet launched (waiting on `depends_on`)
- `blocked on: X` = dependency X hasn't reached target status

### 2.4 Dependency Resolution

Dependencies form a DAG (validated at parse time — cycles are rejected).

**Trigger condition**: A pending lane launches when **all** its `depends_on` lanes reach `idle` or `stopped` status. This hooks into the existing `status_changed` lifecycle event.

```python
async def _on_status_changed(event: LifecycleEvent, **kwargs: Any) -> None:
    session = kwargs["session"]
    if session.flow_id and kwargs["new_status"] in ("idle", "stopped"):
        await _check_and_launch_pending_lanes(session.flow_id)
```

**Handoff injection**: When a dependency is met, the upstream session's `HandoffArtifact` is appended to the downstream session's journal before launch. This gives the downstream lane full context without manual copy.

### 2.5 MCP Integration

New orchestration tools:

| Tool | Description |
|------|-------------|
| `flow_start` | Launch a flow by name or inline spec |
| `flow_status` | Get lane states for a flow |
| `flow_kill` | Kill all lanes in a flow |

Robo supervisors and orchestrator agents can manage flows through the same MCP interface they use for individual sessions.

### 2.6 Robo Integration

Robo supervision works unchanged — it still polls sessions by status. But flow metadata enables smarter decisions:

- Robo can query `session.flow_role` to know a session's purpose
- Robo can check flow-level progress ("is the whole flow stuck or just one lane?")
- Escalation context includes flow name and role for better LLM decisions

---

## 3. What Flows Are NOT

- **Not a DAG runner** — No retries, conditional branches, loops, or error recovery. A flow launches lanes and tracks their status. If a lane fails, the operator decides what to do.
- **Not an org chart** — No hierarchy, delegation chains, or chain-of-command. `depends_on` is sequencing, not authority.
- **Not replacing templates/modes** — Flows compose them. Every lane is still a template-based session.
- **Not mandatory** — `shoal new` continues to work for ad-hoc sessions. Flows are opt-in for multi-agent patterns.
- **Not Paperclip** — No companies, budgets, approvals FSM, or heartbeat protocol. Flows are topology, not governance.

---

## 4. Implementation Plan

### Phase 1 — Flow spec + start/status/kill (MVP)

**Goal**: Declare a multi-lane topology and launch/manage it as a unit.

- [ ] `models/flow.py` — `FlowSpec`, `LaneSpec` Pydantic models with TOML parsing
- [ ] `core/flow.py` — Flow spec discovery (user-global + project-local), validation (DAG cycle check, role uniqueness, template existence)
- [ ] DB migration — `flows` table + `flow_id`/`flow_role` columns on `sessions`
- [ ] `services/flow_manager.py` — `start_flow()`, `kill_flow()`, `flow_status()`
  - `start_flow` creates all lanes via `lifecycle.create_session_lifecycle()`, sets `flow_id` + `flow_role`
  - MVP: all lanes launch immediately (no `depends_on` yet)
- [ ] `cli/flow.py` — `shoal flow start`, `shoal flow status`, `shoal flow kill`, `shoal flow ls`
- [ ] Tests — spec parsing, validation, start/kill lifecycle, status rendering

**No `depends_on` in Phase 1** — all lanes launch in parallel. This keeps the MVP small while still delivering group identity and group operations.

### Phase 2 — Dependency sequencing

**Goal**: Lanes launch automatically when their dependencies are satisfied.

- [ ] DAG resolution in `flow_manager.py` — topological sort, launch root lanes immediately, hold others as `pending`
- [ ] Lifecycle hook on `status_changed` — check pending lanes, launch when ready
- [ ] `pending` pseudo-status for lanes not yet created as sessions
- [ ] Flow status view shows dependency state (blocked on X, Y)
- [ ] Handoff injection — auto-append upstream `HandoffArtifact` to downstream journal on launch

### Phase 3 — MCP + robo integration

**Goal**: Agents and robo can manage flows programmatically.

- [ ] MCP tools: `flow_start`, `flow_status`, `flow_kill`
- [ ] `flow_role` in session snapshot responses
- [ ] Robo-aware flow context in escalation prompts
- [ ] `shoal flow attach <name> <role>` convenience command
- [ ] `shoal flow log <name>` aggregated journal view

### Phase 4 — Ergonomics

**Goal**: Quality-of-life for daily flow usage.

- [ ] `shoal flow create <name>` — interactive flow spec scaffolding
- [ ] Flow templates (meta-templates that define common topologies: author-reviewer, planner-impl-review)
- [ ] `shoal popup` flow-aware grouping (flow lanes grouped visually)
- [ ] Fish completions for flow names and roles

---

## 5. Mapping to Existing Primitives

| Flow concept | Builds on | New code |
|---|---|---|
| Flow spec | Template TOML parsing patterns | `models/flow.py` |
| Lane | `create_session_lifecycle()` | `flow_id`/`flow_role` fields |
| Group operations | Batch MCP ops | `flow_manager.kill_flow()` |
| Dependency sequencing | `status_changed` lifecycle event | Hook + pending state tracking |
| Handoff injection | `HandoffArtifact` | Auto-append on dependency met |
| Flow status | `urgency.py` + session status | Aggregation view |
| MCP integration | `mcp_shoal_server.py` | 3 new tools |
| Robo integration | `robo_supervisor.py` | Flow-aware context |

---

## 6. Open Questions

1. **Lane restart semantics** — If a lane errors out, should `shoal flow restart <name> <role>` re-create just that lane? Or does the operator kill + manually re-create?

2. **Flow-level tags** — Should the flow spec support tags that propagate to all lanes? (Probably yes — `flow.tags = ["sprint-42"]` applied to every lane session.)

3. **Partial start** — Should `shoal flow start` support `--only <role>` to launch a subset of lanes?

4. **Flow completion** — When is a flow "done"? All lanes idle? All lanes stopped? Explicit `shoal flow complete`?

5. **Flow-scoped MCP** — Should flows support a shared MCP server list that all lanes inherit? (May overlap with template MCP inheritance.)

6. **Remote lanes** — Can a lane target a remote host? This would compose with `shoal remote` but adds significant complexity.

---

## 7. Relation to Paperclip

This design is informed by Paperclip's company/agent/issue model but deliberately simpler:

| Paperclip | Shoal Flows | Why different |
|---|---|---|
| Company (multi-tenant org) | Flow (named session group) | Shoal is single-operator |
| Agent (persistent employee) | Lane (session with a role) | Sessions are ephemeral, not permanent |
| Issue + checkout (task tracker) | `depends_on` + handoff | No separate task model needed — the session IS the work unit |
| Heartbeat (bounded execution) | Long-running sessions | Shoal sessions run until done, not in cycles |
| Org hierarchy (CEO → IC) | Flat lanes with sequencing | No authority model, just ordering |
| Budget enforcement | Not in scope | Could layer on later via cost tracking |

The key insight from Paperclip: **group identity matters**. Being able to say "these sessions are one effort" and operate on them as a unit is the 80/20 feature. The governance, budgets, and hierarchy are Paperclip-specific concerns Shoal doesn't need.
