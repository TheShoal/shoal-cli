# Shoal Orchestration API and Schema Proposal

## Purpose

This document proposes Shoal's stable public orchestration contract so that:

- Pisces can use Shoal as the inter-session execution substrate
- Lobster Party can integrate with Shoal through a clean adapter boundary
- consumers do not need to depend on Shoal SQLite internals or tmux details

This proposal intentionally prioritizes:

1. request/reply messaging
2. workflow correlation
3. action/approval semantics
4. watch/subscription ergonomics

It intentionally defers:

- room/chat abstractions
- shared MCP-memory designs
- direct remote control of runtime internals

## Current baseline

Shoal already exposes these core primitives:

### Runtime/session operations

- session lifecycle and status tools via MCP and CLI
- `send_keys` / `capture_pane` as runtime transport/control
- `mark_complete` / `wait_for_completion` for completion signaling

### Session messaging

Current message MCP tools:

- `send_session_message`
- `receive_session_messages`
- `mark_session_message_consumed`

Current SQLite message schema in `src/shoal/core/db.py`:

- `id`
- `from_session`
- `to_session`
- `topic`
- `payload`
- `created_at`
- `consumed_at`

This is enough for a basic mailbox queue, but not enough for first-class workflow coordination.

## Design goals

### Goal 1: Stable public contract

Pisces and Lobster should be able to integrate through:

- MCP tools
- CLI wrappers
- API endpoints

without needing:

- direct SQLite reads
- tmux knowledge
- private schema coupling

### Goal 2: Correlation-first workflows

Every multi-session workflow should be trackable via a stable correlation or workflow ID.

### Goal 3: Separate messages from actions

A message is not the same as a request to take a privileged action.

### Goal 4: Poll internally, stream externally

Shoal may continue to use polling internally, but public consumers should be able to use watch/subscribe semantics.

## Public orchestration surface

## 1. Session lifecycle

These are the stable session-substrate operations.

### Required operations

- `create_session`
- `kill_session`
- `list_sessions`
- `session_info`
- `session_snapshot`
- `wait_for_completion`
- `mark_complete`
- `branch_status`
- `list_worktree_files`
- `read_worktree_file`

### Notes

- `send_keys` remains public, but should be documented as terminal actuation only.
- `capture_pane` remains public, but should be treated as a debugging/inspection primitive, not the primary workflow protocol.

## 2. Journal and handoff surfaces

### Required operations

- `read_journal`
- `append_journal`
- `sync_claw_conversations` where relevant for Lobster interop

### Optional future improvement

- `append_handoff(workflow_id, from_session, to_session, content, metadata)`

This can remain journal-backed internally while exposing a more workflow-aware API.

## 3. Session messaging surfaces

### Required operations

- `send_session_message`
- `receive_session_messages`
- `mark_session_message_consumed`

### Proposed additions

- `watch_session_messages`
- `get_workflow_messages`
- `ack_session_message`

`watch_session_messages` can be implemented with polling under the hood while exposing an event-like interface to clients.

## 4. Session action surfaces

These are separate from ordinary messages.

### Proposed additions

- `request_session_action`
- `list_pending_session_actions`
- `approve_session_action`
- `deny_session_action`
- `watch_session_actions`

Examples of actions:

- merge branch
- run release command
- edit protected path
- escalate to another role/team
- request manual approval from supervisor

## Message model

## Current limitation

Current messages are just:

- sender
- recipient
- topic
- string payload

That is not enough for:

- request/reply pairing
- multi-step workflow tracing
- approval decisions
- durable integration with Lobster task/thread identity

## Proposed message envelope

### Logical envelope

```json
{
  "id": 123,
  "from_session": "planner",
  "to_session": "worker-a",
  "topic": "code-review",
  "kind": "request",
  "payload": "{\"path\":\"src/api.ts\"}",
  "correlation_id": "wf_01H...",
  "reply_to_message_id": null,
  "priority": 3,
  "requires_ack": false,
  "metadata_json": "{\"workflow\":\"auth-migration\",\"thread_id\":\"...\"}",
  "expires_at": null,
  "created_at": "...",
  "consumed_at": null,
  "acked_at": null
}
```

