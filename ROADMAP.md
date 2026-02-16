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

## v0.5.0: Foundation Hardening (Next Up)

**Priority: Security, stability, and infrastructure quality.**

- **Database & Performance**:
  - Implement proper connection pooling for `ShoalDB`.
  - Fix any remaining N+1 query patterns.
- **Security**:
  - Audit command injection risks in notification handlers.
  - Add input validation for user-provided session names.
- **Code Quality**:
  - Unify `SessionStatus` models across CLI and API.
  - Improve sync/async boundaries and documentation.
  - Complete test coverage for background services.

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
