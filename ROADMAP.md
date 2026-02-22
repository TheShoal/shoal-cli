# Shoal Roadmap

This roadmap outlines the planned development for Shoal as a fish-first, personal workflow tool that may still be useful to others.

## Completed Milestones

### v0.4.0 (Released: 2026-02-16)

- ✅ SQLite migration with WAL mode
- ✅ Async-first architecture using `aiosqlite` and `anyio`
- ✅ Session rename, logs, and info commands
- ✅ Session grouping by git root
- ✅ Robo supervisor interactions (send keys, approve actions)
- ✅ Tmux startup commands
- ✅ Conductor → Robo rename with backward compatibility
- ✅ Interactive demo command (`shoal demo`)
- ✅ Consistent Panel styling with Nerd Font icons

### v0.4.1 (Released: 2026-02-16)

- ✅ Comprehensive robo workflow guide (docs/ROBO_GUIDE.md)
- ✅ Release process documentation (RELEASE_PROCESS.md)
- ✅ Enhanced error messages with actionable suggestions
- ✅ README improvements (use cases, examples, documentation links)
- ✅ Database optimization (indexed session name lookups)
- ✅ Test coverage baseline measurement (52%)

### v0.4.2 (Released: 2026-02-16)

- ✅ Database connection lifecycle fixes (nvim commands, API server shutdown)
- ✅ Code quality improvements (deduplication, type safety, error logging)
- ✅ Test infrastructure expansion (demo, git, tmux, MCP pool tests)
- ✅ Test coverage improvement (52% → 57%)
- ✅ Added pytest-cov with coverage reporting
- ✅ Security fix: Quote script paths in demo command

### v0.4.3 (Released: 2026-02-17)

**Priority: Security hardening and code quality improvements.**

- **Security Fixes**:
    - ✅ Verified demo command `.worktrees` parent directory creation (already implemented)
    - ✅ Added Pydantic field validators for session names (SessionState, SessionCreate)
    - ✅ Added validation inside `update_session()` when name parameter is provided
    - ✅ Implemented `PUT /sessions/{id}/rename` API endpoint with full validation
    - ✅ Applied validation at all entry points (CLI new/fork/rename, API POST/PUT)
- **Performance Fixes**:
    - ✅ Verified N+1 query prevention in GET /mcp endpoint (already implemented)
    - ✅ Added test to verify `list_sessions()` is called exactly once
- **Test Coverage Expansion**:
    - ✅ Added CLI rename with invalid name test
    - ✅ Added API session creation with invalid name test
    - ✅ Added API rename endpoint tests (success, 404, invalid, duplicate)
    - ✅ Added `update_session()` with invalid name test
    - ✅ Added GET /status with unknown sessions test
    - ✅ Added GET /mcp N+1 prevention test
    - ✅ Verified MCP proxy test coverage (already adequate)
    - ✅ Test coverage improvement (57% → 59%)
- **Code Quality**:
    - ✅ Fixed StatusResponse model (added missing `unknown` field)
    - ✅ Updated GET /status endpoint to include unknown count
    - ✅ Updated ShoalDB docstring (clarified single connection, WAL mode, lifecycle)
    - ✅ Documented sync-in-async patterns in tmux.py module docstring
    - ✅ Added comment explaining stopped/unknown exclusion in status bar

### v0.4.4 (Released: 2026-02-17)

**Priority: Critical bug fixes and UI/UX improvements.**

- **Critical Bug Fixes**:
    - ✅ Fixed nested `asyncio.run()` crash in 7 commands (attach, fork, kill, wt finish, nvim send/diagnostics, mcp attach)
    - ✅ Fixed branch naming logic (respect existing prefix in worktree names)
    - ✅ Fixed syntax error in mcp.py (extra closing parenthesis)
    - ✅ Restored missing `check` command
    - ✅ Added success message to `init` command
    - ✅ Fixed MCP status to show panel even with 0 servers
- **UI/UX Centralization**:
    - ✅ Created `src/shoal/core/theme.py` module (single source of truth for styling)
    - ✅ Centralized status colors, icons, and table/panel factories
    - ✅ Replaced 100+ inline color/icon references with theme imports
    - ✅ Switched tmux status bar to Unicode symbols (●, ○, ◉, ✗) for universal rendering
    - ✅ Kept Nerd Font glyphs available via optional parameter
- **Code Quality**:
    - ✅ Refactored 6 CLI files to use theme module
    - ✅ Updated test assertions for new Unicode icons
    - ✅ All 161 tests passing (11 skipped)

### v0.5.0 (Released: 2026-02-17)

**Priority: Native fish shell integration for enhanced developer experience.**

