# CLAUDE.md

Shoal is a terminal-first orchestration tool for parallel AI coding agents. Python 3.12+, async-first, fish shell integration.

## Quick Reference

```bash
just ci          # Run all checks: lint → typecheck → test → fish-check
just test        # Unit tests only (excludes integration)
just test-all    # All tests including integration (requires tmux)
just lint        # Ruff lint
just fmt         # Ruff auto-format
just typecheck   # mypy --strict
just cov         # Tests with coverage report
just fish-check  # Validate fish template syntax
```

Prefer running targeted tests: `uv run pytest tests/test_lifecycle.py -x -q`

## Code Style

- **Line length**: 100 chars (ruff + mypy configured in pyproject.toml)
- **Type hints**: Mandatory on all function signatures — `mypy --strict` is enforced
- **Formatting**: ruff format (runs via pre-commit)
- **Lint rules**: E, F, I, UP, B, SIM (see `[tool.ruff.lint]` in pyproject.toml)
- **Imports**: Sorted by ruff (isort-compatible), absolute imports preferred
- **Async**: All I/O operations use `async/await`. Blocking subprocess calls in async contexts MUST use `asyncio.to_thread()`

## Module Layout

```
src/shoal/
├── api/          # FastAPI server (REST endpoints for sessions, MCP, status)
├── cli/          # Typer CLI (session, mcp, config commands)
├── core/         # Business logic (config, database, state, tmux/git wrappers)
├── models/       # Pydantic models (config, session state, API schemas)
├── services/     # Lifecycle orchestration, MCP pool/proxy, status bar
├── integrations/ # Fish shell templates and tool-specific configs
└── dashboard/    # Terminal dashboard (Rich-based)
```

## Architectural Invariants

- **SQLite + WAL mode**: Single async connection via `aiosqlite`, concurrent update guard with `asyncio.Lock`
- **Lifecycle service**: `services/lifecycle.py` is the single orchestrator for create/fork/kill/reconcile — both CLI and API delegate to it
- **MCP pooling**: Shared MCP servers via socat Unix socket proxying — one server instance per type
- **Status detection**: Tmux pane scraping with regex patterns per tool (configured in TOML tool profiles)
- **Git worktrees**: Session isolation via `git worktree add`, not branches in the main working tree
- **Pane identity**: `shoal:<session_id>` tmux pane titles for stable watcher targeting

## Gotchas

- Fish templates in `src/shoal/integrations/fish/templates/*.fish` must pass `fish -n` syntax validation
- The project uses `hatchling` as build backend, not setuptools
- `socat` is a runtime dependency for MCP socket proxying
- Integration tests (marked `@pytest.mark.integration`) require a running tmux session
- Pre-commit hooks enforce: trailing whitespace, EOF newline, YAML/TOML validity, ruff lint+format, gitlint

## Commits

Conventional commits enforced by gitlint: `feat|fix|docs|style|refactor|perf|test|chore: lowercase description`

See @COMMIT_GUIDELINES.md for full spec and examples.

## Architecture

See @ARCHITECTURE.md for design decisions, data flow, and component relationships.
