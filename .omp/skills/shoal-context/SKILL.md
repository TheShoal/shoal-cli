---
name: shoal-context
description: Current shoal-cli project state — active milestone, live docs locations, session state. Use when you need the current development focus, roadmap next steps, or where to find live state files.
---

# Shoal CLI — Current Project State

**Version**: 0.18.0 (in development)
**Active milestone**: v0.18.0 — Lifecycle Hooks, Observability & Robo Supervisor

## Active Milestone: v0.18.0

Priority: event-driven architecture, agent observability, autonomous supervision (robo).
See `ROADMAP.md` for the full phase breakdown and task checklist.

## Live Docs

| Doc | Purpose |
|-----|---------|
| `ROADMAP.md` | Milestone phases, task checklist, current focus |
| `CHANGELOG.md` | Completed releases (v0.4.0–v0.17.0) |
| `SHOAL.md` | Ecosystem snapshot: tool strategy, integration points, recent completions |
| `ARCHITECTURE.md` | Design decisions, data flow, component relationships |
| `CLAUDE.md` | Quick reference: commands, module layout, style, gotchas |

## Recent Completions (v0.17.0)

- `shoal diag` — diagnostics command (DB, watcher, tmux, MCP sockets)
- `shoal demo tutorial` — interactive 7-step guided walkthrough
- Context propagation via `ContextVar` (session/request ID threading)
- Logging infrastructure — named loggers, structured JSON output
- `shoal config show` + `shoal mcp registry` — introspection commands

## Active Sessions

Check live session state with:
```bash
shoal ls        # all sessions
shoal status    # quick summary
```
