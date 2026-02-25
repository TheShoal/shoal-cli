---
name: shoal-deps
description: Audit Shoal's dependencies — check for updates, validate optional dependency boundaries, find unused imports, and verify security. Use for dependency hygiene before releases or periodically.
argument-hint: [audit|updates|unused|boundaries|security]
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Shoal Dependency Auditor

Comprehensive dependency analysis for the Shoal project.

## Subcommands

### `audit` (default) — Full Dependency Audit

Run all checks below and produce a combined report.

### `updates` — Check for Available Updates

1. Read `pyproject.toml` to get all declared dependencies with version constraints
2. For each dependency, check the installed version: `uv pip show <package> 2>/dev/null | grep Version`
3. Check for newer versions: `uv pip index versions <package> 2>/dev/null | head -3`
4. Categorize updates:
   - **Patch**: Safe to update (bug fixes)
   - **Minor**: Review changelog (new features)
   - **Major**: Breaking changes — needs investigation
5. Present a table:

```
| Package | Current | Latest | Update Type | Notes |
|---------|---------|--------|-------------|-------|
| pydantic | 2.10.0 | 2.11.0 | Minor | Check migration guide |
| fastapi | 0.109.0 | 0.115.0 | Minor | New features |
```

### `unused` — Find Unused Dependencies

1. Read all declared dependencies from `pyproject.toml`
2. For each dependency, search for imports across `src/shoal/`:
   - Map package names to import names (e.g., `pydantic` → `pydantic`, `aiosqlite` → `aiosqlite`)
   - Check: `grep -r "import <name>\|from <name>" src/shoal/`
3. Flag any dependency that has zero imports (potential dead dependency)
4. Also check dev dependencies — some may only be used in tests or scripts

### `boundaries` — Validate Optional Dependency Boundaries

Shoal has optional dependencies (`[project.optional-dependencies]`). Validate:

1. **MCP boundary**: `fastmcp` imports must be guarded:
   - Search for `from fastmcp` or `import fastmcp` in `src/shoal/`
   - Each must be inside a `try/except ImportError` block OR in a module that's only loaded when `[mcp]` extra is installed
   - The only allowed unguarded imports are in `services/mcp_shoal_server.py` (the MCP server entry point)

2. **Dev dependency boundary**: Dev-only packages (`pytest`, `ruff`, `mypy`, `httpx`) must NEVER be imported in `src/shoal/` (production code)

3. **Stdlib preference**: Check for cases where stdlib could replace a dependency:
   - `tomllib` (stdlib 3.11+) vs `tomli`
   - `pathlib` vs `os.path`
   - `urllib.request` vs `httpx` for simple GET requests

### `security` — Security Audit

1. Run `uv pip audit` if available, or check for known vulnerabilities:
   - `uv run pip-audit` (if installed)
   - Or manually check: `uv pip list --format=json` and cross-reference
2. Check for pinning issues:
   - Are all deps pinned to at least a minimum version?
   - Any deps using `==` exact pins that should be `>=`?
3. Review `ruff` S rules output for security-relevant findings: `uv run ruff check src/ --select S`

### `tree` — Show Dependency Tree

1. `uv pip tree` or `uv run pip install pipdeptree && uv run pipdeptree`
2. Highlight the dependency tree depth (deep trees = fragile supply chain)
3. Flag any dependency that pulls in more than 5 transitive deps

## Output Format

```
## Dependency Audit Report

### Updates Available
| Package | Current | Latest | Risk |
|---------|---------|--------|------|
| ... | ... | ... | ... |

### Unused Dependencies
- <package> — not imported anywhere in src/

### Boundary Violations
- <file>:<line> — imports <package> without guard

### Security
- N known vulnerabilities found
- All deps have minimum version pins: YES/NO

**Summary**: N updates available, M unused deps, K boundary violations
```

## Rules

- Never auto-update dependencies — only report findings
- Always check both `[dependencies]` and `[optional-dependencies]`
- The `[dev]` group is only for development — verify it's not in the main deps
- Cross-reference with `uv.lock` if it exists for exact resolved versions
