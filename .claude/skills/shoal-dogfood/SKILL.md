---
name: shoal-dogfood
description: Test Shoal features by actually using them — create sessions, apply templates, exercise MCP tools, test the full lifecycle. The definitive integration validation that goes beyond unit tests. Use when you want to verify a feature works end-to-end, not just in isolation.
argument-hint: [feature-area]
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Dogfood Shoal Features

Test Shoal by using Shoal. This skill exercises real features through the actual tool — not mocked tests, but live validation. It uses the Shoal MCP tools available in this session to interact with Shoal as a real user would.

## Feature Areas

`$ARGUMENTS` selects what to dogfood. Default is a quick smoke test of core features.

### `sessions` — Session Lifecycle

Exercise the full session lifecycle via MCP tools:

1. **Create**: Use `mcp__shoal-orchestrator__create_session` to create a test session:
   - Name: `dogfood-test-<timestamp>`
   - Path: `/tmp/shoal-dogfood`
   - Worktree: optional (test both with and without)

2. **Verify**: Use `mcp__shoal-orchestrator__session_info` to confirm it was created correctly. Check all fields are populated.

3. **Interact**: Use `mcp__shoal-orchestrator__send_keys` to send a harmless command (`echo "dogfood test"`) to the session.

4. **Status**: Use `mcp__shoal-orchestrator__session_status` to verify aggregate counts updated.

5. **Journal**: Use `mcp__shoal-orchestrator__append_journal` to write a test entry, then `mcp__shoal-orchestrator__read_journal` to verify it.

6. **Cleanup**: Use `mcp__shoal-orchestrator__kill_session` to destroy the test session.

7. **Verify cleanup**: Confirm the session no longer appears in `mcp__shoal-orchestrator__list_sessions`.

Report each step as PASS/FAIL with timing.

### `mcp` — MCP Orchestration Tools

Exercise every MCP tool exposed by shoal-orchestrator:

1. Call each of the 8 tools with valid inputs
2. Call each with edge cases (empty strings, nonexistent sessions)
3. Verify return types match expected schemas
4. Time each call and flag anything over 2 seconds

### `templates` — Template System

Test template loading and validation:

1. Run `shoal template ls` (via Bash) and verify output includes expected templates
2. Run `shoal template show base-dev` and verify inheritance is displayed
3. Run `shoal template validate base-dev` for each available template
4. If there are project-local templates in `.shoal/templates/`, verify they shadow correctly
5. Test `shoal template mixins` lists available mixins

### `cli` — CLI Surface

Quick smoke test of read-only CLI commands:

1. `shoal --version` — verify version string
2. `shoal status` — verify output format
3. `shoal ls` — verify table renders
4. `shoal ls --format json` — verify valid JSON output
5. `shoal diag` — verify diagnostics run without error
6. `shoal mcp ls` — verify MCP listing
7. `shoal config show` — verify config introspection

Flag any command that exits non-zero or produces unexpected output.

### `detection` — Status Detection

Validate the detection system against real tool configs:

1. Read each tool config from `~/.config/shoal/tools/` or examples
2. For each tool, verify detection patterns compile as regex
3. Test patterns against known sample outputs:
   - Busy: spinner characters, "thinking", "generating"
   - Waiting: prompt characters, "Yes/No", "Allow"
   - Error: "Error:", "FAILED", traceback markers
   - Idle: clean prompt, `$`

### Default (no args) — Quick Smoke Test

Run a minimal end-to-end flow:

1. List current sessions (mcp tool)
2. Check aggregate status (mcp tool)
3. Run `shoal --version` (CLI)
4. Run `shoal diag` (CLI)
5. Report overall health

## Output Format

```
## Dogfood Report: <area>

| Test | Result | Time | Notes |
|------|--------|------|-------|
| Create session | PASS | 1.2s | ID: abc123 |
| Session info | PASS | 0.3s | All fields present |
| ... | ... | ... | ... |

**Summary**: N/M tests passed. <issues if any>
```

## Rules

- **Never leave test sessions running** — always clean up dogfood-test-* sessions
- **Use /tmp for test paths** — never create test artifacts in the real repo
- **Read-only for CLI tests** — only run commands that don't mutate state
- **Time everything** — slow operations are bugs worth reporting
- **Test error paths too** — try invalid inputs and verify graceful handling
