## 1. Quick Win Tests — Zero-Coverage Modules

- [x] 1.1 Create `tests/test_notify.py` with tests for `notify()` (macOS mock, non-macOS skip) and `_escape_applescript_string()` escaping
- [x] 1.2 Create `tests/test_theme.py` with tests for `tmux_status_segment()`, `create_panel()`, `create_table()`, STATUS_STYLES completeness, and icon/symbol constants
- [x] 1.3 Add tests for `dashboard/popup.py` — `_build_entries()` with sessions and empty DB, `print_popup_list()` output format
- [x] 1.4 Add tests for `cli/nvim.py` — `nvim send` (valid/invalid session), `nvim diagnostics` via CLI runner with mocked nvr
- [x] 1.5 Add tests for `cli/setup.py` — `setup fish` command dispatch via CLI runner

## 2. Status Bar & Watcher Edge Cases

- [x] 2.1 Add status bar test: all sessions in same status (only one segment rendered)
- [x] 2.2 Add status bar test: large session count (100+ sessions, correct aggregation)
- [x] 2.3 Add status bar test: all sessions stopped (empty output, no segments)

## 3. CLI Coverage Expansion

- [x] 3.1 Add `cli/session.py` tests: `kill` command (success + not found), `logs` success path, `attach` error paths
- [x] 3.2 Add `cli/mcp.py` tests: `mcp start` (known server), `mcp stop`, `mcp attach`, `mcp detach` with mocked pool
- [x] 3.3 Add `cli/watcher.py` tests: `watcher start --foreground` (mocked Watcher), `watcher start` (background subprocess mock)
- [x] 3.4 Add `cli/robo.py` tests: `robo setup`, `robo start`, `robo stop`, `robo status` via CLI runner
- [x] 3.5 Add `cli/worktree.py` tests: `wt finish` (merge + cleanup), `wt cleanup` (orphan detection) with mocked git

## 4. Unskip & Fix Existing Tests

- [x] 4.1 Unskip fixable `test_demo.py` tests by adding proper tmux/git mocks (start happy path, idempotency, missing tools, custom dir)
- [x] 4.2 Unskip fixable `test_mcp_pool.py` tests by adding proper subprocess mocks (is_mcp_running true, start_mcp_server, stop_mcp_server)
- [x] 4.3 Add `uninstall_fish_integration()` test to `test_fish_integration.py` (file removal, error handling)

## 5. Integration Tests

- [x] 5.1 Create `tests/test_integration.py` with `@pytest.mark.integration` marker
- [x] 5.2 Add session lifecycle test: create → verify status → update → kill → verify cleanup
- [x] 5.3 Add fork workflow test: create parent → fork → verify fork inherits path/tool → kill both
- [x] 5.4 Add multi-session status aggregation test: create sessions in different statuses, verify counts

## 6. API Load Tests

- [x] 6.1 Create `tests/test_api_load.py` with concurrent request test infrastructure
- [x] 6.2 Add concurrent GET /sessions test (20 parallel requests, all return 200)
- [x] 6.3 Add concurrent GET /status test (20 parallel requests, consistent counts)
- [x] 6.4 Add concurrent mixed operations test (interleaved reads + writes, no corruption)

## 7. Database Optimization

- [x] 7.1 Refactor `popup.py` `run_popup()` to pre-fetch session lookup dict alongside entries, eliminating second `with_db()` call
- [x] 7.2 Add/update popup tests to verify single DB lifecycle pattern
- [x] 7.3 Document connection pooling evaluation findings based on load test results (comments in code or design doc update)

## 8. Developer Experience

- [x] 8.1 Create `docs/TROUBLESHOOTING.md` covering: watcher issues, DB locked errors, tmux session not found, MCP connection problems, --debug usage
- [x] 8.2 Audit CLI error messages and add actionable suggestions where missing (focus on `session.py`, `mcp.py`, `watcher.py`)
- [x] 8.3 Update `pyproject.toml` coverage threshold from 57% to 70%
- [x] 8.4 Run full test suite with coverage and verify 70%+ achieved
- [x] 8.5 Update ROADMAP.md to mark v0.6.0 items as completed