- **Fish Shell Support**:
    - ✅ Added `shoal setup fish` command to install integration files
    - ✅ Created `~/.config/fish/conf.d/shoal.fish` bootstrap script
    - ✅ Created `~/.config/fish/completions/shoal.fish` with dynamic session name completions
    - ✅ Added helper functions in `~/.config/fish/functions/` for common workflows
    - ✅ Implemented fish key bindings for instant dashboard access (Ctrl+S, Alt+A)
    - ✅ Added universal variables for cross-session state sharing
    - ✅ Added fish event handlers (fish_preexec) for automatic status detection
    - ✅ Created abbreviations for common shoal commands (sa, sl, ss, sp, sn, sk, si)
    - ✅ Fish is now the primary supported shell experience
- **Theme Module Enhancements**:
    - ✅ Added plain-text output variants for fish completions (`--format plain`)
    - ✅ Ensured `--format plain` works for `ls` and `status` commands
    - ✅ Documented fish integration in README and dedicated guide (docs/FISH_INTEGRATION.md)
- **Testing**:
    - ✅ Added 8 comprehensive tests for fish setup command
    - ✅ All 169 tests passing (11 skipped)

## v0.6.0: Advanced Testing & Polish (Released: 2026-02-17)

**Priority: Comprehensive testing, performance optimization, and developer experience.**

- **Testing Infrastructure**:
    - ✅ Add watcher service tests (tmux death detection, status transitions, notifications)
    - ✅ Add status bar edge case tests (all sessions in one status, large counts, mixed statuses)
    - ✅ Achieve 70%+ test coverage across all modules (reached 77%)
    - ✅ Add integration tests for full workflows (new → fork → kill)
    - ✅ Add load tests for API server with concurrent requests
- **Database & Performance**:
    - ✅ Evaluate need for connection pooling based on API load testing (not required for v0.6.0)
    - ✅ Profile database operations under realistic multi-user scenarios
    - ✅ Optimize popup.py to reduce multiple DB connection cycles
- **Developer Experience**:
    - ✅ Improve error messages with actionable suggestions
    - ✅ Add `--debug` flag for verbose logging (global flag)
    - ✅ Create troubleshooting guide for common issues (docs/TROUBLESHOOTING.md)

## v0.7.0: Fish-First Scope Consolidation (Released: 2026-02-18)

**Priority: Align product surface with personal workflow constraints.**

- ✅ **Scope Reset**: Removed bash/zsh support claims from docs and examples.
- ✅ **CLI Clarity**: Kept fish setup and fish completions as the single supported shell path.
- ✅ **Demo Consistency**: Eliminated bash-dependent demo paths and scripts.
- ✅ **Tool Priority**: Kept OpenCode-first UX with Claude/Gemini as secondary profiles.
- ✅ **Template Foundation**: Added global template management and template-driven session startup.

## v0.7.1: Runtime Contract Stabilization (Released: 2026-02-21)

**Priority: Stabilize tmux/Neovim/runtime behavior before v0.8.0 tagging.**

- ✅ **Socket Contract Alignment**: Moved Neovim socket routing to tmux ID coordinates (`session_id`, `window_id`).
- ✅ **Dynamic Resolution**: `shoal nvim` resolves socket paths at execution time to avoid stale metadata drift.
- ✅ **Rename Stability**: Socket targeting now survives tmux/session-name changes.
- ✅ **Watcher Stability**: Status watcher is pinned to the session-tagged pane (`shoal:<session_id>`) and ignores active-pane drift.
- ✅ **Release Hygiene**: Final docs and cleanup pass before v0.8.0.
- ✅ **Pi Agent Support**: Added Pi coding agent tool config, detection patterns, and `pi-dev` session template.
- ✅ **Fish Enhancements**: Added tool/template completions, `--tool`/`--template`/`--dry-run` flag completions for `shoal new`.

## v0.8.0: Session Template MVP + Safety Rails (Released: 2026-02-21)

**Priority: ship template workflows while preventing state drift during setup failures.**

- ✅ **Template Schema**: Declarative templates for windows, panes, and startup commands with Pydantic validation.
- ✅ **Profile Workflows**: Reusable profiles for common project/task types (opencode, claude, pi, gemini).
- ✅ **`shoal new --template`**: Create sessions/worktrees from a named template (implemented in v0.7.0).
- ✅ **Validation**: Template schema validation (name format, pane sizes, first-pane-is-root, requires windows) and dry-run output.
- ✅ **Failure Compensation**: Create/fork failures cleanly rollback DB rows, tmux sessions, and worktree artifacts in both CLI and API.
- ✅ **Startup Contract**: Unified startup command failure handling between CLI and API with full rollback.
- ✅ **Nvim Diagnostics Safety**: Replaced fragile dynamic `luaeval` string composition with temp-file Lua script invocation.
- ✅ **MCP Name Validation**: `validate_mcp_name()` enforced consistently across API `McpCreate`, CLI `mcp start`/`mcp attach`, and `start_mcp_server()`/`stop_mcp_server()`.

