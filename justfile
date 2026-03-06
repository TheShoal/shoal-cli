# Default: run all checks (same as CI)
default: ci

# Install project in editable mode with dev deps
install:
    uv pip install -e ".[dev]"

# Lint with ruff
lint:
    uv run ruff check .

# Auto-format with ruff
fmt:
    uv run ruff format .

# Type check with mypy
typecheck:
    uv run mypy src/

# Run tests (exclude integration)
test:
    uv run pytest -n auto -m "not integration"

# Run all tests including integration
test-all:
    uv run pytest -n auto

# Security scan with Bandit
security:
    uv run --with bandit bandit -r src/shoal/ -c pyproject.toml -ll

# Run all CI checks sequentially
ci: lint typecheck test fish-check security

# Validate fish template syntax
fish-check:
    fish -n src/shoal/integrations/fish/templates/*.fish

# Check formatting without modifying (for CI)
fmt-check:
    uv run ruff format --check .

# Run tests with coverage report
cov:
    uv run pytest --cov --cov-report=term-missing -m "not integration"

# Serve documentation site locally
docs-serve:
    uv run --extra docs mkdocs serve

# Build documentation site (fails on warnings)
docs-build:
    uv run --extra docs mkdocs build --strict

# Install pre-commit hooks
setup:
    pre-commit install
    pre-commit install --hook-type commit-msg

# Release a new version: just release 0.11.0
release version:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "$(git status --porcelain)" ]]; then
        echo "Error: working tree is dirty" >&2; exit 1
    fi
    current=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
    echo "Bumping version: $current → {{version}}"
    sed -i "s/^version = \"$current\"/version = \"{{version}}\"/" pyproject.toml
    git add pyproject.toml
    git commit -m "chore: bump version to {{version}}"
    git tag -a "v{{version}}" -m "Release v{{version}}"
    echo "Tagged v{{version}}. Push with: git push && git push --tags"
