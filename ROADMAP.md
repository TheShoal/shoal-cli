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

- [ ] Replace manual JSON-RPC probe in `mcp doctor` with FastMCP Client
- [ ] Better error diagnostics from protocol-level failures

### Phase 3 — Transport evaluation (spike)

- [ ] Investigate FastMCP UDS transport support
- [ ] Measure HTTP vs UDS performance for MCP traffic
- [ ] Decide go/no-go for byte bridge replacement

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

- **FastMCP Transport Migration**: Replace byte bridge with FastMCP proxy if Phase 3 spike succeeds.
- **Server Composition Gateway**: Per-session MCP aggregation via FastMCP `mount()`.
- **Project-Local Templates**: `.shoal/templates/` search path in git root.
- **Oh-My-Pi (omp) Integration**: Add `omp.toml` tool definition and `omp-dev` session template mirroring existing pi support. Key opportunities: omp has native MCP (`omp plugin` system) enabling direct socket sharing with Shoal's MCP pool; detection patterns need tuning for omp's extended TUI (subagent/LSP status indicators beyond pi's base patterns); universal config discovery (reads `.claude/`, `.codex/`, `.gemini/` alongside `.omp/`) enables cross-agent workflow sharing.
- Expose hooks for configuration and runtime scripting
- Documentation catchup!! A lot will have changed by v0.16.0

---

## Handoff

> This section is maintained by Claude Code sessions. Each session records what was accomplished and what should happen next, so the next session (which may start with a fresh context) can pick up seamlessly.

### Session: 2026-02-22 — v0.10.1 MCP Stability & Observability

**What we did:**

- Implemented the full v0.10.1 plan (9 items, 5 phases) as 9 atomic commits on `feat/pi-agent-integration`:
    1. Version bump to 0.10.1
    2. Unified MCP name validation (removed duplicate regex from proxy)
    3. Shell injection fix in mcp_configure (shlex.split + shell=False)
    4. Narrowed exception handling in lifecycle startup paths
    5. MCP server logging with 10MB rotation + `shoal mcp logs` command
    6. `shoal mcp doctor` command (PID, socket, JSON-RPC health probing)
    7. Connection/idle timeouts (30s connect, 120s idle) in proxy and pool
    8. Architecture docs corrected to per-connection spawning semantics
    9. Dirty worktree protection on session kill (DirtyWorktreeError, --force, API 409)
- All 351 tests passing, ruff lint clean, ruff format clean
- 3 pre-existing mypy errors remain (mcp_configure.py:90, mcp_proxy.py:55,57) — not introduced by this work
- Updated ROADMAP with v0.10.1 completion and corrected v0.11.0 Tier 1 status
- Created `/shoal-handoff` skill for session continuity
- Tagged v0.10.1

**What to do next:**

- Merge `feat/pi-agent-integration` to `main` (or open PR for review)
- Fix the 3 pre-existing mypy errors (dict type-arg in mcp_configure, StreamWriter arg-type in mcp_proxy)
- Start v0.11.0 remaining items: mypy in pre-commit, parallel CI jobs, coverage reporting, Bandit, release automation
- Consider addressing Brain Dump items: regex detection upgrade, session.py decomposition

### Session: 2026-02-22 — v0.11.0 Developer Tooling & CI/CD

**What we did:**

- Fixed 3 pre-existing mypy strict errors (StreamWriter protocol arg, unused type-ignore, bare dict annotation)
- Added mypy strict to pre-commit hooks (completes Tier 1)
- Split CI into 5 parallel jobs: lint, typecheck, test, fish-check, security
- Added Bandit security linter to pre-commit and CI with pyproject.toml config
- Added release automation: `just release X.Y.Z` + GitHub Actions release workflow on tag push
- Updated CONTRIBUTING.md with security, release, and branch protection docs
- Bumped version to 0.11.0, marked Tiers 1-2 complete in roadmap
- Added `[tool.uv] link-mode = "copy"` to fix hardlink warnings on cross-filesystem venvs
- 5 commits on `main`, 373 tests passing, mypy/ruff/bandit all clean

**What to do next:**

- Push 5 new commits to remote (`git push`)
- Tag v0.11.0 (`git tag -a v0.11.0 -m "Release v0.11.0"` + `git push --tags`) to trigger release workflow
- Fix `uv.lock` ownership (owned by `eli`, should be `nick:dev`) — `sudo chown nick:dev uv.lock`
- Investigate missing `/shoal-handoff` skill — may be a GNU Stow / dotfiles symlink issue with `.claude/` config
- v0.11.0 Tier 3 (nice-to-have): CodeQL/Semgrep, pytest-xdist, py.typed marker, Renovate
- Consider starting v1.0.0 items: CLI/API parity tests, coverage gate, documentation audit

### Session: 2026-02-22 — v0.11.0 Tier 3 + v1.0.0 Prep

**What we did:**

- Synced `__init__.py` version to 0.11.0 (was stale at 0.10.1), created annotated `v0.11.0` tag
- Completed all v0.11.0 Tier 3 items (4 commits):
    - CodeQL SAST scanning (`.github/workflows/codeql.yml`)
    - pytest-xdist added to dev deps for parallel test execution
    - `src/shoal/py.typed` PEP 561 marker with wheel inclusion
    - Renovate evaluated — staying with Dependabot
- Removed all backward-compat shims (1 atomic commit, 9 files):
    - `conductor`/`cond`/`add` CLI aliases, config fallback paths, Pydantic model aliases
    - `get_status_style` re-export from `core/state.py` — imports moved to `core/theme.py`
    - Removed 3 backward-compat tests; DB table name `conductors` retained for migration later
- Boosted test coverage from 72% → 81% (156 new tests across 4 files):
    - 31 API server tests (67% → 84%), 66 lifecycle tests (61% → 94%)
    - 44 template/watcher/worktree tests, 15 session CLI tests
    - Raised `fail_under` from 70 to 80 in `pyproject.toml`
- Added 18 CLI/API parity tests (`tests/test_parity.py`):
    - Structural: both import same lifecycle functions and exception types
    - Behavioral: error handling, rename validation, fork is CLI-only by design
- Backfilled CHANGELOG from v0.6.0 through v0.11.0 (was missing 7 releases)
- Updated README badges (version v0.11.0, 543 tests, 81% coverage)
- Marked all v1.0.0 checklist items complete in ROADMAP
- 9 commits on `main` after v0.11.0 tag, 543 tests passing, all CI green

**What to do next:**

- Push all commits and tag to remote: `git push origin main && git push origin v0.11.0`
- Verify GitHub Actions release workflow triggers on tag push
- Clean up stale tmux sessions from test runs (`_collision`, `_test_cli_*`) — these cause flaky `test_state.py` failures
- Brain Dump items remain: regex detection upgrade, session.py decomposition, MCP socket cleanup on reboot
- Future: FastMCP integration, session templates v2, remote sessions

### Session: 2026-02-22 — v0.12.0 Brain Dump Cleanup

**What we did:**

- Upgraded detection engine from substring matching to compiled regex patterns:
    - `DetectionPatterns` pre-compiles patterns via `model_validator` with `PrivateAttr`
    - `detect_status()` uses `re.search()` instead of `in` operator
    - Added 5 regex-specific tests (word boundaries, anchors, alternation, invalid regex, compiled access)
- Decomposed `session.py` (1,069 lines) into 3 focused modules:
    - `session.py` (~150 lines): attach, detach, rename, prune, popup
    - `session_create.py` (~320 lines): add, fork, kill + branch utilities
    - `session_view.py` (~330 lines): ls, status, info, logs
    - Updated `__init__.py` imports and all test patch paths (8 test files)
- Added MCP socket cleanup to `shoal init`:
    - Renamed `_reconcile_mcp_pool` → `reconcile_mcp_pool` (public API)
    - Init calls reconciliation after `ensure_dirs()`, reports cleaned sockets
    - Added 2 tests for init cleanup behavior
- Bumped version to 0.12.0, marked all Brain Dump items complete
- 553 tests passing, ruff/mypy/bandit all clean

**What to do next:**

- Commit, tag v0.12.0
- Brain Dump is now empty — consider adding new items or starting Future Considerations
- Future: FastMCP integration, session templates v2, remote sessions, ruff lint expansion

### Session: 2026-02-22 — v0.13.0 Ruff Lint Expansion + Roadmap Planning

**What we did:**

- Researched all 4 Future Considerations (FastMCP, Templates v2, Remote Sessions, Ruff Lint)
- Converted Future Considerations into concrete v0.13.0–v0.16.0 milestones in ROADMAP
- Implemented v0.13.0 Ruff Lint Expansion:
    - Added 10 new ruff rule sets: ASYNC, PERF, RUF, LOG, G, C4, PIE, DTZ, RET, RSE, S
    - Fixed 29 violations including 1 genuine event-loop-blocking bug in lifecycle.py
    - Wrapped 6 blocking subprocess.run() calls in asyncio.to_thread()
    - Consolidated Bandit security scanning into ruff S rules
    - Removed Bandit from pre-commit and CI (replaced by ruff --select S)
- 553 tests passing, ruff/mypy all clean, 0 new violations

**What to do next:**

- v0.14.0: Session Templates v2 (extends + mixins)
- v0.15.0: FastMCP Integration (Shoal-as-MCP-server for robo supervisors)
- v0.16.0: Remote Sessions (SSH tunnel + HTTP client)

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
