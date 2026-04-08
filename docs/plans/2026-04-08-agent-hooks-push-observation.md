# Agent Hooks Push Observation — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace tmux-pane scraping as the primary session observation mechanism with a hook-based push model where agents (Pisces, Claude Code) notify Shoal of state transitions in real time, while keeping tmux as a fallback for crash detection and uninstrumented agents.

**Architecture:** Add a `POST /sessions/{name}/heartbeat` REST endpoint to Shoal's API server and a new `heartbeat` MCP tool. Agents call this at `turn_end` (Pisces) or `PostToolUse` (Claude Code) to push structured status. The Watcher remains as a liveness watchdog but at reduced frequency. A new `StatusSource` enum tracks whether status came from `hook` or `watcher`, enabling graceful deprecation.

**Tech Stack:** Python 3.12+ / FastAPI / SQLite / Pydantic / TypeScript (Pisces hooks) / Shell (Claude Code hooks)

---

## Background

Currently Shoal observes agent sessions via passive polling: the `Watcher` runs a loop every 5s, calls `tmux capture-pane` on each session, runs regex patterns against the output to detect `running|waiting|error|idle|stopped`, and updates state. This is:

- **Fragile** — regex patterns break when agents update their TUI
- **High-latency** — up to 5s delay before state transitions are noticed
- **Coarse** — can only detect broad states, not turn boundaries or tool results
- **Wasteful** — constant subprocess calls even when nothing changed

Agents that support hooks (Pisces with `turn_end`, Claude Code with `PostToolUse`) can push this information proactively, making observation instant, reliable, and rich.

## Design

### Status Sources

```python
class StatusSource(StrEnum):
    hook = "hook"        # Agent pushed via heartbeat
    watcher = "watcher"  # Watcher detected via tmux scrape
```

Every `SessionState` gets a new `status_source: StatusSource` field. When a hook heartbeat arrives, the status source flips to `hook` and the Watcher skips that session (or polls at a reduced cadence). If no heartbeat is received within a timeout (default 60s), the session falls back to `watcher`-based observation.

### Heartbeat Payload

```python
class HeartbeatRequest(BaseModel):
    status: SessionStatus            # running | waiting | idle | error | stopped
    summary: str = ""                # One-line description of current turn
    turn_number: int | None = None   # Monotonic turn counter (Pisces)
    tool_name: str | None = None     # Last tool called (PostToolUse)
    tool_result: str | None = None   # Abbreviated tool result
    metadata: dict[str, object] = {} # Extensible bag for future use
```

### API Endpoint

```
POST /sessions/{session_name_or_id}/heartbeat
```

Lightweight — just updates status + writes a journal entry. No need to go through the batch system.

### MCP Tool

```
heartbeat(session, status, summary?, turn_number?, tool_name?, metadata?)
```

So agents already connected to Shoal's MCP server can call this natively.

### Watcher Changes

The Watcher gains a `skip_if_hook` mode:

1. If `session.status_source == "hook"` **and** `session.last_activity < 60s ago` → skip the session entirely
2. If `session.status_source == "hook"` **and** `session.last_activity > 60s ago` → treat as stale, switch back to `watcher`, log a warning
3. If `session.status_source == "watcher"` → poll as normal

This means a hung/crashed agent that stops sending heartbeats automatically falls back to tmux observation within 60s.

### Agent Hook Configuration

**Pisces** (`turn_end` TypeScript hook):
```typescript
// .pisces/hooks/turn_end.ts
export default async function(ctx: HookContext) {
  await fetch(`http://localhost:${SHOAL_PORT}/sessions/${SHOAL_SESSION}/heartbeat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      status: 'waiting',
      summary: ctx.summary || '',
      turn_number: ctx.turnNumber,
    }),
  });
}
```

**Claude Code** (`PostToolUse` shell hook in `settings.json`):
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "",
      "command": "fish -c 'shoal heartbeat $SHOAL_SESSION waiting --summary \"$SHOAL_TOOL\"'"
    }]
  }
}
```

---

## Tasks

### Task 1: Add `StatusSource` enum and `status_source` field to `SessionState`

**Objective:** Extend the data model to track where a session's status came from.

**Files:**
- Modify: `src/shoal/models/state.py`

**Step 1: Add `StatusSource` enum**

In `src/shoal/models/state.py`, add after `SessionStatus`:

```python
class StatusSource(StrEnum):
    """Tracks how the current status was determined."""
    hook = "hook"        # Agent pushed via heartbeat endpoint
    watcher = "watcher"  # Watcher detected via tmux scrape
```

