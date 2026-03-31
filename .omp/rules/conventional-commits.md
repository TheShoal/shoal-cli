---
description: Conventional commit format enforced by gitlint. All commits must follow this pattern.
---

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Type (required)

One of: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

## Scope (optional)

Common scopes: `session`, `mcp`, `cli`, `api`, `fish`, `db`, `config`, `status`, `lifecycle`, `fin`

Omit scope when a change touches too many areas to name one meaningfully.

## Description

- Imperative, present tense: "add" not "added" nor "adds"
- Lowercase first letter
- No period at the end
- 50 characters or less

## Body (optional)

- Bullets (`-`) for multiple changes
- Wrap at 72 characters
- Explain **what** and **why**, not how
- Separate from description with a blank line

## Footer (optional)

- `Fixes #123`, `Closes #456`
- `BREAKING CHANGE: description`

## Examples

```
feat(session): add name validation at all entry points
fix(mcp): prevent N+1 query in MCP listing
test(status): expand status bar test coverage
chore(deps): bump version to 0.4.4
```

Full spec: see `COMMIT_GUIDELINES.md` at the repo root.
