# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

> **Release history**: See [CHANGELOG.md](CHANGELOG.md) for completed releases (v0.4.0–v0.16.0).

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

## Next: Local Templates, Journals, HTTP Transport

### Project-Local Templates
- [x] `.shoal/templates/` search path in git root (local shadows global)
- [x] `template ls` shows SOURCE column (local/global)
- [x] Project-local mixins support

### Structured Session Journals
- [x] `core/journal.py` — append-only markdown per session
- [x] MCP tools: `append_journal`, `read_journal`
- [x] CLI: `shoal journal <session>` view/append
- [x] Journal archive on session kill

### FastMCP HTTP Transport Default
- [x] HTTP default for `shoal-orchestrator` in MCP pool registry
- [x] `mcp doctor` HTTP probe via FastMCP Client
- [x] Auto-configure HTTP URL for tool integration

## Future Considerations

- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()`.
- **Oh-My-Pi (omp) Integration**: Add `omp.toml` tool definition and `omp-dev` session template mirroring existing pi support. Key opportunities: omp has native MCP (`omp plugin` system) enabling direct socket sharing with Shoal's MCP pool; detection patterns need tuning for omp's extended TUI (subagent/LSP status indicators beyond pi's base patterns); universal config discovery (reads `.claude/`, `.codex/`, `.gemini/` alongside `.omp/`) enables cross-agent workflow sharing.
- Expose hooks for configuration and runtime scripting
- Remote status bar: Fish status bar polls remote WebSocket for session status

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-02-23 — Handoff resync + journal archive

**What we did:**

- Resynced handoff (prior entries were stale — test count was 618–728, actual is 820+)
- Journal archive on session kill: `archive_journal()` in `core/journal.py` moves to `journals/archive/`
- Wired into `kill_session_lifecycle()` (best-effort, between DB delete and MCP cleanup)
- Wired into `_prune_impl()` for stopped session cleanup
- Updated CLI kill output, MCP `kill_session` tool return with `journal_archived` key
- 7 new tests (4 journal, 3 lifecycle), 820 total passing, lint/mypy clean

**What to do next:**

- Version bump (v0.17.0?)
- Server Composition Gateway investigation (FastMCP `mount()`)
- Documentation for new features (journal archive, local templates, HTTP transport)
- Consider `shoal journal --archived <session>` CLI for reading archived journals
