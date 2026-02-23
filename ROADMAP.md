# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

> **Release history**: See [CHANGELOG.md](CHANGELOG.md) for completed releases (v0.4.0–v0.15.0).

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

- [ ] Ship `shoal-remote` fish function wrapping SSH
- [ ] Document remote usage patterns

### Phase 2 — `shoal remote` subcommand group

- [ ] `shoal remote connect/disconnect` — SSH tunnel management
- [ ] `shoal remote status/ls` — HTTP GET via tunnel, Rich-formatted
- [ ] `shoal remote send/attach` — interact with remote sessions
- [ ] Remote host config in `~/.config/shoal/config.toml`

### Phase 3 — Status bar integration (optional)

- [ ] Fish status bar polls remote WebSocket for session status

## Future Considerations

- **FastMCP Transport Migration**: Adopt HTTP transport for `shoal-orchestrator` (spike approved); keep byte bridge for third-party stdio servers. Fix proxy Python 3.13 compatibility.
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()`.
- **Project-Local Templates**: `.shoal/templates/` search path in git root.
- **Oh-My-Pi (omp) Integration**: Add `omp.toml` tool definition and `omp-dev` session template mirroring existing pi support. Key opportunities: omp has native MCP (`omp plugin` system) enabling direct socket sharing with Shoal's MCP pool; detection patterns need tuning for omp's extended TUI (subagent/LSP status indicators beyond pi's base patterns); universal config discovery (reads `.claude/`, `.codex/`, `.gemini/` alongside `.omp/`) enables cross-agent workflow sharing.
- Expose hooks for configuration and runtime scripting
- Documentation catchup!! A lot will have changed by v0.16.0

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-02-22 — v0.15.0 FastMCP Integration (Phase 1)

**What we did:**

- Added `fastmcp>=3.0.0` as optional dependency (`shoal[mcp]`) and to dev deps
- Created `src/shoal/services/mcp_shoal_server.py` — FastMCP server with 6 tools:
    - `list_sessions`: list all sessions with status (readOnly)
    - `session_status`: aggregate status counts (readOnly)
    - `session_info`: full session details by name or ID (readOnly)
    - `send_keys`: send keystrokes to a session's tmux pane (destructive)
    - `create_session`: create session with template/worktree/MCP support (destructive)
    - `kill_session`: kill session with dirty-worktree protection (destructive)
- Registered `shoal-mcp-server` console script and `shoal-orchestrator` in default MCP pool
- Added `shoal-orchestrator` mixin and `robo-orchestrator` template for robo workflows
- 26 new tests in `test_mcp_shoal_server.py`, 618 total tests passing, ruff/mypy clean
- Bumped version to 0.15.0

**What to do next:**

- v0.15.0 Phase 2: Replace manual JSON-RPC probe in `mcp doctor` with FastMCP Client
- v0.15.0 Phase 3: Transport evaluation spike (HTTP vs UDS performance)
- Consider extracting shared `create_session` resolution logic from API server + MCP server into lifecycle helper
- v0.16.0: Remote Sessions (SSH tunnel + HTTP client)

### Session: 2026-02-23 — v0.15.0 Phase 2: Protocol-Aware Health Checks

**What we did:**

- Replaced manual JSON-RPC probe in `mcp doctor` with FastMCP Client (`_probe_server()` in `src/shoal/cli/mcp.py`)
- New `_ProbeResult` class holds structured probe results (connection status, server name/version, tool count, latency, error diagnostics)
- Probe uses `StdioTransport` → `shoal-mcp-proxy` → pool socket, testing the full client path
- Doctor table now shows PROTOCOL, TOOLS, VERSION, LATENCY columns (replaces old SOCKET + JSON-RPC)
- Graceful fallback when `fastmcp` not installed (shows "skip", suggests `pip install shoal[mcp]`)
- Replaced 3 old doctor tests with 6 focused tests (dead PID, probe success, timeout, error diagnostics, no-fastmcp)
- Fixed 4 pre-existing ruff lint warnings (test_mcp_pool, test_notify, test_popup)
- 618 tests passing, ruff/mypy/bandit all clean

**What to do next:**

- v0.15.0 Phase 3: Transport evaluation spike (HTTP vs UDS performance for MCP traffic)
- Consider extracting shared `create_session` resolution logic from API server + MCP server into lifecycle helper
- v0.16.0: Remote Sessions (SSH tunnel + HTTP client)

### Session: 2026-02-23 — v0.15.0 Phase 3: Transport Evaluation Spike

**What we did:**

- Investigated FastMCP UDS transport: **not available** in FastMCP 3.0.2 (only stdio, HTTP, SSE, streamable-http)
- Added `--http [PORT]` flag to `shoal-mcp-server` for streamable-http transport mode
- Created `benchmarks/transport_spike.py` — self-contained benchmark comparing stdio vs HTTP transports
- Benchmarked on Python 3.13.11: stdio ~21ms/call, HTTP ~57ms/call, HTTP startup ~65ms vs stdio ~2-9s
- Discovered Python 3.13 compatibility bug in `mcp_proxy.py` (`BaseProtocol` lacks `_drain_helper`)
- Wrote `docs/transport-spike.md` with full findings and go/no-go recommendation
- **Decision: Go** — adopt HTTP for `shoal-orchestrator` (enables v0.16.0 remote sessions), keep byte bridge for third-party stdio servers
- v0.15.0 all 3 phases complete

**What to do next:**

- Fix proxy Python 3.13 bug: replace `BaseProtocol` with `StreamReaderProtocol` in `mcp_proxy.py`
- Production HTTP server: add `shoal mcp start shoal-orchestrator --http` CLI support
- Consider extracting shared `create_session` resolution logic from API server + MCP server
- v0.16.0: Remote Sessions (SSH tunnel + HTTP transport for `shoal-orchestrator`)

### Session: 2026-02-23 — Pre-v0.16.0 Cleanup

**What we did:**

- Fixed Python 3.13 proxy bug: replaced `BaseProtocol` with `StreamReaderProtocol` in `mcp_proxy.py` (lines 48-62) — `StreamWriter` needs `_drain_helper` from `FlowControlMixin` which `BaseProtocol` lacks on 3.13+
- Evaluated `create_session` extraction (API + MCP server): deferred — only 2 call sites with different error types (HTTPException vs ToolError), moderate duplication doesn't justify the indirection
- Trimmed roadmap handoff section from 8 entries to 4 (older entries preserved in CHANGELOG.md)
- Updated `/shoal-handoff` skill with cleanup policy: "prune to last 2-3 entries when writing new handoffs"
- 618 tests passing, ruff/mypy clean

**What to do next:**

- Production HTTP server: add `shoal mcp start shoal-orchestrator --http` CLI support
- v0.16.0: Remote Sessions (SSH tunnel + HTTP transport for `shoal-orchestrator`)
