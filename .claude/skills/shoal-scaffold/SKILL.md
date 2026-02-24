---
name: shoal-scaffold
description: Scaffold new Shoal modules, CLI commands, services, models, and tests following project patterns. Use when adding new features, subcommands, or core modules to the codebase.
argument-hint: <type> <name>
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Scaffold Shoal Components

Generate boilerplate for new Shoal modules that follow existing patterns exactly. `$ARGUMENTS` specifies what to scaffold.

## Parse Arguments

Format: `<type> <name>` where type is one of:

- **`cli <name>`** — New CLI subcommand group (Typer sub-app)
- **`command <group> <name>`** — New command within an existing CLI group
- **`service <name>`** — New service module in `src/shoal/services/`
- **`core <name>`** — New core module in `src/shoal/core/`
- **`model <name>`** — New Pydantic model in `src/shoal/models/`
- **`mcp-tool <name>`** — New MCP tool in the shoal-orchestrator server
- **`template <name>`** — New session template in `examples/config/templates/`
- **`integration <name>`** — New integration test

If `$ARGUMENTS` is empty, ask the user what they want to scaffold.

## Scaffold Rules

### For ALL types:
1. Read 2-3 existing files of the same type to learn the exact patterns (imports, docstrings, error handling, typing)
2. Use `mypy --strict` compatible type hints on every function signature
3. Use `async/await` for any I/O operation
4. Use `asyncio.to_thread()` for blocking subprocess calls in async contexts
5. Add a named logger: `logger = logging.getLogger("shoal.<module>")`
6. Line length: 100 chars max
7. Imports: absolute, sorted by ruff (stdlib → third-party → local)

### `cli <name>` — CLI Subcommand Group
1. Read `src/shoal/cli/session.py` and `src/shoal/cli/mcp.py` for patterns
2. Create `src/shoal/cli/<name>.py` with:
   - Typer sub-app: `app = typer.Typer(name="<name>", help="...")`
   - At least one command stub with `@app.command()`
   - Rich console output patterns (Panel, Table, etc.)
   - `asyncio.run(with_db(_impl()))` wrapper for DB access
3. Register in `src/shoal/cli/__init__.py`: `app.add_typer(<name>.app)`
4. Create `tests/test_cli_<name>.py` with:
   - CliRunner test for help output
   - At least one functional test with mocked dependencies
5. Add fish completion stubs in the completions template if applicable

### `service <name>` — Service Module
1. Read `src/shoal/services/lifecycle.py` for the canonical service pattern
2. Create `src/shoal/services/<name>.py` with:
   - Async functions (not classes, unless stateful)
   - Scoped exception class if the service has failure modes
   - Structured logging with `logger.debug()` timing for key operations
   - Clear separation: one orchestration function, private helpers prefixed `_`
3. Create `tests/test_<name>.py` with:
   - `@pytest.mark.asyncio` on async tests
   - Mock external dependencies (tmux, git, DB)
   - Test both happy path and error/rollback paths

### `core <name>` — Core Module
1. Read `src/shoal/core/state.py` or `src/shoal/core/config.py` for patterns
2. Create `src/shoal/core/<name>.py` with:
   - Pure async functions for I/O
   - Type-safe return values (Pydantic models or typed dicts)
3. Create `tests/test_<name>.py`

### `model <name>` — Pydantic Model
1. Read `src/shoal/models/config.py` and `src/shoal/models/state.py` for patterns
2. Add model to existing models file or create `src/shoal/models/<name>.py` with:
   - Pydantic v2 `BaseModel` with `model_config = ConfigDict(...)` if needed
   - Field validators using `@field_validator` or `@model_validator`
   - `extra="forbid"` on config models
   - Sensible defaults, clear field descriptions
3. Add tests to `tests/test_models.py` or create `tests/test_<name>_models.py`

### `mcp-tool <name>` — New MCP Tool
1. Read `src/shoal/services/mcp_shoal_server.py` for the FastMCP tool pattern
2. Add a new `@mcp.tool()` function following existing patterns:
   - Docstring becomes the tool description
   - Return a dict (JSON-serializable)
   - Use `await asyncio.to_thread(...)` for blocking calls
   - Handle errors gracefully (return error dict, don't raise)
3. Add tests to `tests/test_mcp_shoal_server.py`

### `template <name>` — Session Template
1. Read `examples/config/templates/base-dev.toml` for the canonical structure
2. Create `examples/config/templates/<name>.toml` with:
   - `[template]` section: name, description, tool, extends (if inheriting)
   - `[template.worktree]` section if isolation is needed
   - `[[windows]]` and `[[windows.panes]]` for layout
3. Validate: `uv run python -c "import tomllib; tomllib.load(open('examples/config/templates/<name>.toml', 'rb'))"`
4. Add to template validation test if applicable

### `integration <name>` — Integration Test
1. Read `tests/test_integration.py` for patterns
2. Create test with `@pytest.mark.integration` marker
3. Include tmux/session setup and teardown
4. Use real subprocess calls (not mocked)

## After Scaffolding

1. Show the user what was created (file list with line counts)
2. Run `just lint` and `just typecheck` on the new files
3. Run the new test file: `uv run pytest tests/test_<name>.py -x -q`
4. Report any issues and fix them before finishing
