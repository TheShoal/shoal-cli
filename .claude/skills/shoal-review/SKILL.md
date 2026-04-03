---
name: shoal-review
description: Review staged or recent changes following shoal-cli review doctrine. Ordered by risk tier — behavioral regressions first, style last.
allowed-tools: Read, Glob, Grep, Bash
---

# Shoal Code Review

Review the current diff for quality issues ordered by risk tier.

## Steps

1. Establish scope:
   - `git diff --staged --stat` (if something is staged)
   - or `git log --oneline -5 origin/main..HEAD` (for a branch review)
   - or `git diff origin/main...HEAD --stat` (full branch diff)

2. For each changed file, read it and check the following (in priority order):

   **Tier 1 — Behavioral regressions**
   - Async invariants: blocking calls in async context without `asyncio.to_thread()`
   - Lifecycle delegation: CLI/API bypassing `services/lifecycle.py`
   - Status detection: regex patterns changed or `status_provider` overridden incorrectly
   - SQLite invariants: concurrent writes without `asyncio.Lock`, WAL mode assumptions

   **Tier 2 — Config/deployment risk**
   - Config model changes: `extra="forbid"` maintained? New optional extras correctly gated?
   - New MCP tools: added to `tour.py` tool count? Docstring present (becomes tool description)?
   - New CLI commands: registered in `cli/__init__.py`? Help text correct?

   **Tier 3 — Test coverage**
   - New public functions without tests
   - Async tests using `@pytest.mark.asyncio`
   - External deps (tmux, git, DB) mocked in unit tests

   **Tier 4 — Contract drift**
   - Does the change break invariants documented in `ARCHITECTURE.md`?
   - Does `CHANGELOG.md` or `ROADMAP.md` need updating?

   **Tier 5 — Type safety**
   - Missing type hints on function signatures
   - `Any` usage without justification
   - `mypy --strict` violations

3. Run `just lint` and `just typecheck` — include any failures in the findings.

4. Output findings grouped by severity:
   - **Critical**: must fix before merge (Tier 1 regressions, mypy errors)
   - **Important**: creates tech debt if skipped (missing tests, Tier 2/3 issues)
   - **Nice-to-have**: cleanup (Tier 4/5 improvements)

## Review priority order

1. Behavioral regressions
2. Configuration and deployment risk
3. Test coverage gaps
4. Contract drift against docs/ARCHITECTURE.md
5. Hidden coupling and rollback difficulty
6. Style — never outranks correctness risk

## Output format

```
## Review: <branch or commit range>

### Critical
- file.py:L42 — async I/O without to_thread()

### Important
- tests/test_x.py missing — no coverage for new `foo()` function

### Nice-to-have
- core/bar.py — unused import

### CI
lint: PASS | typecheck: PASS | (or paste failures)
```
