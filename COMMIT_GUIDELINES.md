# Commit Message Guidelines

Shoal follows the [Conventional Commits](https://www.conventionalcommits.org/) specification for all commit messages.

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Type

Must be one of the following:

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that don't affect code meaning (whitespace, formatting, etc.)
- **refactor**: Code change that neither fixes a bug nor adds a feature
- **perf**: Performance improvement
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to build process, dependencies, or auxiliary tools

### Scope

Optional. Narrows the area of change. Keep it short and lowercase.

Common scopes: `session`, `mcp`, `cli`, `api`, `fish`, `db`, `config`, `status`

Omit scope when a change touches too many areas to name one meaningfully.

### Description

- Use imperative, present tense: "change" not "changed" nor "changes"
- Don't capitalize first letter
- No period (.) at the end
- Keep it concise (50 characters or less)

### Body (Optional)

- Use bullets (- or •) for multiple changes
- Wrap at 72 characters
- Explain **what** and **why**, not **how**
- Separate from description with a blank line

### Footer (Optional)

- Reference issues: `Fixes #123`, `Closes #456`
- Breaking changes: `BREAKING CHANGE: description`

## Examples

### Good Commits

```
feat(session): add name validation at all entry points

- Validate session names in SessionState and SessionCreate models
- Add validation to update_session() when name parameter provided
- Implement PUT /sessions/{id}/rename endpoint with full validation
- Apply validation at CLI (new/fork/rename) and API (POST/PUT) entry points
```

```
fix(mcp): prevent N+1 query in MCP listing

Use single list_sessions() call instead of fetching sessions individually
for each MCP server, reducing database queries from O(n) to O(1).
```

```
test(status): expand status bar test coverage

- Add test for multiple mixed statuses
- Verify stopped and unknown sessions excluded from display
- Confirm Unicode icons render correctly in output
```

```
docs(readme): refresh README with improved layout

- Reorganize sections for better flow
- Add examples for common workflows
- Clarify flag descriptions for ambiguous options
```

```
chore(deps): bump version to 0.4.4
```

### Bad Commits

```
❌ Updated some files
❌ Fix bug
❌ WIP
❌ feat: Added a new feature that validates session names and also fixes some bugs with the MCP listing and updates the README
❌ Fixed the thing that was broken yesterday
```

## Tools & Automation

### Git Commit Template

A commit message template is available in `.gitmessage`. Configure git to use it:

```bash
git config commit.template .gitmessage
```

### OpenCode Skill

The `git-commit-messages` skill automatically applies these guidelines when creating commits through OpenCode. It ensures:

- Proper conventional commit format
- Concise, executive-focused messages
- No excessive numbers or self-congratulation
- Appropriate type selection based on changes

### Validation

We recommend using [commitlint](https://commitlint.js.org/) to validate commit messages in CI/CD:

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional
```

## Why Conventional Commits?

1. **Automated Changelogs**: Generate release notes automatically
2. **Semantic Versioning**: Determine version bumps from commit history
3. **Better Git History**: Easier to understand project evolution
4. **Clearer Communication**: Standardized format improves team coordination
5. **Tooling Support**: Many tools integrate with conventional commits

## References

- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [Angular Commit Guidelines](https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit)
- [Commitizen](https://github.com/commitizen/cz-cli) - Interactive commit tool
