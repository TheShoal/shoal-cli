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

### Session: 2026-02-23 — UAT demo bug fixes

**What we did:**

- Populated all 5 `STATUS_STYLES` nerd fields with Nerd Font glyphs (`theme.py`)
- Fixed demo branch detection, tour MCP skip handling, ghost session wording
- Added `--cleanup` flag to `mcp doctor`
- 2 commits (`6d07d29`, `bc9ea40`), 839 tests passing (19 new)

**What to do next:**

- Journal Obsidian frontmatter (see next session)

### Session: 2026-02-23 — Journal frontmatter + async fix

**What we did:**

- Added `JournalMetadata` dataclass + `build_journal_metadata()` factory in `core/journal.py`
- Obsidian-compatible YAML frontmatter on journal creation (title, aliases, tags, created)
- Frontmatter-aware parsing: `_strip_frontmatter()`, `read_frontmatter()`, updated `_parse_journal()`
- Fixed async-unsafe `archive_journal()` call in `_prune_impl()` (was blocking event loop, now `asyncio.to_thread`)
- Added 1MB advisory size warning via `shoal.journal` logger
- Updated CLI and MCP call sites to pass metadata on first journal append
- 1 commit (`176aebd`), 836 tests passing (18 new in test_journal.py), lint/mypy --strict/bandit clean

**What to do next:**

- Version bump to v0.17.0
- Server Composition Gateway investigation (FastMCP `mount()`)
- Documentation for new features (journal frontmatter, journal archive, local templates, HTTP transport)
- Consider `shoal journal --archived <session>` CLI for reading archived journals
- Nerd Font toggle in `shoal ls` (deferred — glyphs now populated, needs config flag)

### Session: 2026-02-23 — Demo & onboarding system overhaul

**What we did:**

- Split monolithic `demo.py` (1249 lines) into `cli/demo/` package: `__init__.py`, `start_stop.py`, `tour.py`, `tutorial.py`
- Redesigned tour from 9 internal-verification steps to 7 user-facing feature steps (Session Lifecycle, Status Detection, Templates & Inheritance, Journals, Diagnostics, MCP Orchestration, Theme & Status)
- Each tour step is an independent async function returning `TourResult` dataclass
- Added `shoal demo tutorial` — interactive 7-step guided walkthrough with real sessions, worktrees, journals, diagnostics, and templates
- Tutorial features: `--cleanup` flag, `--step N` resume, Ctrl+C crash recovery via marker file
- Added next-step prompts to `shoal init` and `shoal setup fish`
- Updated fish completions with `tour` and `tutorial` subcommands
- 5 commits, 24 demo tests passing (7 new), lint/mypy --strict clean

**What to do next:**

- Version bump to v0.17.0
- Server Composition Gateway investigation (FastMCP `mount()`)
- Consider adding `shoal demo tutorial` to the robo-orchestrator template prompt
