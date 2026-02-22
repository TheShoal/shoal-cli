# Contributing to Shoal

Shoal is a personal-first project. Contributions are welcome, but the default scope is the maintainer's workflow: fish + tmux + neovim + opencode.

## Scope and Compatibility

- Fish shell is the only actively supported shell integration right now.
- Claude and Gemini are supported as secondary tool profiles.
- Broad compatibility changes should be optional, isolated, and non-disruptive to default workflows.

## Development Setup

We use `uv` for dependency management.

```fish
# Clone and install in editable mode
git clone git@github.com:usm-ricardoroche/shoal.git
cd shoal
uv pip install -e ".[dev]"
```

### Quick Start

After installing, set up the local development hooks:

```bash
# Install pre-commit hooks (or: just setup)
pre-commit install
pre-commit install --hook-type commit-msg
```

A [`justfile`](justfile) provides all common dev commands. Run `just --list` to see them:

| Command | What it does |
|---------|-------------|
| `just ci` | Run all CI checks (lint, typecheck, test, fish-check) |
| `just lint` | Lint with ruff |
| `just fmt` | Auto-format with ruff |
| `just typecheck` | Type check with mypy |
| `just test` | Run tests (exclude integration) |
| `just test-all` | Run all tests including integration |
| `just cov` | Run tests with coverage report |
| `just fish-check` | Validate fish template syntax |
| `just setup` | Install pre-commit hooks |

## Standards

### Code Style
We use `ruff` for linting and formatting:

```bash
just lint
just fmt
```

### Type Checking
We use `mypy` for static type analysis:

```bash
just typecheck
```

### Testing
All new features should include tests. Run the test suite with:

```bash
just test
```

## Workflow

1.  **Branch**: Create a feature branch (or use `shoal add -w my-feature -b`!).
2.  **Commit**: Follow the [Conventional Commits](COMMIT_GUIDELINES.md) format:
    - `feat:` for new features
    - `fix:` for bug fixes
    - `docs:` for documentation changes
    - `test:` for test additions or corrections
    - `refactor:` for code restructuring
    - `chore:` for maintenance tasks
3.  **PR**: Open a PR to the `main` branch.
4.  **Review**: Ensure CI passes and wait for a review from a maintainer.

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages. Commit messages are validated by `gitlint` via pre-commit hooks.

**Format**: `<type>: <description>`

**Example**:
```
feat: add session name validation at all entry points

- Validate session names in models and API endpoints
- Add CLI validation for new/fork/rename commands
- Include comprehensive test coverage
```

See [COMMIT_GUIDELINES.md](COMMIT_GUIDELINES.md) for full details and examples.

## Release Process

For maintainers: see [RELEASE_PROCESS.md](RELEASE_PROCESS.md) for versioning and release workflow.
