# Architecture Guide

The full architecture guide with design rationale, data flow diagrams, and component relationships is in [ARCHITECTURE.md](https://github.com/TheShoal/shoal-cli/blob/main/ARCHITECTURE.md).

## Key design decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite + WAL** | Zero setup, ACID guarantees, single-machine concurrency via WAL mode |
| **`services/lifecycle.py` as single orchestrator** | CLI and API both delegate to it — no duplicate logic |
| **Git worktrees** (not branches) for isolation | Separate working directories, zero file conflicts between agents |
| **MCP pool via Unix sockets** | One listener per MCP type, fresh process per client connection, no socat |
| **Runtime provider seam** | Transport (tmux) decoupled from status parsing — future backends plug in without surface changes |
| **Async throughout** | All I/O is `async/await`; blocking subprocess calls use `asyncio.to_thread()` |
| **Robo supervisor as an agent** | Supervisor uses the same MCP/CLI interface as human operators — no special backdoors |

## Module layout

```
src/shoal/
├── api/          # FastAPI server (REST + WebSocket)
├── cli/          # Typer CLI
│   └── demo/     # Demo subpackage
├── core/         # Business logic (config, db, tmux/git, journal, context)
├── models/       # Pydantic models (config submodules, session state, API schemas)
├── services/     # Lifecycle, MCP pool/proxy/server, status bar, robo, proactive
├── integrations/ # Fish shell templates and tool-specific configs
└── dashboard/    # Rich-based terminal dashboard
```

## Invariants

These must be maintained across all changes:

1. **Single lifecycle service**: `services/lifecycle.py` owns create/fork/kill/reconcile. Both CLI and API call it.
2. **WAL concurrency**: all DB writes go through `aiosqlite` with `asyncio.Lock`.
3. **Pane identity**: tmux pane titles are `shoal:<session_id>` — do not change this scheme.
4. **Async I/O**: no blocking calls in async contexts; use `asyncio.to_thread()`.
5. **`extra="forbid"` on config models**: prevents silent config key typos.

See [ARCHITECTURE.md](https://github.com/TheShoal/shoal-cli/blob/main/ARCHITECTURE.md) for the full rationale behind each decision.