**Step 2: Add `status_source` and `last_heartbeat` fields to `SessionState`**

```python
class SessionState(BaseModel):
    # ... existing fields ...
    status_source: StatusSource = StatusSource.watcher
    last_heartbeat: datetime | None = None
```

**Step 3: Update DB schema**

In `src/shoal/core/db.py`, add `status_source` and `last_heartbeat` columns to the sessions table migration. Default `status_source` to `"watcher"` and `last_heartbeat` to `NULL`.

**Step 4: Update `update_session` in `src/shoal/core/state.py`**

Ensure the `update_session` function persists `status_source` and `last_heartbeat` to SQLite.

**Step 5: Run tests**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: add StatusSource enum and status_source/last_heartbeat fields"
```

---

### Task 2: Add `HeartbeatRequest` model and `POST /sessions/{name}/heartbeat` endpoint

**Objective:** Create the REST API endpoint that agents call to push their status.

**Files:**
- Create: `src/shoal/models/heartbeat.py`
- Modify: `src/shoal/api/server.py`

**Step 1: Create `HeartbeatRequest` model**

Create `src/shoal/models/heartbeat.py`:

```python
"""Models for agent heartbeat (push status) requests."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shoal.models.state import SessionStatus


class HeartbeatRequest(BaseModel):
    """Payload pushed by an agent at end-of-turn or after tool use."""

    status: SessionStatus
    summary: str = ""
    turn_number: int | None = None
    tool_name: str | None = None
    tool_result: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
```

**Step 2: Add heartbeat endpoint to API server**

In `src/shoal/api/server.py`, add:

```python
from shoal.models.heartbeat import HeartbeatRequest
from shoal.models.state import StatusSource

@app.post("/sessions/{session_ref}/heartbeat")
async def heartbeat_api(session_ref: str, data: HeartbeatRequest) -> dict[str, object]:
    """Receive a status push from an agent hook."""
    session = await find_by_name(session_ref) or await get_session(session_ref)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(UTC)

    updated = await update_session(
        session.id,
        status=data.status,
        status_source=StatusSource.hook,
        last_heartbeat=now,
    )

    # Append journal entry with summary
    if data.summary:
        from shoal.core.journal import append_entry
        await asyncio.to_thread(
            append_entry,
            session.id,
            f"[heartbeat] {data.summary}",
            "agent-hook",
        )

    return {
        "ok": True,
        "session": session_ref,
        "status": data.status.value,
        "status_source": "hook",
    }
```

**Step 3: Write test for heartbeat endpoint**

Create `tests/test_heartbeat.py`:

```python
import pytest
from httpx import AsyncClient
from shoal.api.server import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

async def test_heartbeat_updates_status(client):
    # Create a session first, then heartbeat it
    # ... (use existing test helpers)
    resp = await client.post(
        "/sessions/test-session/heartbeat",
        json={"status": "waiting", "summary": "Task completed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_source"] == "hook"
```

**Step 4: Run tests**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: add heartbeat REST endpoint for agent push status"
```

---

### Task 3: Add `heartbeat` MCP tool to the Shoal MCP server

**Objective:** Expose heartbeat as an MCP tool so agents connected via MCP can call it directly.

**Files:**
- Modify: `src/shoal/services/mcp_shoal_server.py`

**Step 1: Add `heartbeat` tool**

In `src/shoal/services/mcp_shoal_server.py`, add after the existing tools:

```python
@mcp.tool(
    name="heartbeat",
    description=(
        "Push session status to Shoal. Agents call this at end-of-turn "
        "or after tool use to notify Shoal of their current state "
        "without waiting for tmux polling. This makes status detection "
        "instant and reliable."
    ),
)
async def heartbeat_tool(
    session: str,
    status: str,
    summary: str = "",
    turn_number: int | None = None,
    tool_name: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Push agent status to Shoal (replaces tmux polling for instrumented agents)."""
    from shoal.models.heartbeat import HeartbeatRequest
    from shoal.models.state import SessionStatus, StatusSource

    try:
        parsed_status = SessionStatus(status)
    except ValueError:
        raise ToolError(f"Invalid status '{status}'. Valid: {[s.value for s in SessionStatus]}")

    req = HeartbeatRequest(
        status=parsed_status,
        summary=summary,
        turn_number=turn_number,
        tool_name=tool_name,
        metadata=metadata or {},
    )

    # Find session
    from shoal.core.state import find_by_name, get_session
    s = await find_by_name(session) or await get_session(session)
    if not s:
        raise ToolError(f"Session not found: {session}")

    from datetime import UTC, datetime
    now = datetime.now(UTC)

    from shoal.core.state import update_session
    updated = await update_session(
        s.id,
        status=parsed_status,
        status_source=StatusSource.hook,
        last_heartbeat=now,
    )

    if summary:
        from shoal.core.journal import append_entry
        import asyncio
        await asyncio.to_thread(
            append_entry,
            s.id,
            f"[heartbeat] {summary}",
            "agent-hook",
        )

    return {
        "ok": True,
        "session": session,
        "status": parsed_status.value,
        "status_source": "hook",
    }