## v0.8.0a: Review-Driven Fixes (Released: 2026-02-21)

**Priority: address must-fix and should-fix issues from v0.8.0 code review before moving on.**

### Must-fix (blocking)

- ✅ **Tempfile Race**: Replace deprecated `tempfile.mktemp()` in `cli/nvim.py` with `NamedTemporaryFile(delete=False)`. Move `import tempfile` to module top.
- ✅ **Overly Broad Exception Catch**: `server.py:371` `except (ValueError, Exception)` catches all errors including programming bugs and converts them to a generic 500. Narrowed to `Exception` with `logger.warning` for startup failure diagnostics.

### Should-fix (high priority)

- ✅ **Pi Detection Ambiguity**: Removed `"❯"` from `waiting_patterns` and dead `idle_patterns` field so Pi prompt falls through to idle. Updated both `pi.toml` and `tests/conftest.py`.
- ✅ **Rollback Guard Fragility**: Changed CLI guards in `session.py` to check `wt_path` truthiness, aligning with the API pattern.
- ✅ **Fish Completion Glob Safety**: Added `test -d` guards before globbing in `__shoal_tools` and `__shoal_templates`.
- ✅ **Remove `BRANCH_SUMMARY.md`**: Removed commit-planning artifact.

### Tests added

- ✅ `test_pi_idle_at_prompt`: Verify Pi shows idle (not waiting) when pane content is just the prompt.
- ✅ `test_pane_size_non_numeric`: `TemplatePaneConfig(size="abc%")` should raise.

## v0.8.0b: Demo Expansion & Code Review Fixes (Released: 2026-02-22)

**Priority: comprehensive demo proving feature correctness, plus bug fix from code review.**

### Bug fix

- ✅ **Worktree Param Bug**: Fixed `session.py` `_add_impl()` passing `work_dir` instead of `wt_path` as the `worktree` parameter to `create_session()`. Non-worktree sessions incorrectly stored their git root as a worktree path, breaking `shoal ls` display.

### Demo enhancements

- ✅ **`shoal demo tour` Command**: Guided walkthrough exercising 6 feature areas with live pass/fail results:
    - Session state queries (list_sessions, status counts)
    - Status detection engine (7 test cases across Claude and Pi tools)
    - Template validation (valid templates, rejected bad names/sizes/structure)
    - MCP server name validation (accepted/rejected patterns)
    - Session name validation (tmux-safe, security-checked)
    - Theme system (all 5 status styles with icons and colors)
- ✅ **4th Demo Session**: Added `demo-bugfix` with `fix/login-bug` worktree, showing parallel worktree isolation.
- ✅ **Varied Statuses**: Demo sessions get different statuses (running, idle, waiting, running) so `shoal status` shows a realistic dashboard.
- ✅ **Feature-Focused Panes**: Each demo session's info pane teaches about a specific feature area (session management, worktree isolation, status detection, robo coordination).
- ✅ **Richer Demo Project**: Added `pyproject.toml`, `api.py`, and enhanced `utils.py` with `add()` function.
- ✅ **Better Start Banner**: Commands grouped by feature area with `shoal demo tour` prominently featured.

### Tests added (302 total, 301 passing, 1 skipped)

- ✅ `test_create_demo_project_content`: Verify new project files are well-formed.
- ✅ `test_demo_start_varied_statuses`: Verify sessions get correct varied statuses.
- ✅ `test_demo_tour_all_pass`: Verify all 6 tour feature areas pass.
- ✅ `test_demo_tour_detection_engine`: Verify tour's detection tests match expected results.
- ✅ `test_demo_tour_with_sessions`: Verify tour displays session data when sessions exist.
- ✅ `test_demo_tour_no_failures`: Verify no tour checks produce failures.
- Updated `test_demo_start_happy_path` and `test_demo_start_custom_dir` for 4 sessions, 2 worktrees, feature flags.

---

## Upcoming

## v0.9.0: Lifecycle Hardening (Released: 2026-02-22)

**Priority: make failure paths robust and code maintainable before v1.0.**

This milestone combines the highest-value items from the previous v0.8.1–v0.8.3 plan into a single focused release.

### Failure-path coverage (highest priority)

