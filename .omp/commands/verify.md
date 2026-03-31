---
description: Run the full shoal CI pipeline or targeted checks (lint, typecheck, test, fish-check, coverage).
---

Run the CI pipeline and report results clearly.

## Default: full pipeline

```bash
just ci
```

This runs: lint → typecheck → test → fish-check → security.

## Targeted runs

If the user specifies a specific check, run only that:

| Argument | Command |
|----------|---------|
| `lint` | `just lint` |
| `typecheck` or `types` | `just typecheck` |
| `test` | `just test` |
| `test-all` | `just test-all` |
| `fish` | `just fish-check` |
| `cov` or `coverage` | `just cov` |
| `fmt` | `just fmt-check` |
| (empty or `all`) | `just ci` |

## Reporting

- If all steps pass, report success with a one-line summary including pass count.
- If any step fails, show the specific errors and suggest fixes.
- For lint/type failures, include `file:line` references.
