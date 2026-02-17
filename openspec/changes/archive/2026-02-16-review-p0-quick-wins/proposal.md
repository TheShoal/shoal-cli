## Why

The v0.5.0 code review identified critical reliability and security gaps that must be addressed before sharing Shoal with other users. Subprocess calls can hang indefinitely, the watcher daemon crashes on any poll error, the API is network-accessible without authentication, and the fish shell integration has several correctness issues. These are all low-effort fixes with high impact on stability and safety.

## What Changes

- Add timeout parameters to all `subprocess.run` calls in `tmux._run()` and `git._run()`, with `TimeoutExpired` handling
- Wrap the watcher's `_poll_cycle()` in try/except so a single failure doesn't kill the daemon
- Add tmux session cleanup on fork failure (mirror the existing `_add_impl` error-handling pattern)
- Detect tmux name collisions from lossy sanitization before calling `tmux.new_session`
- Fix `ConnectionManager` to use a `set` for connections and handle per-connection broadcast errors
- Bind the API server to `127.0.0.1` instead of `0.0.0.0` by default
- Add `status is-interactive; or return` guard to `bootstrap.fish`
- Change `set -U` (universal/disk-write) to `set -g` (global/memory-only) in `bootstrap.fish`
- Replace `curl | sh` in CI with `astral-sh/setup-uv@v5` GitHub Action
- Remove unused imports (`Panel`, `Table`) from `installer.py`
- Add `fish -n` syntax validation step to CI
- Harden fzf preview in `quick-attach.fish` against shell injection

## Capabilities

### New Capabilities
- `subprocess-timeouts`: Add configurable timeouts to tmux and git subprocess wrappers with proper error handling
- `watcher-resilience`: Make the watcher poll loop fault-tolerant so it survives transient errors
- `session-lifecycle-safety`: Fix fork cleanup, detect tmux name collisions, and prevent orphaned DB records
- `connection-manager-fixes`: Harden WebSocket connection tracking and broadcast against disconnection errors
- `api-security-defaults`: Bind API to localhost by default to prevent network exposure
- `fish-integration-fixes`: Add interactive guard, fix universal variable performance issue, and harden fzf preview
- `ci-hardening`: Replace insecure `curl | sh`, remove unused imports, and add fish template syntax checks

### Modified Capabilities

## Impact

- **`src/shoal/core/tmux.py`**: `_run()` gains `timeout` parameter; callers must handle `subprocess.TimeoutExpired`
- **`src/shoal/core/git.py`**: `_run()` gains `timeout` parameter with longer default for `push()`
- **`src/shoal/services/watcher.py`**: Poll loop wrapped in try/except with logging
- **`src/shoal/cli/session.py`**: `_fork_impl` gets tmux failure cleanup; session creation checks for tmux name collisions
- **`src/shoal/api/server.py`**: `ConnectionManager` refactored; default bind address changed to `127.0.0.1`
- **`src/shoal/integrations/fish/templates/bootstrap.fish`**: Interactive guard added, `set -U` changed to `set -g`
- **`src/shoal/integrations/fish/templates/quick-attach.fish`**: fzf preview hardened with `--` and quoting
- **`src/shoal/integrations/fish/installer.py`**: Unused imports removed
- **`.github/workflows/ci.yml`**: `curl | sh` replaced with official action; fish syntax check step added
- **`src/shoal/core/state.py`**: Collision detection added to tmux name sanitization flow
