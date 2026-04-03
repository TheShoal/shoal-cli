# Commit Guidelines

Shoal enforces [Conventional Commits](https://www.conventionalcommits.org/) via the `gitlint` pre-commit hook.

The full specification is in [COMMIT_GUIDELINES.md](https://github.com/TheShoal/shoal-cli/blob/main/COMMIT_GUIDELINES.md).

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Whitespace / formatting (no logic change) |
| `refactor` | Code restructure (no feature, no fix) |
| `perf` | Performance improvement |
| `test` | Add or correct tests |
| `chore` | Build, deps, auxiliary tools |

## Scopes (common)

`session`, `mcp`, `cli`, `api`, `fish`, `db`, `config`, `status`

Omit scope when a change touches too many areas.

## Description rules

- Imperative present tense: "add" not "added"
- No capital first letter
- No trailing period
- 50 characters or less

## Examples

```
feat(session): add name validation at all entry points
fix(mcp): prevent N+1 query in MCP listing
test(status): expand status bar test coverage
docs(readme): refresh README with improved layout
chore(deps): bump version to 0.38.0
```

## Validation

The `gitlint` hook runs on every `git commit`. To run manually:

```bash
gitlint --commits HEAD
```
