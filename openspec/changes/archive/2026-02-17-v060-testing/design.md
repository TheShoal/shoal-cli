## Context

Shoal is a terminal-first orchestration tool for parallel AI coding agents, currently at v0.5.0. Test coverage is ~59% with a threshold of 57%. The v0.6.0 milestone targets 70%+ coverage, integration/load testing, DB performance optimization, and developer experience improvements.

Key coverage gaps identified:
- 6 modules with zero test coverage (568 lines): `core/notify.py`, `core/theme.py`, `dashboard/popup.py`, `cli/nvim.py`, `cli/setup.py`, `__main__.py`
- 8 modules with significant gaps (2,547 lines): `cli/session.py`, `cli/robo.py`, `cli/demo.py`, `cli/worktree.py`, `cli/mcp.py`, `cli/watcher.py`, `integrations/fish/installer.py`, `services/mcp_pool.py`
- 8 skipped tests across `test_demo.py` and `test_mcp_pool.py`
- No integration or load tests exist
- `popup.py` opens 2-3 separate DB connections per invocation
- No troubleshooting documentation

The `--debug` flag was already implemented by a merged branch (commit `c9923fc`).

## Goals / Non-Goals

**Goals:**
- Reach 70%+ test coverage across all modules
- Add integration tests validating end-to-end session lifecycle workflows
- Add API load tests to validate concurrent request handling
- Optimize `popup.py` to use a single DB connection lifecycle
- Create a troubleshooting guide for common issues
- Raise the coverage threshold in pyproject.toml from 57% to 70%

**Non-Goals:**
- Implementing connection pooling (evaluate only; defer to v0.7.0 if needed)
- Refactoring the watcher polling architecture (that's v0.7.0 event bus work)
- Adding new features or CLI commands
- Changing the async DB architecture (aiosqlite singleton pattern stays)
- Full end-to-end tests requiring real tmux/git (all tests mock at system boundaries)

## Decisions

### 1. Test organization: extend existing files vs. create new ones
**Decision**: Extend existing test files for unit tests; create new files only for integration and load tests.
**Rationale**: Keeps related tests together. Each source module already maps to a test file (e.g., `test_state.py` → `core/state.py`). New files only for genuinely new test categories: `test_integration.py` for workflow tests, `test_api_load.py` for load tests, `test_theme.py` and `test_notify.py` for newly-tested modules.

### 2. Integration test approach: mocked boundaries vs. real tmux
**Decision**: Mock at the tmux/git/subprocess boundary, not at the application layer.
**Rationale**: Real tmux would make tests environment-dependent and flaky. Mocking at the boundary (e.g., `tmux.new_session`, `git.is_git_repo`) lets us test the full application logic path while keeping tests fast and CI-friendly. Use the `@pytest.mark.integration` marker already defined in pyproject.toml.

### 3. Load test approach: asyncio.gather vs. external tool
**Decision**: Use `asyncio.gather` with `httpx.AsyncClient` for in-process load tests.
**Rationale**: Keeps tests self-contained in pytest without external dependencies (no locust/k6). The FastAPI app can be tested via `ASGITransport` (already in conftest.py). Concurrent requests via `asyncio.gather` adequately stress the async handler pipeline and DB.

### 4. popup.py DB optimization strategy
**Decision**: Refactor `run_popup()` to pass pre-fetched session data rather than opening a second `with_db()` call. Use a closure or pass-through pattern.
**Rationale**: The current pattern opens DB twice in `run_popup()` — once for `_build_entries()` and once for `get_session()` after fzf selection. Since fzf is a blocking subprocess call in between, we can't keep a single async context open across it. Instead, we pre-fetch a session lookup dict alongside the entries list, eliminating the second DB call entirely.

### 5. Handling skipped tests
**Decision**: Attempt to unskip by adding proper mocks. Tests that genuinely require real system resources stay skipped with clear documentation.
**Rationale**: Skipped tests represent known gaps. Many were skipped for convenience rather than fundamental incompatibility. Adding mocks for `subprocess.Popen`, tmux commands, and git operations should make most of them runnable.

## Risks / Trade-offs

- **[Risk] Coverage percentage could be misleading** → Mitigation: Focus on testing meaningful behavior paths, not just lines. Prioritize error handling and edge cases over trivial getters.
- **[Risk] Mocked integration tests may miss real integration issues** → Mitigation: Keep mocks thin (mock system calls, not application logic). Real integration testing deferred to manual verification with tmux.
- **[Risk] Load tests may be flaky due to timing** → Mitigation: Use assertion on correctness (all requests succeed, no data corruption) rather than performance thresholds. Keep concurrency moderate (10-20 concurrent requests).
## Load Test Results & Evaluation

Load testing was performed using `asyncio.gather` with 20 concurrent requests for read operations (listing sessions, status polling) and 10 concurrent mixed read/write operations.

**Findings:**
- **Zero Failures**: All concurrent requests returned 200/201 status codes.
- **Data Integrity**: Interleaved reads and writes showed no signs of data corruption or deadlocks.
- **Performance**: In-process response times remained sub-millisecond even under concurrency.

**Evaluation:**
The current `aiosqlite` single-connection singleton with WAL mode enabled is highly performant and sufficient for Shoal's multi-agent orchestrator use case. Shoal typically handles low-to-medium concurrency (single user, many agents).

**Recommendation:**
Connection pooling is **NOT required** for v0.6.0. The single-connection architecture should be maintained for simplicity and reliability. This decision should be re-evaluated only if multi-user support or significantly higher agent concurrency becomes a goal.
