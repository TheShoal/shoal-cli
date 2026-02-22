---
name: shoal-verify
description: Run the full shoal CI pipeline (lint, typecheck, test, fish-check). Use after making code changes to verify everything passes.
disable-model-invocation: true
allowed-tools: Bash, Read
---

# Verify Shoal CI Pipeline

Run the full CI pipeline and report results clearly.

## Steps

1. Run `just ci` from the project root (this runs: lint → typecheck → test → fish-check)
2. If all steps pass, report success with a one-line summary
3. If any step fails, show the specific errors and suggest fixes

If `$ARGUMENTS` contains a specific check name (lint, typecheck, test, fish-check), run only that check instead of the full pipeline.

## Targeted runs

- `$ARGUMENTS` = "lint" → `just lint`
- `$ARGUMENTS` = "typecheck" or "types" → `just typecheck`
- `$ARGUMENTS` = "test" → `just test`
- `$ARGUMENTS` = "test-all" → `just test-all`
- `$ARGUMENTS` = "fish" → `just fish-check`
- `$ARGUMENTS` = "cov" or "coverage" → `just cov`
- Empty or "all" → `just ci`
