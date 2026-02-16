# Shoal Roadmap

This roadmap outlines the planned development for Shoal as it moves toward a stable v1.0.0 for internal use at US Mobile.

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

## v0.4.3: Security & Test Hardening (In Progress)

**Priority: Address immediate security gaps and test coverage issues identified in code audit.**

- **Security Fixes**:
  - Fix demo command: create `.worktrees` parent directory before `git worktree add`
  - Add comprehensive session name validation (regex, length, reserved names)
  - Apply validation at all CLI entry points (new, fork, rename)
  - Apply validation at all API entry points (POST /sessions, PUT /sessions/{id}/rename)
- **Performance Fixes**:
  - Fix N+1 query in GET /mcp endpoint (hoist `list_sessions()` out of loop)
- **Test Coverage Expansion**:
  - Add watcher service tests (tmux death, status transitions, notifications)
  - Create MCP proxy tests (argument parsing, socket checks, execvp)
  - Add status bar edge case tests (mixed statuses)
- **Code Quality**:
  - Unify SessionStatus models (remove API duplicate)
  - Update ShoalDB docstring (clarify single connection vs pool)
  - Document sync-in-async patterns in tmux.py
  - Clarify stopped/unknown status handling in status bar

## v0.5.0: Advanced Testing & Polish

**Priority: Comprehensive testing, performance optimization, and developer experience.**

**Note:** Security and code quality issues from original v0.5.0 scope moved to v0.4.3 for immediate resolution.

- **Database & Performance**:
  - Evaluate need for connection pooling based on API load testing
  - Profile database operations under realistic multi-user scenarios
  - Optimize popup.py to reduce multiple DB connection cycles
- **Testing Infrastructure**:
  - Achieve 70%+ test coverage across all modules
  - Add integration tests for full workflows (new → fork → kill)
  - Add load tests for API server with concurrent requests
- **Developer Experience**:
  - Improve error messages with file:line references
  - Add `--debug` flag for verbose logging
  - Create troubleshooting guide for common issues

## v0.6.0: Event-Driven Architecture

**Priority: Infrastructure for real-time UI features.**

- **Event Bus**: Implement an internal pub/sub system for session state changes.
- **WebSocket Updates**: Real-time state pushing to the API and UI.
- **Enhanced Watcher**: Use the event bus instead of polling for faster, more efficient notifications.

## v0.7.0: The Interface

**Priority: User experience and TUI polish.**

- **Advanced Popup**: Add preview panes and interactive log tailing to the fzf dashboard.
- **Tmux Integration**: Configurable status bar segments with color-coded health checks.
- **Visuals**: Explore a minimal web dashboard for visualizing complex multi-agent workflows.

## Future Considerations

- **FastMCP Integration**: Native support for the FastMCP protocol.
- **Session Templates**: Predefined session configurations for common stacks.
- **Remote Sessions**: Support managing sessions on remote machines via SSH.
- **Ruff Lint Expansion**: Enforce stricter async and security linting rules.
