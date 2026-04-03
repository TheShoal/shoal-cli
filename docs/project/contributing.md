# Contributing

Shoal is a personal workflow tool built for sustained daily use. Contributions that align with the design principles are welcome.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- [just](https://just.systems/) for task running
- tmux (for integration tests)
- Fish shell (for fish-check and integration tests)

## Setup

```bash
git clone https://github.com/TheShoal/shoal-cli
cd shoal-cli
uv sync --all-extras
uv run pre-commit install
```

## Development workflow

```bash
just ci          # full gate: lint → typecheck → test → fish-check → security
just test        # unit tests only (fast)
just test-all    # all tests including integration (requires tmux)
just lint        # ruff lint
just fmt         # ruff auto-format
just typecheck   # mypy --strict
just cov         # tests + coverage report
just fish-check  # validate fish template syntax
```

Prefer targeted test runs during development:

```bash
uv run pytest tests/test_lifecycle.py -x -q
```

## Code standards

- **Type hints**: mandatory on all function signatures — `mypy --strict` enforced
- **Line length**: 100 chars
- **Imports**: absolute, sorted by ruff
- **Async**: all I/O uses `async/await`; blocking calls in async contexts must use `asyncio.to_thread()`
- **Commits**: [Conventional Commits](commit-guidelines.md) enforced by `gitlint`

## Pull requests

1. Fork the repo and create a branch with a [conventional prefix](commit-guidelines.md) (`feat/`, `fix/`, etc.)
2. Run `just ci` and ensure all checks pass
3. Open a PR against `main` with a clear description of what changed and why
4. Keep changes small and focused — large PRs are hard to review

## Architecture

Before making structural changes, read [Architecture Guide](architecture-guide.md) to understand the key design invariants (SQLite + WAL, lifecycle service as single orchestrator, MCP pooling, runtime provider seam).

!!! note "Scope"
    Shoal is intentionally optimized for a personal stack: Fish + tmux + macOS. Changes that add Linux/Windows compatibility without breaking the primary stack are welcome; changes that make the primary stack worse are not.
