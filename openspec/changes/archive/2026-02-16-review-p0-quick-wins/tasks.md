## 1. Subprocess Timeouts

- [x] 1.1 Add `timeout` parameter (default 30s) to `tmux._run()` in `src/shoal/core/tmux.py`
- [x] 1.2 Add `timeout` parameter (default 30s) to `git._run()` in `src/shoal/core/git.py`
- [x] 1.3 Set `timeout=120` on `git.push()` call to `_run()`
- [x] 1.4 Handle `subprocess.TimeoutExpired` in `_run()` functions with clear error messages identifying the command and timeout value

## 2. Watcher Resilience

- [x] 2.1 Wrap `_poll_cycle()` call in `watcher.py` main loop with `try/except Exception`
- [x] 2.2 Log poll failures using `logger.exception()` for full traceback

## 3. Session Lifecycle Safety

- [x] 3.1 Add tmux name collision detection in `core/state.py` `create_session()` — call `tmux.has_session()` with the sanitized name before returning
- [x] 3.2 Wrap `tmux.new_session()` in `_fork_impl` with try/except, calling `delete_session()` on failure (mirror `_add_impl` pattern)

## 4. ConnectionManager Fixes

- [x] 4.1 Change `active_connections` from `list[WebSocket]` to `set[WebSocket]` in `server.py`
- [x] 4.2 Change `connect()` to use `.add()` and `disconnect()` to use `.discard()`
- [x] 4.3 Add per-connection error handling in `broadcast()` — catch exceptions, collect broken connections, remove them after iteration

## 5. API Security Defaults

- [x] 5.1 Change default `host` from `"0.0.0.0"` to `"127.0.0.1"` in `server.py` `uvicorn.run()` call
- [x] 5.2 Change default `host` from `"0.0.0.0"` to `"127.0.0.1"` in CLI `serve` command in `cli/__init__.py`

## 6. Fish Integration Fixes

- [x] 6.1 Add `status is-interactive; or return` as first line of `bootstrap.fish`
- [x] 6.2 Change `set -U __shoal_last_session` to `set -g __shoal_last_session` in `bootstrap.fish`
- [x] 6.3 Change `--preview="shoal info {}"` to `--preview='shoal info -- {}'` in `quick-attach.fish`
- [x] 6.4 Add `--` before `$session` in the `shoal attach` call in `quick-attach.fish`

## 7. CI Hardening

- [x] 7.1 Replace `curl -LsSf https://astral.sh/uv/install.sh | sh` with `uses: astral-sh/setup-uv@v5` in `.github/workflows/ci.yml`
- [x] 7.2 Remove unused imports (`Panel`, `Table`) from `installer.py`
- [x] 7.3 Add CI step to run `fish -n` on all `.fish` template files in `src/shoal/integrations/fish/templates/`
