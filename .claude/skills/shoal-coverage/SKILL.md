---
name: shoal-coverage
description: Run tests with coverage and identify under-tested files. Use to check test coverage or find gaps.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Shoal Coverage Report

Run the test suite with coverage analysis and report gaps.

## Steps

1. Run coverage: `uv run pytest --cov=src/shoal --cov-report=term-missing -m "not integration" -q`
2. Parse the output:
   - Report overall coverage percentage
   - List files below 80% coverage, sorted worst-first
   - For each low-coverage file, show the missing line ranges
3. Cross-reference with recent changes: `git diff --name-only HEAD~5 -- src/shoal/`
   - Highlight recently-changed files that are below 80%
4. Summarize: total files, files below gate, recently-changed files at risk

## Targeted Mode

If `$ARGUMENTS` is provided, treat it as a file path or module name:
- `$ARGUMENTS` = "lifecycle" → `uv run pytest --cov=src/shoal/services/lifecycle --cov-report=term-missing tests/test_lifecycle.py -q`
- `$ARGUMENTS` = path → run coverage for that specific file

## Output Format

```
## Coverage Report

**Overall**: XX% (gate: 80%)

### Files Below 80%
| File | Coverage | Missing Lines | Recently Changed? |
|------|----------|---------------|-------------------|
| ... | ... | ... | yes/no |

### Summary
- N files below 80% gate
- M of those were recently changed (last 5 commits)
```
