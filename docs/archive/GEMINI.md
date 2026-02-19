# Shoal: AI Agent Guidelines

This document outlines the architecture, conventions, and testing strategies for Shoal, designed to help Gemini and other AI agents contribute effectively to the project.

## Project Vision

Shoal is a terminal-first orchestrator for AI agents. It treats AI agents as first-class citizens in a developer's workflow, managing their lifecycle via tmux sessions and git worktrees.

## Architectural Patterns

- **Async-First**: The core state management (`shoal.core.state`) and API (`shoal.api.server`) are asynchronous, using `aiosqlite` and `anyio`.
- **SQLite State**: All persistent state is stored in a single SQLite database (`shoal.db`) using WAL mode for concurrency.
- **Subprocess Isolation**: Wrappers for `tmux` and `git` are isolated in `shoal.core.tmux` and `shoal.core.git`.
- **Pure Detection**: Status detection logic is a pure function in `shoal.core.detection`, making it easily testable without external dependencies.
- **XDG Compliance**: Config lives in `~/.config/shoal/`, persistent state in `~/.local/share/shoal/`, and logs/PIDs in `~/.local/state/shoal/`.

## Testing Strategy

Shoal maintains a high-quality test suite using `pytest` and `pytest-asyncio`.

### Key Test Files

- `tests/test_cli.py`: Tests for the Typer CLI commands using `CliRunner`. Note: CLI commands typically use `asyncio.run` internally, so these tests should **not** be marked with `@pytest.mark.asyncio` if they use `runner.invoke`.
- `tests/test_watcher.py`: Tests for the background polling and status detection logic. These are async tests.
- `tests/test_state.py`: Tests for SQLite CRUD operations (async).
- `tests/test_api.py`: Tests for the FastAPI server.

### Conventions

- **Mocking**: Always mock `tmux` and `git` calls in unit tests to avoid dependency on the host system's state.
- **Fixtures**: Use the `mock_dirs` fixture (defined in `conftest.py`) to ensure tests run against isolated temporary directories.
- **Verification**: After adding a feature, run the full suite: `uv run pytest`.

## Contribution Process for Agents

1.  **Understand**: Explore the existing command groups in `src/shoal/cli/`.
2.  **State**: If adding new state, update the Pydantic models in `src/shoal/models/state.py` and the database schema in `src/shoal/core/db.py`.
3.  **Implement**: Follow the pattern of keeping CLI handlers thin and delegating logic to `shoal.core`.
4.  **Test**: Add tests to the appropriate file in `tests/`. Ensure new CLI commands are added to `tests/test_cli.py`.
5.  **Document**: Update `README.md` and this file if project-wide patterns change.

## Useful Commands

- `uv run pytest`: Run all tests.
- `ruff check src/`: Linting.
- `mypy src/`: Type checking.
- `shoal check`: Verify local environment and dependencies.
