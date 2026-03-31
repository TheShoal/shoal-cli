# Shoal × Lobster Party Integration Spec

This document specifies the implementation for integrating Shoal CLI with
[Lobster Party](~/sanctum/opus/patron/lobster-party/) (distributed Claw runtimes)
and [Smorgasbord](~/sanctum/opus/patron/smorgasbord/) (meta-repo context layer).

Three phases, each in its own worktree branch.

---

## Phase 1: Claw Runtime Provider (`feat/claw-provider`)

### Goal

Add `claw` as Shoal's second runtime provider so sessions can target lobster-party
Claw runtimes via gRPC instead of tmux.

### 1.1 Proto Stub Generation

Copy proto files from lobster-party and generate Python stubs:

```
proto/
  lobster_loop.proto    # copied from ~/sanctum/opus/patron/lobster-party/proto/
  a2a_core.proto
  a2a_claw.proto

src/shoal/generated/
  __init__.py
  lobster_loop_pb2.py
  lobster_loop_pb2.pyi
  lobster_loop_pb2_grpc.py
  a2a_core_pb2.py
  a2a_core_pb2.pyi
  a2a_claw_pb2.py
  a2a_claw_pb2.pyi
  a2a_claw_pb2_grpc.py
```

Add to justfile:

```makefile
gen-protos:
    python -m grpc_tools.protoc \
        -Iproto \
        --python_out=src/shoal/generated \
        --grpc_python_out=src/shoal/generated \
        --pyi_out=src/shoal/generated \
        proto/lobster_loop.proto \
        proto/a2a_core.proto \
        proto/a2a_claw.proto
```

Add optional dep group in pyproject.toml:

```toml
[project.optional-dependencies]
claw = ["grpcio>=1.60", "grpcio-tools>=1.60", "protobuf>=4.25"]
```

### 1.2 Data Model Changes

**File: `src/shoal/models/state.py`**

```python
class RuntimeKind(StrEnum):
    tmux = "tmux"
    claw = "claw"

class ClawRuntimeState(BaseModel):
    kind: Literal[RuntimeKind.claw] = RuntimeKind.claw
    claw_id: str
    grpc_addr: str           # e.g. "localhost:50051"
    employee_id: str = ""

# Update the union type:
RuntimeState = TmuxRuntimeState | ClawRuntimeState
```

The discriminated union uses the `kind` field. SQLite stores `runtime` as JSON —
Pydantic handles deserialization automatically.

### 1.3 Config Model

**New file: `src/shoal/models/config/claw.py`**

```python
class ClawConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grpc_addr: str = "localhost:50051"
    jwt_secret: str = ""
    employee_id: str = ""
    tls: bool = False
    known_claws: dict[str, str] = {}  # name → grpc_addr
```

Load from `[claw]` section in config.toml. Re-export from `models/config/__init__.py`.

### 1.4 gRPC Client

**New file: `src/shoal/core/claw_client.py`**

Async wrapper around generated stubs. Guard imports behind try/except for optional dep:

```python
class ClawClient:
    def __init__(self, addr: str, jwt_secret: str = "", tls: bool = False) -> None: ...
    async def turn(self, claw_id: str, employee_id: str, payload: str,
                   event_id: str | None = None) -> str: ...
    async def status(self, claw_id: str) -> ClawStatusResult: ...
    async def health(self, claw_id: str) -> ClawHealthResult: ...
    async def close(self) -> None: ...
    def _mint_jwt(self, claw_id: str, employee_id: str) -> str: ...
```

Use `grpc.aio` for async channels. Return plain dataclasses (not proto objects)
so the rest of Shoal doesn't depend on protobuf types.

### 1.5 Runtime Provider

**New file: `src/shoal/services/runtime_providers/claw.py`**

Implements all 13 `RuntimeProvider` Protocol methods:

