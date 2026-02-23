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
- [ ] Journal cleanup on session kill

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

### Session: 2026-02-23 — 5-Milestone implementation sprint

**What we did:**

- M1 Housekeeping: fixed flaky CliRunner test, committed unstaged docs, gitignored CODE_REVIEW artifacts
- M2 Documentation: updated TROUBLESHOOTING.md (remote, diagnostics, removed socat refs), updated FISH_INTEGRATION.md (XDG, diag), fixed stale socat ref in CLAUDE_CODE_SETUP.md
- M3 Project-local templates: `.shoal/templates/` search path, local shadows global, SOURCE column in `template ls`, local mixins, 13 tests
- M4 Structured session journals: `core/journal.py`, `cli/journal.py`, MCP tools `append_journal`/`read_journal`, 18 tests
- M5 HTTP transport default: `_DEFAULT_TRANSPORTS` registry, `get_transport()`, auto-detect HTTP in CLI, `mcp doctor` HTTP probe, HTTP config generation, 8 tests
- Updated ROADMAP.md with concrete milestone sections

**What to do next:**

- Wire journal cleanup into `kill_session_lifecycle()` (delete journal on kill)
- Consider formal version bump (v0.17.0?)
- Server Composition Gateway investigation
- Documentation for new features (journal, local templates, HTTP transport)

### Session: 2026-02-23 — Logging, observability, and tracing + cleanup

**What we did:**

- Implemented full 3-phase observability plan from code review (14 tasks, commit `e4fde55`)
- Phase 1: SSH credential redaction, CORS fix, loggers for 8 silent modules, watcher exponential backoff, named FileHandler
- Phase 2: `core/context.py` (ContextVar session_id/request_id), RequestIdMiddleware, ContextFilter wired into CLI/watcher/lifecycle, `shoal diag` command, deepened `/health` endpoint
- Phase 3: `core/logging_config.py` (JsonFormatter), `--log-level`/`--log-file`/`--json-logs` CLI flags, MCP pool + DB operation timing
- Fixed bandit B310 warnings in `remote.py` with `# nosec B310` comments (`f6bfc02`)
- Added session CLI coverage tests: attach, detach, rename, prune, popup (`e3617e3`)
- 29 files changed (6 new), 1368 insertions, 728+ tests, 81.91% coverage

**What to do next:**

- Commit remaining unstaged v0.16.0 changes (CHANGELOG, README, ROADMAP, remote docs, fish installer, remote.fish)
- Documentation catchup
- Consider adding observability milestone to ROADMAP if formalizing as a release

### Session: 2026-02-23 — XDG compliance + status bar cleanup

**What we did:**

- XDG Base Directory compliance: `config_dir()` reads `XDG_CONFIG_HOME`, `state_dir()` reads `XDG_DATA_HOME`, `runtime_dir()` reads `XDG_STATE_HOME`, `build_nvim_socket_path()` reads `XDG_RUNTIME_DIR` — all fall back to current defaults
- Fish completions use `$XDG_CONFIG_HOME` instead of hardcoded `~/.config`
- Simplified status bar: returns dict of counts, `main()` prints JSON
- 8 new XDG tests, 676 total passing, committed as `3bbc1b2`

**What to do next:**

- See latest handoff entry above
