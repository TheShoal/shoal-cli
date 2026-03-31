# Conventional Commits

All commits in this project MUST follow the Conventional Commits specification, enforced by gitlint.

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Type

Must be one of: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

## Scope

Optional. Common scopes: `session`, `mcp`, `cli`, `api`, `fish`, `db`, `config`, `status`

Omit scope when a change touches too many areas to name one meaningfully.

## Description

- Imperative, present tense: "change" not "changed" nor "changes"
- Don't capitalize first letter
- No period at the end
- Keep it concise (50 characters or less)

## Body

- Use bullets for multiple changes
- Wrap at 72 characters
- Explain what and why, not how

## Examples

Good:
```
feat(session): add name validation at all entry points
fix(mcp): prevent N+1 query in MCP listing
test(status): expand status bar test coverage
chore(deps): bump version to 0.4.4
```

Bad:
```
Updated some files
Fix bug
WIP
```
