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

## v0.4.1: Polish & Onboarding (In Progress)

**Priority: User experience and production readiness.**

- **Documentation**:
  - Add usage examples and screenshots to README.
  - Document robo workflow patterns.
  - Create video/GIF demo of `shoal popup` and status bar.
- **Testing & Quality**:
  - Measure baseline coverage with `pytest-cov`.
  - Add integration tests for demo command.
  - Improve error messages for common user mistakes.
- **Performance**:
  - Profile and optimize `list_sessions()` queries.
  - Review database connection lifecycle.

## v0.5.0: Foundation Hardening

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