| Method | Implementation |
|--------|---------------|
| `payload(runtime)` | Dict of claw_id, grpc_addr, employee_id |
| `summary(runtime)` | `{"claw": claw_id, "addr": grpc_addr}` |
| `exists(session)` | gRPC Health → healthy bool |
| `async_exists(session)` | Async gRPC Health |
| `attach(session)` | Raise `RuntimeError("Claw sessions do not support terminal attach")` |
| `capture_output(session, lines)` | Return empty string (no terminal pane) |
| `async_capture_output(session, lines)` | Return empty string |
| `async_send_input(session, text, enter, delay)` | gRPC Turn(payload=text), return response |
| `async_wait_for_ready(session, tool_config, timeout)` | Poll Health until healthy |
| `async_rename(session, new_name)` | Return runtime unchanged (Claws have durable IDs) |
| `async_kill(session)` | Return True (Claws are durable, we just remove from Shoal DB) |
| `async_observe(session, tool_config, lines)` | gRPC Status+Health → RuntimeObservation |

**Register in `services/runtime_provider.py`:**

```python
def _providers() -> dict[RuntimeKind, RuntimeProvider]:
    from shoal.services.runtime_providers.tmux import TmuxRuntimeProvider
    providers: dict[RuntimeKind, RuntimeProvider] = {
        RuntimeKind.tmux: TmuxRuntimeProvider(),
    }
    try:
        from shoal.services.runtime_providers.claw import ClawRuntimeProvider
        providers[RuntimeKind.claw] = ClawRuntimeProvider()
    except ImportError:
        pass  # grpcio not installed
    return providers
```

### 1.6 ClawState → SessionStatus Mapping

| ClawState (proto enum) | SessionStatus |
|------------------------|---------------|
| READY (4), ACTIVE (5) | running |
| IDLE (6) | idle |
| PAUSED (7), DRAINING (8) | waiting |
| FAILED (10) | error |
| TERMINATED (12), TERMINATING (11), SUSPENDED (9) | stopped |
| REQUESTED (1), PROVISIONING (2), STARTING (3) | running |
| UNSPECIFIED (0) | unknown |

### 1.7 Lifecycle

**New function in `services/lifecycle.py`:**

```python
async def create_claw_session_lifecycle(
    *,
    session_name: str,
    claw_id: str,
    grpc_addr: str,
    employee_id: str = "",
    prompt: str = "",
    tags: list[str] | None = None,
) -> SessionState:
```

- No tmux session creation
- No worktree creation (Claw has its own)
- Create DB row with ClawRuntimeState
- Verify health via gRPC
- If prompt provided, send via Turn RPC
- Emit session_created hook

**CLI entry: `shoal new --runtime claw --claw-id <id>`** or via template with
`runtime = "claw"` field.

### 1.8 Tests

All tests mock gRPC — no real lobster-loop needed for unit tests.
Mark integration tests with `@pytest.mark.claw`.

- `tests/test_claw_provider.py` — all 13 provider methods
- `tests/test_claw_client.py` — gRPC client with mocked channel
- `tests/test_claw_state.py` — ClawRuntimeState serialization, discriminator
- `tests/test_claw_config.py` — ClawConfig validation

### 1.9 Files Summary

| New | Modified |
|-----|----------|
| `proto/*.proto` (3 files) | `src/shoal/models/state.py` |
| `src/shoal/generated/*.py` (stubs) | `src/shoal/services/runtime_provider.py` |
| `src/shoal/core/claw_client.py` | `src/shoal/models/config/__init__.py` |
| `src/shoal/models/config/claw.py` | `src/shoal/core/config.py` |
| `src/shoal/services/runtime_providers/claw.py` | `src/shoal/services/lifecycle.py` |
| `scripts/generate_protos.sh` | `pyproject.toml` |
| `tests/test_claw_*.py` (4 files) | `justfile` |

---

## Phase 2: MCP ↔ A2A Bridge (`feat/mcp-a2a-bridge`)

### Goal

Add MCP tools to shoal-orchestrator so agents can interact with Claw runtimes,
and register Shoal as a delegatable command in lobster-party's majordomo.

### 2.1 New MCP Tools

**File: `src/shoal/services/mcp_shoal_server.py`**

Add these tools (requires `[claw]` extra):

| Tool | Params | Returns |
|------|--------|---------|
| `send_to_claw` | `claw_id: str, message: str` | `{"response": str, "state": str}` |
| `claw_status` | `claw_id: str \| list[str]` | Status dict or batch results |
| `list_claws` | — | List of configured claws from ClawConfig |
| `claw_health` | `claw_id: str` | `{"healthy": bool, "issues": list[str]}` |

Guard tool registration behind grpcio import check — tools only appear when
`shoal[claw]` is installed.

### 2.2 Lobster Party Side (Rust)

