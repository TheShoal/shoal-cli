---
name: shoal-verify
description: Run the full shoal CI pipeline (lint, typecheck, test, fish-check). Use after making code changes to verify everything passes.
---

# Verify Shoal CI Pipeline

Run the full CI pipeline and report results clearly.

## Steps

1. Run `just ci` from the project root (this runs: lint → typecheck → test → fish-check → security)
2. If all steps pass, report success with a one-line summary
3. If any step fails, show the specific errors and suggest fixes

If the user specifies a specific check, run only that check instead of the full pipeline.

## Targeted runs

- `lint` → `just lint`
- `typecheck` or `types` → `just typecheck`
- `test` → `just test`
- `test-all` → `just test-all`
- `fish` → `just fish-check`
- `cov` or `coverage` → `just cov`
- `fmt` → `just fmt-check`
- Empty or `all` → `just ci`

## Doc-only changes

For changes that only touch `.md`, `.yml`, or docs files, run `just docs-lint && just docs-build` instead of the full pipeline.