- ✅ **Rollback integration tests**: Test that create/fork failures cleanly rollback DB + tmux + worktree when tmux.new_session raises or startup command interpolation fails.
- ✅ **API boundary validation test**: POST to `/mcp` with path-traversal name (`../../../etc`), verify 400.
- ✅ **Watcher resilience**: Log warning (not silently skip) when tool config is missing for a session.
- ✅ **Startup reconciliation**: Add boot-time check to reconcile stale DB rows with actual tmux session state (mark stopped if tmux session is gone).

### Lifecycle service extraction

- ✅ **Shared orchestration layer**: Extract create/fork/kill orchestration from `cli/session.py` and `api/server.py` into `services/lifecycle.py`. Eliminates duplicated rollback logic and reduces both files by ~30%.
- ✅ **Rollback helper**: Single `_rollback(session_id, tmux_name, wt_path, git_root)` function used by CLI and API, with async variant `_rollback_async()`.
- ✅ **Template execution reuse**: Merge duplicated startup paths into one implementation (sync + async variants in lifecycle.py).

### Error clarity

- ✅ **Structured logging**: Add session ID and operation name to create/fork/rename/kill log lines.
- ✅ **Scoped exceptions in watcher**: Replace broad `except Exception` with specific subprocess/config error handling.
- ✅ **WebSocket cleanup**: Explicit connection cleanup on broadcast failure.

### Async correctness

- ✅ **Async subprocess calls**: Move blocking `tmux._run()` and `git._run()` off the event loop in API/watcher contexts via `asyncio.to_thread()` wrappers (`async_*` prefixed functions).
- ✅ **Concurrent update guards**: Prevent lost status updates when watcher and user CLI both write to the same session row (asyncio.Lock in ShoalDB.update_session).

## v0.10.0: MCP Streamlining (Released: 2026-02-22)

**Priority: make MCP servers zero-friction by eliminating manual steps, external dependencies, and hardcoded configuration.**

### Foundation

- ✅ **Pure Python bridge**: Replace socat dependency with asyncio-based stdio↔unix-socket bridge in `mcp_proxy.py` and `mcp_pool.py`. Eliminates system dependency and shell injection surface.
- ✅ **Configurable server registry**: Replace hardcoded `KNOWN_SERVERS` with `~/.config/shoal/mcp-servers.toml`. Built-in defaults preserved as fallback.

### Core UX

- ✅ **Auto-configure on attach**: `shoal mcp attach` runs the tool's config command or merges into config file automatically. Falls back to manual hint if tool has no config method.
- ✅ **Auto-start on attach**: If MCP server is not running but is in registry, start it automatically before attaching.

### Lifecycle Integration

- ✅ **`--mcp` flag**: `shoal new --mcp memory,github` starts, attaches, and configures MCP servers during session creation. MCP failures warn but don't block session creation.
- ✅ **Template MCP declarations**: `SessionTemplateConfig` gains `mcp: list[str]`. Merged with `--mcp` flag (union, deduped).
- ✅ **Auto-cleanup and reconciliation**: MCP servers stopped when last session using them is killed. Boot-time reconciliation cleans orphaned sockets/PIDs.

## v0.10.1: MCP Stability & Observability (Released: 2026-02-22)

**Priority: harden MCP gaps from v0.10.0, add diagnostics, fix data-loss risk in kill.**

### Security & validation

- ✅ **Unified MCP name validation**: Remove duplicate regex from `mcp_proxy.py`, import `validate_mcp_name` from `mcp_pool` for consistent rules across pool and proxy.
- ✅ **Shell injection fix**: Replace `shell=True` with `shlex.split()` + `shell=False` in `mcp_configure.py`. Names with shell metacharacters no longer cause injection.
- ✅ **Narrow exception handling**: Replace `except (ValueError, Exception)` catch-all in lifecycle startup paths with specific types (`ValueError`, `CalledProcessError`, `TimeoutError`). Unexpected errors now propagate for debugging.

### Observability

- ✅ **MCP server logging**: Per-server log files in `~/.local/state/shoal/mcp-pool/logs/`. Pool server stderr and spawned MCP command stderr both captured. Log rotation truncates at 10MB.
- ✅ **`shoal mcp logs <name>`**: CLI command to view MCP server logs with `--tail` flag.
- ✅ **`shoal mcp doctor`**: Deep health check — probes PID liveness, socket connectivity, JSON-RPC initialize, and reports latency in a Rich table.

### Reliability

- ✅ **Connection timeouts**: 30s connect timeout on Unix socket connections in both proxy and pool. 120s idle timeout on read operations. Prevents hung connections from consuming resources.
- ✅ **Dirty worktree protection**: `kill_session_lifecycle()` checks for uncommitted changes before worktree removal. Raises `DirtyWorktreeError` unless `--force` is passed. CLI shows dirty files, API returns 409 Conflict.

