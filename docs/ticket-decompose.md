# Issue Decomposition

Break large Linear issues into trackable child sub-issues from the CLI.

## When to Use

**Ideal for:**
- Large epics or features that span multiple sessions
- Work that needs to be split across team members
- Projects requiring fine-grained progress tracking
- Stories that benefit from parallelization

**Not for:**
- Already-scoped single-session tickets
- Issues that are inherently atomic

## Command Usage

### Basic Decomposition

```bash
# Preview what would be created (dry-run mode)
shoal ticket decompose TEAM-123 --dry-run

# Create the child issues
shoal ticket decompose TEAM-123
```

### How It Works

1. **Fetch parent issue**: Pulls the Linear issue including title, description, labels
2. **Generate decomposition plan**: Creates a structured breakdown with:
   - Child issue titles
   - Descriptions with context
   - Shared labels from parent
   - Parent-child relationship tracking
3. **Create sub-issues**: Uses Linear API to create each child issue
4. **Link back to parent**: Establishes parent-child relationship in Linear

### Output

The command shows:

```
📦 Decomposing TEAM-123: "Build authentication system"

Dry run mode — no issues will be created.

Child issues that would be created:
  1. TEAM-XXX: Design auth data model
     Labels: backend, auth
  2. TEAM-XXX: Implement JWT token service
     Labels: backend, auth, security
  3. TEAM-XXX: Add login/logout endpoints
     Labels: backend, api
  4. TEAM-XXX: Add session middleware
     Labels: backend
  5. TEAM-XXX: Write integration tests
     Labels: backend, testing

Run without --dry-run to create these issues.
```

## Integration with Shoal Workflow

### Full Lifecycle

```bash
# 1. Decompose a large feature
shoal ticket decompose TEAM-123

# 2. Pick a child issue to work on
shoal ticket pick --team myteam

# 3. Start a session for that issue
shoal ticket start TEAM-124

# 4. Do the work...

# 5. Mark it done
shoal ticket done TEAM-124

# 6. Repeat for remaining children
```

### Multi-Agent Parallelization

```bash
# Decompose once
shoal ticket decompose TEAM-123

# Spawn parallel sessions for each child
shoal ticket start TEAM-124
shoal ticket start TEAM-125
shoal ticket start TEAM-126

# Each session works independently in its own worktree
shoal ls --tree
```

## Dry-Run Mode

Always preview before creating:

```bash
shoal ticket decompose TEAM-123 --dry-run
```

**What dry-run shows:**
- Number of child issues
- Proposed titles and descriptions
- Label inheritance
- Estimated complexity

**What dry-run does NOT do:**
- Create issues in Linear
- Modify the parent issue
- Consume API quota

## Error Handling

Common issues and resolutions:

| Error | Cause | Solution |
|-------|-------|----------|
| "Issue not found" | Invalid issue ID | Check the issue key format |
| "Team not configured" | Missing workspace.toml | Add team config |
| "Linear API error" | Rate limit / permissions | Wait or check API token |
| "No decomposition needed" | Issue already small | Skip decomposition |

## Best Practices

1. **Use dry-run first**: Always preview before creating
2. **Meaningful titles**: Ensure generated titles are specific
3. **Label inheritance**: Parent labels propagate to children
4. **Track in Linear**: Parent issue shows all children
5. **Session per child**: Use `shoal ticket start` for each child

## Configuration

No special configuration required — uses existing Linear integration from `~/.config/shoal/config.toml` and `.shoal/workspace.toml`.

## See Also

- [Linear and PM workflows](cli-reference.md#linear-and-pm-workflows) — Full ticket command reference
- [Team Doctrine](team-doctrine.md) — Multi-agent team patterns
- [Operator Playbooks](operator-playbooks.md) — Common workflows