```

**Step 2: Run tests**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: add heartbeat MCP tool for agent push status"
```

---

### Task 4: Update Watcher to skip hook-instrumented sessions

**Objective:** The Watcher should skip sessions that have recently received a heartbeat, falling back to tmux scraping only when heartbeats stop.

**Files:**
- Modify: `src/shoal/services/watcher.py`

**Step 1: Add heartbeat staleness check to `_poll_cycle`**

In `src/shoal/services/watcher.py`, inside `_poll_cycle`, after fetching sessions and before observing each one:

```python
from shoal.models.state import StatusSource

# In the loop over sessions:
HEARTBEAT_STALE_SECONDS = 60.0  # Consider hook-instrumented sessions stale after 60s

for session in sessions:
    if session.status.value == "stopped":
        continue

    # Skip polling if session has a recent heartbeat
    if session.status_source == StatusSource.hook and session.last_heartbeat:
        elapsed = (datetime.now(UTC) - session.last_heartbeat).total_seconds()
        if elapsed < HEARTBEAT_STALE_SECONDS:
            logger.debug(
                "Skipping %s: hook heartbeat %.0fs ago",
                session.name, elapsed,
            )
            continue
        else:
            logger.warning(
                "Hook heartbeat stale for %s (%.0fs), falling back to watcher",
                session.name, elapsed,
            )
            # Fall back to watcher mode
            await update_session(session.id, status_source=StatusSource.watcher)
```

**Step 2: Add `HEARTBEAT_STALE_SECONDS` to config**

In `src/shoal/models/config/general.py`, add:

```python
heartbeat_stale_seconds: float = 60.0
```

And load it in the Watcher constructor.

**Step 3: Write test for Watcher skip logic**

```python
import pytest
from datetime import UTC, datetime, timedelta
from shoal.models.state import SessionState, SessionStatus, StatusSource, TmuxRuntimeState

def test_watcher_skips_hook_instrumented_session():
    session = SessionState(
        id="test",
        name="test",
        tool="pisces",
        path="/tmp",
        runtime=TmuxRuntimeState(session_name="shoal-test"),
        status=SessionStatus.waiting,
        status_source=StatusSource.hook,
        last_heartbeat=datetime.now(UTC),
    )
    # ... assert Watcher skips this session
```

**Step 4: Run tests**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: Watcher skips sessions with recent heartbeats, falls back on stale"
```

---

### Task 5: Add `shoal heartbeat` CLI command

**Objective:** Provide a CLI command so agents can push status without needing MCP or HTTP.

**Files:**
- Modify: `src/shoal/cli/session.py` (or create new `heartbeat.py`)

**Step 1: Add heartbeat CLI command**

Create `src/shoal/cli/heartbeat.py`:

```python
"""CLI command for pushing agent heartbeat to Shoal."""

from __future__ import annotations

import asyncio
import click
from shoal.models.state import SessionStatus


@click.command("heartbeat")
@click.argument("session")
@click.argument("status", type=click.Choice([s.value for s in SessionStatus]))
@click.option("--summary", default="", help="One-line description of current state")
@click.option("--turn-number", type=int, default=None, help="Turn counter (Pisces)")
@click.option("--tool-name", default=None, help="Last tool called (PostToolUse)")
def heartbeat_cli(session: str, status: str, summary: str, turn_number: int | None, tool_name: str | None) -> None:
    """Push a status heartbeat for a session."""
    from shoal.core.state import find_by_name, get_session, update_session
    from shoal.models.state import StatusSource
    from datetime import UTC, datetime

    s = asyncio.run(find_by_name(session)) or asyncio.run(get_session(session))
    if not s:
        click.echo(f"Session not found: {session}", err=True)
        raise SystemExit(1)

    parsed = SessionStatus(status)
    now = datetime.now(UTC)

    updated = asyncio.run(update_session(
        s.id,
        status=parsed,
        status_source=StatusSource.hook,
        last_heartbeat=now,
    ))

    if summary:
        from shoal.core.journal import append_entry
        append_entry(s.id, f"[heartbeat] {summary}", "agent-hook")

    click.echo(f"✓ {s.name}: {parsed.value} (source: hook)")
