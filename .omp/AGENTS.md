# Shoal CLI — OMP Project Context

This project uses the global `shoal` skill for architecture and CLI reference.
Full Claude Code context is in `CLAUDE.md` and `ARCHITECTURE.md` at the repo root.

## OMP-specific notes

Quality gates active in this session (shoal-dev extension):
- Any `.py` edit → `ruff check --fix` (lint, on top of global ruff format)
- Any `.py` edit in `src/shoal/` → `mypy --strict` on the file
- `pip install` in bash → blocked; use `uv` instead

## Quick reference

```bash
just ci          # Full pipeline: lint → typecheck → test → fish-check → security
just test        # Unit tests only (excludes integration)
just test-all    # All tests including integration (requires tmux)
just lint        # Ruff lint
just fmt         # Ruff auto-format
just typecheck   # mypy --strict
just cov         # Tests with coverage report
just fish-check  # Validate fish template syntax
```

Prefer targeted tests: `uv run pytest tests/test_lifecycle.py -x -q`

## Key facts

- Python 3.12+, hatchling build backend (not setuptools)
- Line length: 100 chars (ruff + mypy configured in pyproject.toml)
- Type hints: mandatory on all function signatures — `mypy --strict` enforced
- All I/O is `async/await`. Blocking calls in async contexts → `asyncio.to_thread()`
- Fish templates at `src/shoal/integrations/fish/templates/*.fish` must pass `fish -n`
- Integration tests (`@pytest.mark.integration`) require a live tmux session
- Run `just ci` before committing (lint → typecheck → test → fish-check → security)
- Conventional commits enforced by gitlint: `feat|fix|docs|style|refactor|perf|test|chore: lowercase`
- Pre-commit hooks enforce: trailing whitespace, EOF newline, YAML/TOML validity, ruff lint+format, gitlint

## Module layout

```
src/shoal/
├── api/          # FastAPI server (REST endpoints for sessions, MCP, status)
├── cli/          # Typer CLI (session, mcp, config, remote, demo commands)
│   └── demo/     # Demo subpackage (start/stop, tour, tutorial)
├── core/         # Business logic (config, database, state, tmux/git wrappers,
│                 #   journal, context propagation, remote tunnels, logging)
├── models/       # Pydantic models (config, session state, API schemas)
├── services/     # Lifecycle orchestration, MCP pool/proxy/server, status bar
├── integrations/ # Fish shell templates and tool-specific configs
└── dashboard/    # Terminal dashboard (Rich-based)
```

Console entry points: `shoal` (CLI), `shoal-mcp-proxy` (stdio-to-socket bridge), `shoal-mcp-server` (FastMCP orchestration server), `shoal-status` (status bar JSON)

## Architectural invariants

- **SQLite + WAL mode**: Single async connection via `aiosqlite`, concurrent update guard with `asyncio.Lock`
- **Lifecycle service**: `services/lifecycle.py` is the single orchestrator for create/fork/kill/reconcile — both CLI and API delegate to it
- **MCP pooling**: Shared MCP servers via asyncio Unix socket proxying — one listener per type, per-connection spawning
- **Status detection**: Tmux pane scraping with regex patterns per tool (configured in TOML tool profiles)
- **Git worktrees**: Session isolation via `git worktree add`, not branches in the main working tree
- **Pane identity**: `shoal:<session_id>` tmux pane titles for stable watcher targeting
- **Runtime provider**: `services/runtime_provider.py` dispatches through a provider seam (currently tmux-only)

## Gotchas

- Fish templates in `src/shoal/integrations/fish/templates/*.fish` must pass `fish -n` syntax validation
- The project uses `hatchling` as build backend, not setuptools
- MCP pool uses pure Python asyncio (no socat dependency since v0.10.0)
- Integration tests (marked `@pytest.mark.integration`) require a running tmux session
- Pre-commit hooks enforce: trailing whitespace, EOF newline, YAML/TOML validity, ruff lint+format, gitlint
- `SessionState.runtime` is nested — `TmuxRuntimeState(kind="tmux", session_name=..., session_id=..., window_id=..., nvim_socket=...)`
- Ruff lint rules: E, F, I, UP, B, SIM, ASYNC, PERF, RUF, LOG, G, C4, PIE, DTZ, RET, RSE, S

## Tool discipline

**MUST use `write` (not `edit`) for these file types:**
- `justfile` — `edit` inserts blank lines between recipe name and body, breaking `just` parsing
- `*.yaml` / `*.yml` — `edit` inserts blank lines between keys, corrupting YAML structure
- `*.toml` — same blank-line insertion problem

**Verification discipline:**
- For doc-only changes: run `just docs-lint` + `just docs-build`, not `just ci`
- For Python-only changes: run `just fmt-check lint typecheck test`, not `just ci`
- Never run `just ci` as a reflexive check — it runs the full test suite and takes 10+ seconds
