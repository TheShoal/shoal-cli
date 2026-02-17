# Contributing to Shoal

Shoal is an internal US Mobile tool. Contributions are welcome from all employees and contractors!

## Development Setup

We use `uv` for dependency management.

```bash
# Clone and install in editable mode
git clone git@github.com:usmobile/shoal.git
cd shoal
uv pip install -e ".[dev]"
```

## Standards

### Code Style
We use `ruff` for linting and formatting. Please run it before submitting changes:

```bash
ruff check .
ruff format .
```

### Type Checking
We use `mypy` for static type analysis:

```bash
mypy src/
```

### Testing
All new features should include tests. Run the test suite with:

```bash
pytest
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

We follow [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages.

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