```

Register it in the CLI group.

**Step 2: Run tests**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: add shoal heartbeat CLI command"
```

---

### Task 6: Pisces `turn_end` hook — push heartbeat to Shoal

**Objective:** Create a Pisces hook that pushes status to Shoal at the end of every turn.

**Files:**
- Create: `src/extensibility/hooks/shoal_heartbeat.ts` (in Pisces repo)

**Step 1: Create the hook module**

```typescript
// src/extensibility/hooks/shoal_heartbeat.ts
import { HookContext, HookDefinition } from "./types";

const SHOAL_PORT = parseInt(process.env.SHOAL_PORT || "8484", 10);
const SHOAL_SESSION = process.env.SHOAL_SESSION || "";

async function sendHeartbeat(status: string, summary: string, turnNumber?: number) {
  if (!SHOAL_SESSION) return; // Not in a Shoal session

  try {
    await fetch(`http://localhost:${SHOAL_PORT}/sessions/${SHOAL_SESSION}/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        summary: summary.slice(0, 200), // Truncate long summaries
        turn_number: turnNumber,
      }),
    });
  } catch {
    // Non-critical: heartbeat failure should not disrupt the agent
  }
}

export const turnEndHook: HookDefinition = {
  event: "turn_end",
  handler: async (ctx: HookContext) => {
    await sendHeartbeat("waiting", ctx.summary || "Turn complete", ctx.turnNumber);
  },
};

export const agentEndHook: HookDefinition = {
  event: "agent_end",
  handler: async (ctx: HookContext) => {
    await sendHeartbeat("stopped", "Agent finished");
  },
};
```

**Step 2: Register the hook in Pisces settings**

In `.pisces/settings.json` or equivalent:

```json
{
  "hooks": {
    "turn_end": ["shoal_heartbeat"],
    "agent_end": ["shoal_heartbeat"]
  }
}
```

**Step 3: Test manually**

```bash
# Start a Shoal session with Pisces
shoal create --tool pisces --name test-heartbeat

# Verify heartbeats arrive
shoal watch test-heartbeat
# Should show status_source: "hook" within 1 turn
```

**Step 4: Commit (in Pisces repo)**

```bash
git add -A && git commit -m "feat: add Shoal heartbeat hook for turn_end and agent_end"
```

---

### Task 7: Claude Code `PostToolUse` hook — push heartbeat to Shoal

**Objective:** Configure Claude Code to push heartbeats after tool calls via shell hook.

**Files:**
- Modify: `~/.claude/settings.json` or project `.claude/settings.json`

**Step 1: Create the heartbeat script**

Create `~/.shoal/hooks/claude_heartbeat.sh`:

```bash
#!/usr/bin/env bash
# Claude Code PostToolUse hook for Shoal heartbeat
# Called after every tool use with env vars set by Claude Code.

SESSION="${SHOAL_SESSION:-}"
TOOL="${CLAUDE_TOOL_NAME:-unknown}"

# If not in a Shoal session, skip
[ -z "$SESSION" ] && exit 0

# Push heartbeat via Shoal API
curl -s -X POST "http://localhost:${SHOAL_PORT:-8484}/sessions/${SESSION}/heartbeat" \
  -H "Content-Type: application/json" \
  -d "{\"status\": \"running\", \"summary\": \"Tool: ${TOOL}\", \"tool_name\": \"${TOOL}\"}" \
  > /dev/null 2>&1 &

# Also mark waiting after a short delay (end of turn approximation)
(sleep 2 && curl -s -X POST "http://localhost:${SHOAL_PORT:-8484}/sessions/${SESSION}/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{"status": "waiting", "summary": "Turn complete"}' \
  > /dev/null 2>&1) &
```

```bash
chmod +x ~/.shoal/hooks/claude_heartbeat.sh
```

**Step 2: Register in Claude Code settings**

In `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "command": "~/.shoal/hooks/claude_heartbeat.sh"
      }
    ]
  }
}
```

**Step 3: Test manually**

```bash
# Start a Shoal session with Claude Code
shoal create --tool claude --name test-claude-hb