### Proposed `kind` values

- `request`
- `response`
- `event`
- `handoff`
- `approval_request`
- `approval_decision`
- `error`

### Proposed semantics

- `request`: asks a peer/supervisor/worker for work or a decision
- `response`: terminal or partial response to a prior request
- `event`: progress or status signal
- `handoff`: durable transfer context
- `approval_request`: asks for approval to perform an action
- `approval_decision`: approval result tied to an approval request
- `error`: structured failure signal

## SQLite schema proposal

## 1. Evolve `messages` table

### Current shape

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_session TEXT NOT NULL,
    to_session TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT
)
```

### Proposed shape

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_session TEXT NOT NULL,
    to_session TEXT NOT NULL,
    topic TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'event',
    payload TEXT NOT NULL,
    correlation_id TEXT,
    reply_to_message_id INTEGER,
    priority INTEGER NOT NULL DEFAULT 3,
    requires_ack INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    consumed_at TEXT,
    acked_at TEXT,
    FOREIGN KEY(reply_to_message_id) REFERENCES messages(id)
)
```

### Proposed indexes

```sql
CREATE INDEX idx_messages_to_session_created
ON messages(to_session, created_at);

CREATE INDEX idx_messages_to_session_unconsumed
ON messages(to_session, consumed_at, created_at);

CREATE INDEX idx_messages_correlation
ON messages(correlation_id, created_at);

CREATE INDEX idx_messages_reply_to
ON messages(reply_to_message_id);
```

## 2. Add `session_actions` table

Actions should not be overloaded onto the normal message queue.

### Proposed schema

```sql
CREATE TABLE session_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_session TEXT NOT NULL,
    target_session TEXT,
    target_role TEXT,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    correlation_id TEXT,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    decision_reason TEXT,
    metadata_json TEXT
)
```

### Allowed `status` values

- `pending`
- `approved`
- `denied`
- `expired`
- `cancelled`
- `executed`
- `failed`

### Notes

- `target_session` is for direct requests.
- `target_role` allows supervisor- or role-routed actions later.
- `action_type` should be a constrained enum in code even if stored as text.

## 3. Optional future `workflow_runs` table

Not required immediately, but useful if workflow identity becomes first-class.

### Proposed schema

```sql
CREATE TABLE workflow_runs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT
)
```

This helps unify:

- Pisces `/team` runs
- Lobster tasks/threads
- future Shoal-native workflows

## API semantics

## 1. `send_session_message`

### Current

Minimal sender, recipient, topic, payload.

### Proposed request

```json
{
  "to": "worker-a",
  "topic": "code-review",
  "kind": "request",
  "payload": "{\"path\":\"src/api.ts\"}",
  "from_session": "planner",
  "correlation_id": "wf_123",
  "reply_to_message_id": null,
  "priority": 3,
  "requires_ack": false,
  "metadata": {
    "workflow": "auth-migration"
  }
}
```

### Proposed response

```json
{
  "id": 123,
  "to": "worker-a",
  "topic": "code-review",
  "kind": "request",
  "correlation_id": "wf_123"
}
```

## 2. `receive_session_messages`

### Proposed filters

- `session`
- `topic`
- `kind`
- `correlation_id`
- `unconsumed_only`
- `limit`
- `after_id`

This allows workflow-centric retrieval without scraping entire inboxes.

## 3. `watch_session_messages`

### Proposed request

```json
{
  "session": "planner",
  "correlation_id": "wf_123",
  "topics": ["code-review", "status"],
  "kinds": ["event", "response"],
  "after_id": 120,
  "timeout_seconds": 30
}
```

### Behavior

