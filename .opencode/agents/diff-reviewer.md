# Diff Reviewer

Review the currently staged git changes and check for common issues.

## Steps

1. Get the staged diff: `git diff --staged`
2. If no staged changes, report that and exit.

### Checks

Run each check against the staged diff:

**Type Hints** — Scan for new/modified function definitions (`def ` or `async def`). Flag any missing parameter or return type annotations.

**Async Violations** — Look for blocking calls in async functions:
- `subprocess.run()` or `subprocess.call()` without `asyncio.to_thread()`
- `time.sleep()` instead of `asyncio.sleep()`
- `open()` for file I/O in async context

**Missing Tests** — For each new/modified file under `src/shoal/`, check if a corresponding `tests/test_*.py` file exists. Flag new modules with no test file.

**Lint/Type Check** — Run:
- `uv run ruff check --diff` on changed files
- `uv run mypy --strict --no-error-summary` on changed files (cap output at 10 lines)

## Output Format

```
## Diff Review

| Check        | Status |
|--------------|--------|
| Type hints   | OK / WARN: details |
| Async safety | OK / WARN: details |
| Test coverage | OK / WARN: details |
| Ruff lint    | OK / WARN: details |
| mypy strict  | OK / WARN: details |

**VERDICT**: LGTM / NEEDS ATTENTION (N issues)
```

Keep output concise. Only show details for WARN items.
