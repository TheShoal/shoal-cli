---
name: shoal-arch-check
description: Validate Shoal's architectural invariants — async correctness, lifecycle delegation, module boundaries, detection patterns, and more. Use when refactoring or before major changes to catch structural violations.
argument-hint: [all|async|lifecycle|boundaries|detection|db|mcp]
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Shoal Architecture Checker

Validate that the codebase adheres to Shoal's documented architectural invariants. These are the rules from ARCHITECTURE.md and CLAUDE.md that linters can't catch.

## Target Selection

`$ARGUMENTS` selects which checks to run. Default is `all`.

- `all` — Run every check below
- `async` — Async correctness only
- `lifecycle` — Lifecycle delegation only
- `boundaries` — Module boundary enforcement only
- `detection` — Status detection pattern validation only
- `db` — Database usage patterns only
- `mcp` — MCP pool/proxy patterns only

## Checks

### 1. Async Correctness (`async`)

The project mandates: "All I/O operations use async/await. Blocking subprocess calls in async contexts MUST use asyncio.to_thread()."

Scan for violations:

1. **Blocking subprocess in async functions**: Search for `subprocess.run`, `subprocess.call`, `subprocess.check_output`, `subprocess.Popen` inside `async def` functions. These must use `asyncio.to_thread()`.
   ```
   Grep for: subprocess\.(run|call|check_output|Popen) in src/shoal/
   Then check if the calling function is async
   ```

2. **Blocking sleep**: Search for `time.sleep()` in async functions (should be `asyncio.sleep()`).

3. **Blocking file I/O**: Search for `open()` in async functions that aren't wrapped in `asyncio.to_thread()`. Acceptable in sync CLI wrappers.

4. **Missing async wrappers**: Check that `core/tmux.py` and `core/git.py` sync functions have corresponding `async_*` wrappers used in `services/` and `api/`.

### 2. Lifecycle Delegation (`lifecycle`)

The invariant: "services/lifecycle.py is the single orchestrator for create/fork/kill/reconcile — both CLI and API delegate to it."

1. **CLI delegation**: Verify that `cli/session_create.py` calls `create_session_lifecycle()`, `fork_session_lifecycle()`, `kill_session_lifecycle()` — not raw tmux/git/DB operations directly.

2. **API delegation**: Verify that `api/server.py` calls lifecycle functions — not raw state/tmux operations.

3. **No duplicate orchestration**: Search for `tmux.new_session` or `git.worktree_add` outside of `services/lifecycle.py`. Flag any direct calls from CLI or API layers.

4. **Rollback coverage**: Verify that `_rollback` or `_rollback_async` is called in every `except` block within lifecycle functions.

### 3. Module Boundaries (`boundaries`)

Enforce the layered architecture: CLI/API → Services → Core → Models.

1. **Models import nothing from shoal**: `src/shoal/models/` should only import from stdlib, pydantic, and other models. Flag any import from `shoal.core`, `shoal.services`, or `shoal.cli`.

2. **Core doesn't import services**: `src/shoal/core/` should not import from `shoal.services` or `shoal.cli`.

3. **CLI/API use services, not core directly for orchestration**: `cli/session_create.py` and `api/server.py` should call lifecycle functions, not raw `core/state.py` CRUD for session creation/deletion (reading is fine).

4. **No circular imports**: Check that there are no import cycles between modules.

### 4. Status Detection Patterns (`detection`)

Validate the detection system integrity:

1. **Tool config completeness**: For each `.toml` file in tool configs, verify it has `[detection]` section with `busy_patterns`, `waiting_patterns`, `error_patterns`, `idle_patterns`.

2. **Regex validity**: Attempt to compile every pattern in detection configs. Flag invalid regex.

3. **Pane title convention**: Grep for tmux pane title usage — should always use `shoal:<session_id>` format.

4. **Watcher targeting**: Verify `services/watcher.py` targets panes by title, not by index or position.

### 5. Database Patterns (`db`)

Validate SQLite + WAL usage:

1. **Single connection**: Verify `core/db.py` uses singleton pattern (`get_instance()`). No other module should create raw `aiosqlite.connect()` calls.

2. **WAL mode**: Verify WAL is enabled at connection time.

3. **Context manager usage**: Check that all DB operations use `async with get_db() as db:` pattern or `with_db()` wrapper.

4. **Lock on writes**: Verify `asyncio.Lock` is used for `update_session` and other write operations.

5. **No raw SQL outside db/state**: Flag any `db.execute()` calls outside `core/db.py` and `core/state.py`.

### 6. MCP Pool Patterns (`mcp`)

Validate MCP orchestration:

1. **Name validation**: Verify `validate_mcp_name()` is called at every entry point (CLI, API, pool, proxy).

2. **Socket path consistency**: All MCP socket paths should use the same `state_dir() / "mcp-pool" / "sockets"` pattern.

3. **No socat dependency**: Verify no references to `socat` in production code (benchmarks/docs are OK).

4. **Proxy uses asyncio**: Verify `mcp_proxy.py` uses pure asyncio (no subprocess socat).

## Output Format

```
## Architecture Check: <target>

| Invariant | Status | Details |
|-----------|--------|---------|
| Async correctness | PASS/FAIL | N violations found |
| Lifecycle delegation | PASS/FAIL | ... |
| Module boundaries | PASS/FAIL | ... |
| Detection patterns | PASS/FAIL | ... |
| Database patterns | PASS/FAIL | ... |
| MCP patterns | PASS/FAIL | ... |

### Violations (if any)
- **[category]** file.py:123 — description of violation
```

Keep output focused on violations. Don't list passing checks in detail.