- Internally poll at a small interval.
- Return new matching messages since `after_id`.
- Allow CLI/MCP/API consumers to treat the result as a stream.

## 4. `request_session_action`

### Proposed request

```json
{
  "requester_session": "worker-a",
  "target_session": "supervisor",
  "action_type": "merge_branch",
  "payload": {
    "branch": "feature/auth",
    "target": "main"
  },
  "correlation_id": "wf_123",
  "metadata": {
    "reason": "all checks passed"
  }
}
```

### Proposed response

```json
{
  "id": 77,
  "status": "pending",
  "action_type": "merge_branch",
  "correlation_id": "wf_123"
}
```

## 5. `approve_session_action` / `deny_session_action`

### Proposed request

```json
{
  "action_id": 77,
  "resolved_by": "supervisor",
  "reason": "validated manually"
}
```

### Proposed response

```json
{
  "id": 77,
  "status": "approved",
  "resolved_by": "supervisor"
}
```

## Backward compatibility

### Message migration strategy

1. Add nullable/new columns with defaults.
2. Continue accepting the old minimal `send_session_message` shape.
3. Default old messages to:
   - `kind = 'event'`
   - `priority = 3`
   - `requires_ack = false`
4. Add richer MCP/API params in a backward-compatible way.
5. Migrate callers gradually.

## Consumer-specific mapping

## Pisces mapping

Pisces should use Shoal as follows:

- `/team` run ID -> `correlation_id`
- planner-to-worker instruction -> `request`
- worker progress -> `event`
- final result -> `response`
- human handoff -> `handoff`
- privileged operation -> `request_session_action`

Pisces should not rely on:

- direct DB queries for critical orchestration
- pane scraping as the main coordination mechanism

## Lobster mapping

Lobster should map:

- Lobster `task_id` -> Shoal `correlation_id`
- Lobster thread/conversation metadata -> Shoal `metadata_json`
- Lobster `AgentToAgent` -> Shoal message or action request
- Lobster subscribe semantics -> Shoal watch surfaces

Lobster should not rely on:

- tmux targeting
- Shoal internal schema
- direct session-runtime internals

## Observability and safety

### Observability

Shoal should emit structured logs/telemetry for:

- message sent
- message consumed
- message acked
- action requested
- action approved/denied
- workflow correlation ID on every event where possible

### Safety

- approval-required actions must be explicit
- messages remain lightweight and non-privileged by default
- raw pane control should remain a separate transport path, not the workflow protocol
- do not log sensitive payload contents unless redacted/summarized

## Non-goals

This proposal does not add:

- chat rooms
- room membership
- broadcast pubsub semantics
- shared MCP-memory as cross-session state

Those are separate future decisions.

## Recommended implementation order

### Phase 1

- enrich message schema
- add correlation semantics
- keep current tools backward compatible

### Phase 2

- add action request table and tools
- add approval/deny flows

### Phase 3

- add watch/message polling wrappers
- expose workflow-centric retrieval

### Phase 4

- add optional `workflow_runs`
- map Lobster and Pisces workflow identities cleanly

## Implementation status

### P0 — Contract stabilization (shipped)

All schema enrichments and baseline tools are live in `src/shoal/`.

| Surface | File | Notes |
|---|---|---|
| `MessageEnvelope` model | `src/shoal/models/message.py` | Pydantic; all 7 `MessageKind` values |
| `SessionAction` model | `src/shoal/models/action.py` | `ActionStatus` StrEnum |
| Enriched `messages` DDL | `src/shoal/core/db.py` | Additive migration; existing rows unaffected |
| `session_actions` DDL | `src/shoal/core/db.py` | Separate table, not message queue |
| `send_session_message` | `mcp_shoal_server.py` | Now accepts all envelope fields |
| `receive_session_messages` | `mcp_shoal_server.py` | Filters: topic, kind, correlation_id, after_id |
| `mark_session_message_acked` | `mcp_shoal_server.py` | Sets `acked_at` |
| `request_session_action` | `mcp_shoal_server.py` | Creates pending action |
| `list_pending_session_actions` | `mcp_shoal_server.py` | Supports target_session / target_role filter |
| `approve_session_action` | `mcp_shoal_server.py` | Sets status → approved |
| `deny_session_action` | `mcp_shoal_server.py` | Sets status → denied |

