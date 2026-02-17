## Context

Shoal v0.5.0 wraps tmux and git via synchronous `subprocess.run` calls with no timeout protection. The watcher daemon runs an unguarded poll loop. The API server binds to all interfaces. The fish integration lacks interactive guards. These issues were identified in a comprehensive code review and are all straightforward to fix with minimal architectural changes.

The codebase has a clean separation: `core/tmux.py` and `core/git.py` provide subprocess wrappers, `services/watcher.py` runs the poll daemon, `api/server.py` hosts the FastAPI app, and `integrations/fish/templates/` contains the shell scripts. Each fix is localized to its module.

## Goals / Non-Goals

**Goals:**
- Prevent indefinite hangs from subprocess calls by adding timeouts
- Make the watcher daemon resilient to transient errors
- Eliminate orphaned DB records when tmux operations fail during fork
- Prevent tmux session name collisions from lossy sanitization
- Harden WebSocket connection management against disconnection errors
- Restrict API network exposure to localhost by default
- Fix fish shell integration correctness and performance issues
- Improve CI security and add fish template validation

**Non-Goals:**
- Async subprocess wrappers (P2 — requires `asyncio.to_thread` migration)
- Atomic DB updates / eliminating read-modify-write races (P1 — requires schema changes)
- Token-based API authentication (proper auth is a separate change)
- Consolidating CLI/API session creation into a shared service (P2 refactor)
- Adding a `ShoalError` exception hierarchy (P2 refactor)
- XDG support for fish installer (P1)

## Decisions

### D1: Timeout values — 30s default, 120s for git push

`tmux._run()` and `git._run()` get a `timeout` parameter defaulting to 30 seconds. `git.push()` overrides with `timeout=120` since pushes to remote can legitimately take longer.

**Why 30s:** Tmux commands and local git operations complete in under 1s. A 30s timeout catches hangs (credential prompts, unresponsive server) without false positives. The review suggested this exact value.

**Alternative considered:** Per-command timeout configuration via TOML. Rejected — adds complexity for no real user need at this stage.

### D2: Watcher error handling — log and continue, no backoff

Wrap `_poll_cycle()` in a bare `except Exception` with `logger.exception()`. No exponential backoff or circuit breaker.

**Why no backoff:** The watcher already sleeps `poll_interval` (5s) between cycles. If errors are transient (DB locked momentarily), the next cycle will succeed. If errors are persistent (DB corrupted), the logs will show repeated failures for diagnosis. Adding backoff increases complexity without clear benefit for a single-user tool.

### D3: ConnectionManager — set instead of list, per-connection error handling

Replace `list[WebSocket]` with `set[WebSocket]` and use `discard()` instead of `remove()`. In `broadcast()`, catch exceptions per-connection and remove broken connections.

**Why set:** `discard()` is idempotent (no `ValueError` if absent), which eliminates the crash path. Lookup is O(1). WebSocket objects are hashable.

### D4: Tmux collision detection — check before create, fail loudly

Before `tmux.new_session()`, call `tmux.has_session()` with the sanitized name. If a collision is detected, raise a `ValueError` with a message explaining which different session names mapped to the same tmux name.

**Why fail instead of auto-resolve:** Auto-appending suffixes (e.g., `shoal_foo-bar-2`) would create confusing tmux session names that don't match the Shoal session name. Failing loudly forces the user to choose a distinct name.

**Where to add the check:** In `core/state.py`'s `create_session()` function, which is the shared path for both CLI and API session creation.

### D5: Fork cleanup — mirror _add_impl's try/except pattern

Wrap `tmux.new_session()` in `_fork_impl` with the same try/except/cleanup pattern used in `_add_impl`. On failure, call `delete_session()` to remove the orphaned DB record.

### D6: API bind address — 127.0.0.1 default, configurable

Change the default `host` from `0.0.0.0` to `127.0.0.1` in both `server.py` and `cli/__init__.py`. Users who need network access can pass `--host 0.0.0.0` explicitly.

### D7: Fish fixes — minimal, targeted changes

- Add `status is-interactive; or return` as line 1 of `bootstrap.fish`
- Change `set -U __shoal_last_session` to `set -g __shoal_last_session`
- In `quick-attach.fish`, change `--preview="shoal info {}"` to `--preview='shoal info -- {}'`
- Add `--` before `$session` in the attach call

### D8: CI — official action + fish syntax check

Replace `curl -LsSf https://astral.sh/uv/install.sh | sh` with `uses: astral-sh/setup-uv@v5`. Add a step that runs `fish -n` on all `.fish` template files (conditional on fish being available, or install fish in CI).

## Risks / Trade-offs

- **[Timeout false positives]** A 30s timeout could theoretically trigger on a very slow machine or overloaded CI. → Mitigation: 30s is extremely generous for local operations; `git.push` gets 120s.
- **[Bare except in watcher]** Catching `Exception` could mask serious bugs (e.g., `SystemExit`). → Mitigation: Use `logger.exception()` which logs the full traceback; only catch `Exception`, not `BaseException`.
- **[set ordering for ConnectionManager]** Sets are unordered, so broadcast order is nondeterministic. → Mitigation: Broadcast order doesn't matter for WebSocket notifications.
- **[fish -n in CI requires fish installed]** Ubuntu runners don't have fish by default. → Mitigation: Add `apt-get install -y fish` step, or make the step conditional.
- **[API bind change may break existing setups]** Users who rely on remote API access will need to pass `--host 0.0.0.0`. → Mitigation: This is pre-v1.0 and the feature was never documented as network-accessible.
