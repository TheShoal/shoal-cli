# Verify — CI Pipeline Runner

Run the full CI pipeline and report results clearly.

## Steps

1. Run `just ci` from the project root (this runs: lint -> typecheck -> test -> fish-check)
2. If all steps pass, report success with a one-line summary
3. If any step fails, show the specific errors and suggest fixes

## Targeted Runs

If asked to run a specific check, use the corresponding command:

| Check | Command |
|-------|---------|
| lint | `just lint` |
| typecheck / types | `just typecheck` |
| test | `just test` |
| test-all | `just test-all` |
| fish | `just fish-check` |
| coverage | `just cov` |
| all (default) | `just ci` |