### Documentation

- ✅ **Architecture corrections**: Rewrote ARCHITECTURE.md section 4 to describe per-connection spawning (not shared state). Removed socat references. Updated README MCP descriptions.

### Stats

- 351 tests passing, 9 commits, 0 regressions.

---

## Upcoming

## v0.11.0: Developer Tooling & CI/CD

**Priority: enforce quality locally and in CI; make the repo feel like a proper 2026 Python project.**

### Tier 1 — Local enforcement & dependency hygiene

- ✅ **Pre-commit framework**: `.pre-commit-config.yaml` with ruff (lint + format), gitlint, Fish syntax check (`fish -n`), trailing whitespace, end-of-file fixer, YAML/TOML validation.
- ✅ **Commitlint**: Conventional Commits validated via gitlint on `commit-msg` hook.
- ✅ **Dependabot**: `.github/dependabot.yml` for pip ecosystem and GitHub Actions version updates.
- ✅ **Task runner**: `justfile` with common targets — `just lint`, `just fmt`, `just test`, `just typecheck`, `just ci` (all), `just cov`, `just fish-check`.
- ✅ **`.editorconfig`**: 100-char line length, UTF-8, LF endings, trim trailing whitespace, final newline.
- ✅ **mypy in pre-commit**: Add mypy hook to pre-commit (currently only run via `just typecheck`).

### Tier 2 — CI improvements & security

- ✅ **Parallel CI jobs**: Split `.github/workflows/ci.yml` into 5 concurrent jobs: `lint`, `typecheck`, `test`, `fish-check`, `security`.
- ✅ **Coverage reporting**: Add `--cov-report=xml` to pytest and upload to Codecov on main branch pushes.
- ✅ **Bandit**: Python security linter in pre-commit (medium+ severity) and CI. Configured in `pyproject.toml`.
- ✅ **Release automation**: `just release X.Y.Z` bumps version, commits, tags. GitHub Actions workflow creates Release on tag push.
- ✅ **Branch protection**: Documented rules in CONTRIBUTING.md (CI pass required, review for external PRs, no force push to main).

### Tier 3 — Nice to have

- [x] **CodeQL or Semgrep**: CodeQL SAST scanning on PRs, main pushes, and weekly schedule.
- [x] **pytest-xdist**: Added for parallel test execution (`pytest -n auto`).
- [x] **`py.typed` marker**: Added `src/shoal/py.typed` with wheel inclusion for PEP 561.
- [x] **Renovate (alternative to Dependabot)**: Evaluated — staying with Dependabot. Simpler for a single-maintainer project.

## v1.0.0: Stable Release

**Priority: production-ready for daily personal use with confidence.**

- [x] **CLI/API parity tests**: 18 tests verifying CLI and API share lifecycle functions, exception types, and validation.
- [x] **Coverage gate**: Raised to 80%+ (81% achieved, 543 tests). CI enforcement via `fail_under = 80`.
- [x] **Documentation audit**: README badges updated, CHANGELOG backfilled from v0.6.0 through v0.11.0.
- [x] **Deprecation cleanup**: Removed conductor/cond/add aliases, config fallbacks, model aliases, and re-export shims.
- [x] **`get_status_style` re-export**: Removed from `state.py`; `session.py` and `worktree.py` import from `theme.py` directly.

## Brain Dump

- [x] Demo templates: Configure demo to start with two panes -- one for opencode and one for the current demo output
- [x] Change demo output to list instead of boxes, and have it include examples of what to run in the opencode window (assumes they are logged in -- up to them to do so)
- [x] Demo tmux naming: Keep demo tmux session names stable (`demo-main`, `demo-feature`, `demo-robo`) regardless of configured global session prefix.
- [ ] Regex detection: Upgrade detection engine from substring matching to compiled regex patterns for more precise status detection.
- [ ] Session.py decomposition: Split 700+ line file by concern (create, view, lifecycle) — currently tracked under v0.9.0 lifecycle extraction.
- [ ] MCP socket cleanup: Add cleanup on reboot or `shoal init` for stale `/tmp/shoal/mcp-pool/*.sock` files.

## Future Considerations

- **FastMCP Integration**: Native support for the FastMCP protocol.
- **Session Templates v2**: Advanced inheritance/composition after MVP stabilizes.
- **Remote Sessions**: Support managing sessions on remote machines via SSH.
- **Ruff Lint Expansion**: Enforce stricter async and security linting rules.

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
