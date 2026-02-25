## Why

Shoal's test coverage sits at ~59%, well below the 70% target for v0.6.0. Several core modules (theme, notify, popup) and most CLI command paths have zero or minimal test coverage. There are no integration tests for end-to-end workflows, no load tests for the API server, and the popup dashboard opens multiple unnecessary DB connections per invocation. A troubleshooting guide is also missing, making it harder for developers to self-serve when issues arise.

## What Changes

- Add unit tests for 6 untested modules: `core/notify.py`, `core/theme.py`, `dashboard/popup.py`, `cli/nvim.py`, `cli/setup.py`, `__main__.py`
- Expand CLI test coverage for `session.py`, `mcp.py`, `watcher.py`, `robo.py`, `worktree.py`
- Unskip fixable tests in `test_demo.py` and `test_mcp_pool.py`
- Add status bar edge case tests (all-same-status, large counts)
- Add fish uninstall test coverage
- Create integration tests for full session lifecycle workflows (new → fork → kill)
- Create API load tests with concurrent request handling
- Optimize `popup.py` to consolidate multiple DB connection cycles into one
- Evaluate connection pooling needs based on load test findings
- Create `docs/TROUBLESHOOTING.md` with common issues and solutions
- Audit and improve error messages with actionable suggestions
- Raise coverage threshold from 57% to 70% in `pyproject.toml`

## Capabilities

### New Capabilities

- `test-coverage-expansion`: Comprehensive unit test additions across all untested and under-tested modules to reach 70%+ coverage
- `integration-tests`: End-to-end workflow tests validating session lifecycle (create, fork, kill, cleanup)
- `api-load-tests`: Concurrent request load testing for the FastAPI server to validate performance under parallel access
- `db-optimization`: Consolidation of popup.py's multiple DB connection cycles and connection pooling evaluation
- `troubleshooting-guide`: Developer-facing documentation for common issues, debugging techniques, and self-service resolution

### Modified Capabilities

<!-- No existing spec requirements are changing -->

## Impact

- **Tests**: 16 existing test files expanded; 2-3 new test files added (`test_integration.py`, `test_api_load.py`, `test_theme.py`)
- **Source**: `dashboard/popup.py` refactored to use single DB lifecycle; `pyproject.toml` coverage threshold updated
- **Docs**: New `docs/TROUBLESHOOTING.md` file
- **CI**: Coverage gate raised from 57% → 70%
