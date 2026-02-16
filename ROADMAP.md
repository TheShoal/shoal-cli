# Shoal Roadmap

This roadmap outlines the planned development for Shoal as it moves toward a stable v1.0.0 for internal use at US Mobile.

## v0.4.1: Foundation Hardening (Next Up)

**Priority: Critical infrastructure fixes and security.**

- **Database & Performance**:
  - Implement proper connection pooling for `ShoalDB`.
  - Fix N+1 query patterns in `list_sessions()`.
- **Security**:
  - Fix command injection vulnerability in notification handlers via `shlex.quote()`.
- **Code Quality**:
  - Unify `SessionStatus` models.
  - Improve sync/async boundaries and documentation.
- **Testing**:
  - Measure baseline coverage with `pytest-cov`.
  - Complete patch coverage for background services.

## v0.5.0: Event-Driven Architecture

**Priority: Infrastructure for real-time UI features.**

- **Event Bus**: Implement an internal pub/sub system for session state changes.
- **WebSocket Updates**: Real-time state pushing to the API and UI.
- **Enhanced Watcher**: Use the event bus instead of polling for faster, more efficient notifications.

## v0.6.0: The Interface

**Priority: User experience and TUI polish.**

- **Advanced Popup**: Add preview panes and interactive log tailing to the fzf dashboard.
- **Tmux Integration**: Configurable status bar segments with color-coded health checks.
- **Visuals**: Explore a minimal web dashboard for visualizing complex multi-agent workflows.

## Someday / Maybe

- **FastMCP Integration**: Native support for the FastMCP protocol.
- **Session Templates**: Predefined session configurations for common stacks.
- **Remote Sessions**: Support managing sessions on remote machines via SSH.
- **Ruff Lint Expansion**: Enforce stricter async and security linting rules.
