---
description: Reference for shoal session lifecycle, pane identity, status detection guarantees, and cleanup protocol.
---

## Pane identity contract

Every shoal-managed tmux pane MUST have its title set to `shoal:<session_id>`. Shoal sets this at session creation time. Never rename panes in running sessions — status detection depends on this title to locate the correct pane.

If the session uses Neovim, the socket path follows this pattern:

```
/tmp/nvim-<session_id>-<window_id>.sock
```

Do not change this path or create sockets at alternate locations; tooling that attaches to Neovim state relies on it.

---

## Status detection — what it guarantees and what it does not

Status is heuristic, not event-driven. Shoal polls pane output every 5 seconds and pattern-matches against regexes to infer state. This is not a real event stream.

Consequences:
- `idle` can false-positive if the agent prints a prompt-like string mid-task (e.g. during a clarification question inside a long run). Trust `idle` only after `running` patterns have been absent for two consecutive poll cycles (~10 seconds).
- `running` → `idle` transitions may lag by up to one poll cycle.
- `waiting` requires the session to emit a recognizable approval prompt. If the agent implements a non-standard prompt, it will be misclassified as `running`.

Do not build hard synchronization logic on top of status polling. Use it for display and loose orchestration only.

---

## Status state machine

```
idle → running → waiting → idle
                          → error → idle
                                  → stopped
       running → idle
       running → error → stopped
```

| State | Meaning |
|---|---|
| `idle` | Session is ready for input |
| `running` | Agent is actively processing |
| `waiting` | Agent is waiting for user approval |
| `error` | Agent encountered an unrecoverable error |
| `stopped` | Session has been killed; pane no longer exists |

---

## Status provider selection

The provider is set in the session template or tool definition. Pick the most specific one available:

| Provider | Use for | Notes |
|---|---|---|
| `pi` | `pi` / OMP sessions | Event-based; most accurate; use by default for pi sessions |
| `opencode_compat` | OpenCode sessions | Compatibility regex tuned for OpenCode's output patterns |
| `regex` | `claude`, `codex`, generic | Generic pattern matching; good enough for most tools |

---

## Worktree cleanup protocol

Run these in order. Skipping steps leaves dangling state.

```bash
shoal kill <name>       # terminate the session and its pane
shoal prune             # remove stopped sessions from the registry
shoal wt prune          # remove stale git worktrees
```

If `auto_commit = true` is set in `config.toml`, shoal automatically creates a conventional commit on the working branch before executing `kill`. The commit message is derived from the session name.

---

## Fork semantics

`shoal fork <src> <dst>` creates a new worktree from the current branch HEAD of the source session. The source session continues running — fork does not pause or snapshot it.

The forked session:
- Inherits all env vars from the source session's template
- Does NOT inherit MCP state (each session gets a fresh MCP process pool)
- Starts in `idle` state; the agent has not launched yet

---

## MCP pool

Each new connection from shoal to an MCP server spawns a fresh MCP process. MCP processes are not shared between agents or sessions.

Memory is NOT shared between agents across connections. If cross-agent state sharing is required, it must be persisted externally — files, SQLite, or a shared service. Do not rely on in-process MCP state surviving a session restart or fork.
