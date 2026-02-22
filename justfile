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
    uv run pytest -m "not integration"

# Run all tests including integration
test-all:
    uv run pytest

# Run all CI checks sequentially
ci: lint typecheck test fish-check

# Validate fish template syntax
fish-check:
    fish -n src/shoal/integrations/fish/templates/*.fish

# Check formatting without modifying (for CI)
fmt-check:
    uv run ruff format --check .

# Run tests with coverage report
cov:
    uv run pytest --cov --cov-report=term-missing -m "not integration"

# Install pre-commit hooks
setup:
    pre-commit install
    pre-commit install --hook-type commit-msg
