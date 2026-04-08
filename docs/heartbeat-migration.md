# Agent Heartbeat — Push Observation

## Overview

Shoal now supports **push-based status observation** via agent heartbeat hooks.
Instead of relying solely on the tmux-based Watcher (which polls pane output
every few seconds), agents can actively report their status at end-of-turn.

This gives higher fidelity status tracking:
- **Watcher** (🟡 Polled): tmux-based, ~5s delay, infers status from pane text
- **Hook** (🟢 Live): agent-pushed, near-instant, explicit status from the agent

## Architecture

```
┌──────────┐    heartbeat     ┌───────────────┐
│  Agent   │ ──────────────► │  Shoal Server  │
│ (Pisces) │  REST / MCP/CLI │  POST /heartbeat│
└──────────┘                 └───────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │   Watcher     │
                              │  (fallback)   │
                              └──────────────┘
```

- The Watcher **skips** sessions with a recent heartbeat (<60s)
- If the heartbeat goes stale (>60s), the Watcher **falls back** to polling
- Status source is tracked per-session via `status_source` field

## API

### REST Endpoint

```
POST /sessions/{session_ref}/heartbeat
Content-Type: application/json

{
  "status": "waiting",       // Required: running|waiting|error|stopped
  "summary": "Turn complete", // Optional: one-line description
  "turn_number": 5,           // Optional: turn counter
  "tool_name": "read_file",   // Optional: last tool called
  "tool_result": "ok",        // Optional: tool result
  "metadata": {}              // Optional: arbitrary metadata
}
```

Response:
```json
{
  "ok": true,
  "session": "my-session",
  "status": "waiting",
  "status_source": "hook"
}
```

### MCP Tool

```python
# Via Shoal MCP server
shoal_heartbeat(
    session="my-session",
    status="waiting",
    summary="Turn complete",
    turn_number=5,
)
```

### CLI Command

```bash
shoal heartbeat my-session waiting --summary "Turn complete"
shoal heartbeat my-session running --tool-name "read_file"
```

## Integration Guides

### Pisces (turn_end hook)

1. Copy `src/shoal/integrations/hooks/shoal_heartbeat.ts` to your Pisces
   hooks directory
2. Set `SHOAL_SESSION` and `SHOAL_PORT` environment variables
3. Configure `turn_end` and `agent_end` hooks in Pisces config

```typescript
// Pisces config
hooks: {
  turn_end: "./shoal_heartbeat.ts#turnEnd",
  agent_end: "./shoal_heartbeat.ts#agentEnd",
}
```

### Claude Code (PostToolUse hook)

1. Copy `src/shoal/integrations/hooks/claude_heartbeat.sh` somewhere
2. Make it executable: `chmod +x claude_heartbeat.sh`
3. Add to Claude Code settings:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "command": "/path/to/claude_heartbeat.sh",
        "env": {
          "SHOAL_SESSION": "$SHOAL_SESSION",
          "SHOAL_PORT": "$SHOAL_PORT"
        }
      }
    ]
  }
}
```

### Custom Agents

Any agent can push heartbeats via the REST API:

```bash
curl -X POST http://localhost:8484/sessions/my-session/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"status": "waiting", "summary": "Done thinking"}'
```

## Migration Guide

### For Existing Users

No breaking changes. The Watcher continues to work as before. Heartbeat is
opt-in — sessions without hooks remain Watcher-polled.

### Enabling Heartbeat

1. Update Shoal: `pip install --upgrade shoal`
2. Add hooks to your agent (see integration guides above)
3. Set `SHOAL_SESSION` env var when creating sessions
4. The dashboard will show 🟢 Live for hook-instrumented sessions

### Dashboard Changes

Session cards now show the status source:
- 🟢 **Live** — Agent is pushing heartbeats
- 🟡 **Polled** — Watcher is observing via tmux

## Configuration

Add to `config.toml` to customize staleness timeout:

```toml
[general]
heartbeat_stale_seconds = 60.0  # Default: 60s before Watcher fallback
```

## Data Model

### StatusSource Enum

| Value | Description |
|-------|-------------|
| `watcher` | Status inferred by tmux watcher |
| `hook` | Status explicitly pushed by agent |

### Session State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `status_source` | StatusSource | `watcher` | How status was determined |
| `last_heartbeat` | datetime? | None | Timestamp of last heartbeat |

### HeartbeatRequest Model

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | SessionStatus | Yes | Current agent status |
| `summary` | str | No | One-line state description |
| `turn_number` | int? | No | Turn counter |
| `tool_name` | str? | No | Last tool called |
| `tool_result` | str? | No | Tool result |
| `metadata` | dict | No | Arbitrary metadata |
