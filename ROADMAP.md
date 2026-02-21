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

## v0.7.1: Runtime Contract Stabilization (In Progress)

**Priority: Stabilize tmux/Neovim/runtime behavior before v0.8.0 tagging.**

- ✅ **Socket Contract Alignment**: Moved Neovim socket routing to tmux ID coordinates (`session_id`, `window_id`).
- ✅ **Dynamic Resolution**: `shoal nvim` resolves socket paths at execution time to avoid stale metadata drift.
- ✅ **Rename Stability**: Socket targeting now survives tmux/session-name changes.
- ✅ **Watcher Stability**: Status watcher is pinned to the session-tagged pane (`shoal:<session_id>`) and ignores active-pane drift.
- 🔄 **Release Hygiene**: Final docs and cleanup pass before v0.8.0.

## v0.8.0: Session Template MVP + Safety Rails

**Priority: ship template workflows while preventing state drift during setup failures.**

- **Template Schema**: Add declarative templates for windows, panes, and startup commands.
- **Profile Workflows**: Define reusable profiles for common project/task types.
- **`shoal new --template`**: Create sessions/worktrees from a named template.
- **Validation**: Add template validation and dry-run output before execution.
- **Failure Compensation**: Ensure create/fork failures cleanly rollback DB rows, tmux sessions, and worktree artifacts.
- **Startup Contract**: Unify startup command failure handling between CLI and API.
- **Nvim Diagnostics Safety**: Replace fragile dynamic `luaeval` command composition with a safer invocation path.
- **MCP Name Validation**: Enforce MCP name format consistently across API/CLI/proxy paths.

## v0.8.1: Reliability and Error Taxonomy

**Priority: make runtime failures diagnosable and deterministic.**

- **Typed Errors**: Replace broad `except Exception` in watcher/API/session hot paths with scoped exception handling.
- **Error Taxonomy**: Introduce shared tmux/git/mcp error types and map them to stable CLI/API responses.
- **Structured Logging**: Add operation and session identifiers to create/fork/rename/kill logs.
- **Failure-Path Tests**: Add targeted tests for tmux unavailable, startup command interpolation failures, and stale runtime artifacts.
- **WebSocket Robustness**: Harden connection cleanup and broadcast failure handling with explicit metrics/log counters.

## v0.8.2: Maintainability Refactor (Behavior Preserving)

**Priority: reduce regression risk by extracting shared orchestration logic.**

- **Lifecycle Service Layer**: Move create/fork/rename/kill orchestration into shared services used by both CLI and API.
- **File Decomposition**: Split `cli/session.py` and `api/server.py` by concern (transport, orchestration, rendering).
- **Template Execution Reuse**: Remove duplicated startup execution paths and keep one implementation.
- **Parity Contract Tests**: Add tests proving CLI and API session lifecycle commands follow the same behavior contracts.
- **Complexity Budget**: Reduce `session.py`/`server.py` size and cyclomatic complexity by at least 25%.

## v0.8.3: Concurrency and Runtime Hardening

**Priority: improve correctness under concurrent operations and runtime churn.**

- **Async Safety for tmux/git Calls**: Move blocking subprocess calls off the event loop in API/watcher contexts.
- **Session Update Concurrency**: Prevent lost updates for status/MCP/rename flows with optimistic or transactional update guards.
- **Startup Reconciliation**: Add boot-time checks to reconcile stale DB rows, stale sockets, and missing tmux sessions.
- **Concurrent Integration Tests**: Add stress tests for websocket status broadcasting and simultaneous lifecycle operations.
- **Load Targets**: Define and track latency/error targets for API status and session creation endpoints under parallel load.

## Brain Dump

- [x] Demo templates: Configure demo to start with two panes -- one for opencode and one for the current demo output
- [x] Change demo output to list instead of boxes, and have it include examples of what to run in the opencode window (assumes they are logged in -- up to them to do so)
- [x] Demo tmux naming: Keep demo tmux session names stable (`demo-main`, `demo-feature`, `demo-robo`) regardless of configured global session prefix.

## Future Considerations

- **FastMCP Integration**: Native support for the FastMCP protocol.
- **Session Templates v2**: Advanced inheritance/composition after MVP stabilizes.
- **Remote Sessions**: Support managing sessions on remote machines via SSH.
- **Ruff Lint Expansion**: Enforce stricter async and security linting rules.
