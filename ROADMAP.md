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

- [x] Ship `shoal-remote` fish function wrapping SSH
- [x] Document remote usage patterns

### Phase 2 — `shoal remote` subcommand group

- [x] `shoal remote connect/disconnect` — SSH tunnel management
- [x] `shoal remote status/ls` — HTTP GET via tunnel, Rich-formatted
- [x] `shoal remote send/attach` — interact with remote sessions
- [x] Remote host config in `~/.config/shoal/config.toml`

### Phase 3 — Status bar integration (deferred)

- [ ] Fish status bar polls remote WebSocket for session status

## Future Considerations

- **FastMCP Transport Migration**: Adopt HTTP transport for `shoal-orchestrator` (spike approved); keep byte bridge for third-party stdio servers. Fix proxy Python 3.13 compatibility.
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()`.
- **Project-Local Templates**: `.shoal/templates/` search path in git root.
- **Oh-My-Pi (omp) Integration**: Add `omp.toml` tool definition and `omp-dev` session template mirroring existing pi support. Key opportunities: omp has native MCP (`omp plugin` system) enabling direct socket sharing with Shoal's MCP pool; detection patterns need tuning for omp's extended TUI (subagent/LSP status indicators beyond pi's base patterns); universal config discovery (reads `.claude/`, `.codex/`, `.gemini/` alongside `.omp/`) enables cross-agent workflow sharing.
- Expose hooks for configuration and runtime scripting
- **Structured Session Journals**: Per-session `.shoal/journal.md` written via MCP, enabling robo supervisors to query child agent progress at varying granularity. Inspired by [GCC](https://arxiv.org/abs/2508.00031) (git-like context versioning for agents) — Shoal would provide storage/retrieval infrastructure without managing agent internals.
- Documentation catchup!! A lot will have changed by v0.16.0

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-02-23 — v0.16.0 Remote Sessions (Phase 2)

**What we did:**

- Created `src/shoal/core/remote.py` — SSH tunnel lifecycle (start/stop/list) + HTTP client helpers (get/post/delete via `urllib.request`, no new deps)
- Created `src/shoal/cli/remote.py` — 7 CLI commands: `ls`, `connect`, `disconnect`, `status`, `sessions`, `send`, `attach`
- Added `RemoteHostConfig` model to `models/config.py` with `remote: dict[str, RemoteHostConfig]` on `ShoalConfig`
- Added fish shell completions for remote subcommands and host name completions
- 45 new tests (25 core + 20 CLI), 666 total passing, ruff/mypy --strict/fish-check all clean
- v0.16.0 all phases complete (Phase 1 + Phase 2; Phase 3 deferred)

**What to do next:**

- Commit remaining unstaged v0.16.0 changes (CHANGELOG, README, ROADMAP, remote docs, fish installer, remote.fish)
- Documentation catchup

### Session: 2026-02-23 — XDG compliance + status bar cleanup

**What we did:**

- XDG Base Directory compliance: `config_dir()` reads `XDG_CONFIG_HOME`, `state_dir()` reads `XDG_DATA_HOME`, `runtime_dir()` reads `XDG_STATE_HOME`, `build_nvim_socket_path()` reads `XDG_RUNTIME_DIR` — all fall back to current defaults
- Fish completions (`__shoal_tools`, `__shoal_templates`, `__shoal_remote_hosts`) use `$XDG_CONFIG_HOME` instead of hardcoded `~/.config`
- Removed dead `state_dir` field from `GeneralConfig` model
- Simplified status bar: `status_bar.py` returns dict of counts, `main()` prints JSON; removed `tmux_fg`/`tmux_status_segment` from theme
- 8 new XDG tests, 676 total passing, ruff/mypy --strict clean
- Committed as `3bbc1b2`

**What to do next:**

- Commit remaining unstaged v0.16.0 changes (CHANGELOG, README, ROADMAP, remote docs, fish installer, remote.fish)
- Fix bandit B310 findings in `remote.py` (queued in backlog)
- Documentation catchup
