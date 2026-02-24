---
name: shoal-parallel
description: Orchestrate parallel Shoal sessions to work on independent parts of a feature. Use when a task has multiple independent workstreams that can be developed concurrently. This is the ultimate dogfooding skill — using Shoal to build Shoal.
argument-hint: [plan|launch|status|collect]
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Parallel Development with Shoal Sessions

Use Shoal's own orchestration to parallelize development work on the Shoal codebase. This is the meta skill — building the tool with the tool.

## Subcommands

Parse `$ARGUMENTS` for the operation:

### `plan <feature>` — Decompose a Feature into Parallel Workstreams

1. Analyze the feature request and identify **independent** workstreams that can be developed in parallel
2. For each workstream, determine:
   - Which files will be modified (check for overlaps — overlapping files = serial, not parallel)
   - What tests need to be written
   - What the acceptance criteria are
3. Present a parallel work plan:

```
## Parallel Work Plan: <feature>

### Session 1: <workstream-name>
- Branch: feat/<feature>-<part>
- Files: src/shoal/core/new_module.py, tests/test_new_module.py
- Goal: <one-line description>

### Session 2: <workstream-name>
- Branch: feat/<feature>-<part>
- Files: src/shoal/cli/new_command.py, tests/test_cli_new.py
- Goal: <one-line description>

### Integration (serial, after parallel work)
- Merge branches, resolve any interface mismatches
- Run full CI: `just ci`
```

4. Ask the user to confirm or adjust the plan before launching.

### `launch` — Create Shoal Sessions for Each Workstream

For each workstream in the plan:

1. Create a Shoal session using the MCP tools:
   ```
   Use mcp__shoal-orchestrator__create_session with:
   - name: shoal-<workstream>
   - path: /srv/dev/.shoal
   - worktree: feat/<feature>-<part>
   - branch: true
   ```

2. Send initial instructions to each session via `mcp__shoal-orchestrator__send_keys`:
   - The specific task for that workstream
   - Files to modify
   - Acceptance criteria
   - Reminder to run tests when done

3. Journal the work plan in each session:
   ```
   Use mcp__shoal-orchestrator__append_journal with the workstream details
   ```

4. Report the launched sessions with their names and branches.

### `status` — Check Progress of Parallel Sessions

1. Use `mcp__shoal-orchestrator__list_sessions` to get all active sessions
2. Filter for sessions matching the current feature prefix
3. For each session:
   - Use `mcp__shoal-orchestrator__session_info` for status
   - Use `mcp__shoal-orchestrator__read_journal` for progress notes
4. Present a status dashboard:

```
## Parallel Status: <feature>

| Session | Status | Branch | Last Journal |
|---------|--------|--------|-------------|
| shoal-core | Thinking | feat/x-core | "Implementing base class" |
| shoal-cli | Waiting | feat/x-cli | "CLI done, running tests" |
```

### `collect` — Merge Parallel Work Back Together

1. Check all parallel sessions are done (status = idle or waiting)
2. For each session's branch:
   - `git log main..<branch> --oneline` to see what was done
   - Check for conflicts with other branches
3. Suggest a merge order (least dependencies first)
4. For each branch:
   - `git merge <branch>` into the working branch
   - Run `just ci` after each merge to catch issues early
5. Kill the parallel sessions after successful merge
6. Report the combined result

### Default (no subcommand)

If `$ARGUMENTS` is empty, show usage:

```
## Parallel Development

Usage: /shoal-parallel <subcommand>

  plan <feature>   Decompose a feature into parallel workstreams
  launch           Create Shoal sessions from the plan
  status           Check progress of parallel sessions
  collect          Merge parallel work back together

This skill uses Shoal to build Shoal — the ultimate dogfooding loop.
```

## Guidelines

- **Never parallelize overlapping files** — if two workstreams touch the same file, they must be serial
- **Always use worktrees** — each session gets its own git worktree for isolation
- **Journal everything** — each session should journal its progress for visibility
- **Test before merging** — each branch must pass `just ci` independently
- **Prefer 2-3 sessions** — more than 4 parallel sessions becomes hard to coordinate
- **Name sessions clearly** — `shoal-<feature>-<part>` naming convention
