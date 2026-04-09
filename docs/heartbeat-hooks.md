# Heartbeat Hooks

Heartbeat hooks push agent status to the Shoal API at the end of every turn and when the agent exits. Shoal uses these signals to switch sessions from the `watcher` (tmux scraping) source to the `hook` source — more accurate and lower latency.

Two hooks are provided: one for **omp** (TypeScript Extension) and one for **Claude Code** (shell hook).

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOAL_SESSION` | Yes | — | Shoal session name or ID. Hook is a no-op if unset. |
| `SHOAL_PORT` | No | `8080` | Port the Shoal HTTP API listens on. |

---

## omp Heartbeat Extension (`omp_heartbeat.ts`)

A TypeScript [omp Extension](https://github.com/can1357/oh-my-pi) that fires on `onTurnEnd` and `onAgentEnd`.

### Install

```bash
mkdir -p ~/.config/shoal/hooks
# Copy from the Shoal repo:
cp src/shoal/integrations/hooks/omp_heartbeat.ts ~/.config/shoal/hooks/
```

Register in `~/.omp/agent/config.yml`:

```yaml
extensions:
  - ~/.config/shoal/hooks/omp_heartbeat.ts
```

### What it pushes

| Event | Status pushed |
|---|---|
| `onTurnEnd` | `waiting` (+ optional summary, truncated to 200 chars) |
| `onAgentEnd` | `stopped` |

The extension also exports legacy named hooks (`turnEnd`, `agentEnd`) for backward compatibility with older omp hook-module APIs.

---

## Claude Code Heartbeat Hook (`claude_heartbeat.sh`)

A shell hook that fires via Claude Code's `PostToolUse` hook mechanism.

### Install

```bash
mkdir -p ~/.config/shoal/hooks
cp src/shoal/integrations/hooks/claude_heartbeat.sh ~/.config/shoal/hooks/
chmod +x ~/.config/shoal/hooks/claude_heartbeat.sh
```

Add to `~/.claude/settings.json` (see `claude_settings_snippet.json` in the same directory for the exact snippet):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{ "type": "command", "command": "~/.config/shoal/hooks/claude_heartbeat.sh" }]
      }
    ]
  }
}
```

---

## Two-source status model

Shoal tracks how a session's status was determined via `StatusSource`:

| Source | How | Staleness |
|---|---|---|
| `hook` | Agent pushed via heartbeat endpoint | Authoritative; 60 s stale window |
| `watcher` | Watcher scrapes tmux pane output | Fallback when hook is absent or stale |

When a hook is active, Shoal uses the pushed status directly. After `heartbeat_stale_seconds` (default 60) without a push, it falls back to the watcher. The status bar and dashboard show the source so you can see which sessions are hook-instrumented.

---

## Legacy: Pisces hook (`shoal_heartbeat.ts`)

The original hook for the Pisces fork of omp. Uses port **8484** instead of **8080**. Kept for backward compatibility — for new setups use `omp_heartbeat.ts`.
