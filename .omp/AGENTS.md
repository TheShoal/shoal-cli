# Shoal CLI — OMP Project Context

This project uses the global `shoal` skill for architecture and CLI reference.
Full Claude Code context is in `CLAUDE.md` and `ARCHITECTURE.md` at the repo root.

## OMP-specific notes

Quality gates active in this session (shoal-dev extension):
- Any `.py` edit → `ruff check --fix` (lint, on top of global ruff format)
- Any `.py` edit in `src/shoal/` → `mypy --strict` on the file
- `pip install` in bash → blocked; use `uv` instead

## Key facts

- Python 3.12+, hatchling build backend (not setuptools)
- All I/O is `async/await`. Blocking calls in async contexts → `asyncio.to_thread()`
- Fish templates at `src/shoal/integrations/fish/templates/*.fish` must pass `fish -n`
- Integration tests (`@pytest.mark.integration`) require a live tmux session
- Run `just ci` before committing (lint → typecheck → test → fish-check → security)
- Conventional commits enforced by gitlint: `feat|fix|docs|style|refactor|perf|test|chore: lowercase`