# Use Claude Code, verify heartbeats arrive
shoal session-info test-claude-hb
# Should show status_source: "hook"
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: add Claude Code heartbeat hook for Shoal"
```

---

### Task 8: Update Dashboard to display `status_source`

**Objective:** Show users whether a session's status comes from a hook or the watcher.

**Files:**
- Modify: `src/shoal/dashboard/` (relevant UI components)

**Step 1: Add `status_source` indicator to session cards**

In the session card/list component, add a small badge:
- 🟢 `hook` → "Live" (agent is pushing heartbeats)
- 🟡 `watcher` → "Polled" (tmux-based observation)

**Step 2: Add heartbeat timestamp to session detail view**

Show `last_heartbeat` time in the session detail panel, with a relative time indicator ("12s ago").

**Step 3: Run dashboard dev server and verify visually**

```bash
cd ~/pantheon/tools/shoal-cli && uv run shoal dashboard
# Open http://localhost:8484 and verify indicators
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: dashboard shows status_source (hook vs watcher)"
```

---

### Task 9: Integration test — full heartbeat flow

**Objective:** End-to-end test verifying the complete heartbeat flow from agent hook to Shoal state update to Watcher skip.

**Files:**
- Create: `tests/test_heartbeat_integration.py`

**Step 1: Write integration test**

```python
"""Integration test: agent heartbeat → Shoal state → Watcher behavior."""

import pytest
from datetime import UTC, datetime, timedelta
from shoal.models.state import SessionState, SessionStatus, StatusSource, TmuxRuntimeState
from shoal.core.state import update_session


@pytest.mark.asyncio
async def test_heartbeat_updates_status_and_source():
    """POST /sessions/{name}/heartbeat should update status and set source=hook."""
    # ... create session, POST heartbeat, verify state


@pytest.mark.asyncio
async def test_watcher_skips_recent_heartbeat():
    """Watcher should skip polling sessions with recent heartbeats."""
    # ... create session, set heartbeat, verify watcher skips


@pytest.mark.asyncio
async def test_watcher_falls_back_on_stale_heartbeat():
    """Watcher should fall back to tmux polling when heartbeat is stale (>60s)."""
    # ... create session, set stale heartbeat, verify watcher polls


@pytest.mark.asyncio
async def test_mcp_heartbeat_tool():
    """MCP heartbeat tool should update session status."""
    # ... call heartbeat_tool, verify state
```

**Step 2: Run full test suite**

```bash
cd ~/pantheon/tools/shoal-cli && uv run pytest tests/ -x -q
```

**Step 3: Commit**

```bash
git add -A && git commit -m "test: add integration tests for heartbeat flow"
```

---

### Task 10: Documentation — update README and add migration guide

**Objective:** Document the new heartbeat feature and migration path.

**Files:**
- Modify: `README.md`
- Create: `docs/heartbeat-migration.md`

**Step 1: Add heartbeat section to README**

Add a section describing:
- What heartbeat is
- How to enable it for Pisces and Claude Code
- Configuration options (`heartbeat_stale_seconds`)
- Fallback behavior

**Step 2: Create migration guide**

`docs/heartbeat-migration.md`:

```markdown
# Migrating from tmux-only to Heartbeat Observation

## Overview

Shoal now supports **push-based status observation** via agent hooks. When
enabled, agents notify Shoal of their state in real-time instead of relying
on tmux pane scraping.

## Enabling

### Pisces
Add the `shoal_heartbeat` hook to your `.pisces/settings.json`:

\`\`\`json
{
  "hooks": { "turn_end": ["shoal_heartbeat"] }
}
\`\`\`

Set `SHOAL_SESSION` and `SHOAL_PORT` environment variables in your session
template.

### Claude Code
Add to `.claude/settings.json`:

\`\`\`json
{
  "hooks": {
    "PostToolUse": [{ "matcher": "", "command": "~/.shoal/hooks/claude_heartbeat.sh" }]
  }
}
\`\`\`

## Fallback

If an agent stops sending heartbeats for >60s (configurable), Shoal
automatically falls back to tmux-based observation. No manual intervention
required.
```

**Step 3: Commit**

```bash
git add -A && git commit -m "docs: add heartbeat feature documentation and migration guide"
```

---

## Summary

| Task | Scope | Effort |
|------|-------|--------|
| 1. StatusSource model | Core | 30min |
| 2. REST heartbeat endpoint | API | 45min |
| 3. MCP heartbeat tool | MCP | 30min |
| 4. Watcher skip logic | Watcher | 45min |
| 5. CLI heartbeat command | CLI | 20min |
| 6. Pisces hook | Pisces | 30min |
| 7. Claude Code hook | Config | 15min |
| 8. Dashboard indicators | UI | 30min |
| 9. Integration tests | Tests | 45min |
| 10. Documentation | Docs | 20min |

**Total estimated effort:** ~5.5 hours

**Dependency chain:** Tasks 1→2→3→4 (sequential, core), Tasks 5-8 (can parallel after Task 2), Tasks 9-10 (after all others).