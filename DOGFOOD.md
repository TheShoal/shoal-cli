# Shoal Dogfood Run

You are a developer using Shoal to manage AI coding sessions. Your job is to exercise every major feature of Shoal and ruthlessly document every friction point, error, unexpected behavior, or confusing output you encounter.

## Your mission

Work through the checklist below IN ORDER. For each step, run the command, observe the output, and record findings in a structured log. Do not skip steps. Do not smooth over problems — every failure, confusing message, slow operation, or missing feedback is a finding.

## Environment
- Repo: /Users/ricardoroche/sanctum/opus/proprium/the-shoal/shoal-cli
- You have access to shoal-orchestrator MCP tools

## Checklist

### 1. Init & config
```
shoal init --refresh-tools
shoal config show
shoal template ls
shoal template show pi-dev
```
Record: Does --refresh-tools print useful output? Does config show miss anything important? Are template names/descriptions clear?

### 2. Create a real worker session
Use MCP: create_session with:
- name: dogfood-worker
- template: pi-dev
- tool: omp
- path: /Users/ricardoroche/sanctum/opus/proprium/the-shoal/shoal-cli
- worktree: feat/dogfood-test
- branch: true
- prompt: "Read src/shoal/core/config.py and write a one-paragraph summary of what it does. Then stop."

Record: Did the session start cleanly? Did omp launch automatically? Any startup errors?

### 3. List and inspect
```
shoal ls
shoal status
shoal info dogfood-worker
```
Record: Is the output readable? Are statuses accurate? Does info show everything you'd want?

### 4. Monitor the worker
Use capture_pane to watch it work. Wait for it to finish (go idle).
Record: How long did status detection take to update? Were statuses accurate during the run?

### 5. History and journal
```
shoal history dogfood-worker
shoal journal dogfood-worker
```
Record: Are entries present? Is the format useful? Any missing entries?

### 6. Send keys
```
shoal send dogfood-worker "git status"
```
Wait a moment, then capture_pane to see if it worked.
Record: Did it work? Any delay? Feedback to the user?

### 7. Fork
```
shoal fork dogfood-worker dogfood-fork
```
Then: `shoal ls` to confirm both sessions exist.
Record: Did fork work cleanly? Did the fork inherit the worktree/branch state?

### 8. Fin commands
```
shoal fin ls
shoal fin ls --path .
```
Record: Does fin ls (no path) show the right message? Is the output format clear?

### 9. Worktree commands
```
shoal wt ls
shoal wt prune
```
Record: Does wt ls show both worktrees? Is output format useful?

### 10. Diagnostics
```
shoal diag
shoal check
```
Record: Any false positives? Missing checks? Confusing output?

### 11. MCP
```
shoal mcp ls
```
Record: What's running? Anything unexpected?

### 12. Kill with auto-commit
First, enable auto_commit in the config temporarily if possible (or note that it can't be tested without editing config.toml).
Then:
```
shoal kill dogfood-worker
shoal kill dogfood-fork
```
Record: Did kill give clear feedback? Was DirtyWorktreeError triggered? Was auto-commit attempted? Did worktree cleanup work?

### 13. Post-kill state
```
shoal ls
shoal wt ls
```
Record: Is the state clean? Any orphans?

## Output format

After completing the checklist, produce a structured findings report:

```
## Dogfood Findings

### Critical (blocks workflow)
- [C1] <description> — <command that triggered it> — <exact error or behavior>

### Friction (slows or confuses)
- [F1] <description> — <command> — <what happened vs what should have happened>

### Polish (minor, low priority)
- [P1] <description>

### Works well (worth preserving)
- [W1] <description>
```

Be specific. "shoal ls output is confusing" is not a finding. "shoal ls shows session ID truncated to 8 chars but shoal kill requires the full ID" is a finding.