**File: `~/sanctum/opus/patron/lobster-party/cmd/lobster-loop/src/majordomo.rs`**

Add Shoal commands to the delegation whitelist:

```rust
"shoal.list" => ("shoal", &["ls", "--format", "json"]),
"shoal.status" => ("shoal", &["status", "--format", "json"]),
"shoal.send" => ("shoal", &["send", "{session}", "{keys}"]),
```

This enables Claws to call `majordomo-do --command-id shoal.list` to query Shoal
state from inside a sandbox.

### 2.3 Tests

- `tests/test_mcp_claw_tools.py` — mock ClawClient, test tool shapes
- lobster-party side: Rust unit test for new whitelist entries

### 2.4 Files Summary

| New | Modified |
|-----|----------|
| `tests/test_mcp_claw_tools.py` | `src/shoal/services/mcp_shoal_server.py` |
| | `~/sanctum/opus/patron/lobster-party/cmd/lobster-loop/src/majordomo.rs` |

---

## Phase 3: Conversation/Journal Sync (`feat/journal-sync`)

### Goal

Import lobster-party QMD conversations into Shoal journals and export Shoal
journals to QMD format for lobster-party's qmd-index.

### 3.1 QMD Format (read)

Lobster Party stores conversations as weekly-bucketed pairs:

```
conversations/{year}-W{week}/{turn_id}.md    # YAML frontmatter + markdown
conversations/{year}-W{week}/{turn_id}.json  # TurnRecord fields
```

JSON TurnRecord fields: `id`, `timestamp`, `claw_id`, `event_id`, `prompt`,
`response`, `thinking`, `prompt_summary`, `response_summary`, `model`,
`prompt_tokens`, `response_tokens`, `cost_usd`, `metadata`.

### 3.2 Import (QMD → Journal)

**New file: `src/shoal/core/claw_conversations.py`**

```python
@dataclass
class ClawTurn:
    id: str
    timestamp: datetime
    claw_id: str
    event_id: str
    prompt: str
    response: str
    model: str
    tokens: int | None
    cost_usd: float | None

def read_qmd_turns(conversations_dir: Path, since: datetime | None = None) -> list[ClawTurn]: ...
def turns_to_journal_entries(turns: list[ClawTurn]) -> str: ...
```

**Modified: `src/shoal/core/journal.py`**

```python
async def import_claw_turns(
    session_name: str,
    conversations_dir: Path,
    since: datetime | None = None,
) -> int:
    """Import QMD turns into session journal. Returns count of imported turns."""
```

Journal format per imported turn:

```markdown
## {timestamp} — claw-sync

**[claw:{claw_id} turn:{event_id}]** {prompt_summary}
> {response_summary}
({tokens} tokens, ${cost_usd})
```

### 3.3 Export (Journal → QMD)

```python
def export_journal_to_qmd(
    journal_path: Path,
    output_dir: Path,
    session_name: str,
) -> int:
    """Write journal entries as QMD-compatible markdown+JSON pairs. Returns count."""
```

### 3.4 CLI Command

```
shoal sync <session> [--direction import|export|both] [--since TIMESTAMP]
```

### 3.5 MCP Tool

```python
@mcp.tool()
async def sync_claw_conversations(
    session: str,
    direction: str = "import",
) -> dict[str, object]: ...
```

### 3.6 Tests

- `tests/test_claw_conversations.py` — parse fixture QMD files, roundtrip
- `tests/fixtures/qmd/` — sample .md and .json turn files

### 3.7 Files Summary

| New | Modified |
|-----|----------|
| `src/shoal/core/claw_conversations.py` | `src/shoal/core/journal.py` |
| `tests/test_claw_conversations.py` | `src/shoal/services/mcp_shoal_server.py` |
| `tests/fixtures/qmd/*.md` | `src/shoal/cli/session.py` |
| `tests/fixtures/qmd/*.json` | |

---

## Constraints

- Python 3.12+, `mypy --strict`, `ruff` lint
- `grpcio` is optional — all claw imports guarded with try/except
- `just ci` must pass without `[claw]` extra installed
- Tests requiring grpcio: `@pytest.mark.claw` (skipped if not installed)
- Conventional commits: `feat(claw): ...`, `feat(mcp): ...`, `feat(journal): ...`
- Proto stubs committed (not generated during CI)