### P1 — Watch and workflow surfaces (shipped)

| Surface | File | Notes |
|---|---|---|
| `watch_session_messages` | `mcp_shoal_server.py` | Polling loop; returns on first hit or timeout |
| `get_workflow_messages` | `mcp_shoal_server.py` | Cross-session trace by correlation_id |
| `watch_session_actions` | `mcp_shoal_server.py` | Polling loop over pending action bus |
| `db.get_workflow_messages` | `src/shoal/core/db.py` | No to_session filter; ordered by id |
| `message_bus.get_workflow_messages` | `src/shoal/core/message_bus.py` | Thin wrapper |
| `action_bus.watch_pending_actions` | `src/shoal/core/action_bus.py` | Returns `list[SessionAction]` |
| `session_summary` enriched | `mcp_shoal_server.py` | Now includes `active_workflow_ids` |

### Deferred

- `workflow_runs` table
- room/chat abstractions
- shared MCP-memory
- direct Lobster tmux control

---

## P1 MCP tool contracts

### `watch_session_messages`

Blocks until matching messages arrive or the timeout elapses.
Internal implementation polls SQLite at `poll_interval` (default 1 s).

**Input**

| Field | Type | Default | Description |
|---|---|---|---|
| `session` | string | required | Recipient session to watch |
| `topic` | string | null | Filter by topic |
| `kind` | string | null | Filter by `MessageKind` |
| `correlation_id` | string | null | Filter by workflow ID |
| `after_id` | int | null | Only messages with id > this value |
| `timeout_seconds` | float | 30 | Max wall-clock seconds to wait |

**Output** — list of message objects (same shape as `receive_session_messages`).

**Side effects** — none; consumed state is not modified.

**`readOnlyHint`** — false (the polling loop does not mutate state, but the tool
is not marked read-only to avoid caching by model context).

---

### `get_workflow_messages`

Returns all messages across every session that share the given `correlation_id`.
Ordered ascending by `id`.

**Input**

| Field | Type | Default | Description |
|---|---|---|---|
| `correlation_id` | string | required | Workflow/correlation ID to query |
| `kind` | string | null | Optional `MessageKind` filter |
| `limit` | int | 100 | Max rows returned |
| `after_id` | int | null | Only messages with id > this value |

**Output** — list of message objects.

**`readOnlyHint`** — true.

---

### `watch_session_actions`

Blocks until pending `session_actions` rows match the filters, or the timeout
elapses.  Approved/denied actions are excluded.

**Input**

| Field | Type | Default | Description |
|---|---|---|---|
| `target_session` | string | null | Filter by target_session |
| `target_role` | string | null | Filter by target_role |
| `correlation_id` | string | null | Filter by workflow ID |
| `timeout_seconds` | float | 30 | Max wall-clock seconds to wait |

**Output** — list of `SessionAction` objects (same shape as `list_pending_session_actions`).

**`readOnlyHint`** — false (polling may be cached incorrectly if marked read-only).

---

### `session_summary` enrichment

All return paths now include:

```json
{
  "active_workflow_ids": ["wf_01H...", "wf_02X..."]
}
```

`active_workflow_ids` is the sorted list of distinct `correlation_id` values from
unconsumed messages currently sitting in the session's inbox.
Returns an empty list when no unconsumed workflow messages exist.


## Definition of done

Shoal's orchestration substrate is successful when:

- Pisces can use Shoal without depending on Shoal SQLite internals
- Lobster can integrate with Shoal through a stable contract
- request/reply workflows are first-class
- approvals are first-class
- `send_keys` is no longer treated as a messaging substitute
