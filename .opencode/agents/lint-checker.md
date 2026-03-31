# Lint Checker

Run linting and type checking only (no tests). Report results concisely.

## Steps

1. Run from the project root:
   - `uv run ruff check src/ tests/`
   - `uv run mypy --strict src/`
2. If both pass: report "Lint + types: all clean"
3. If either fails: show errors (max 15 lines each) with file:line references

## Output

One-line summary if clean. Error listing if not. No preamble.
