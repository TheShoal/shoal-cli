# Scaffold — Component Generator

Generate boilerplate for new Shoal modules that follow existing patterns exactly.

## Supported Types

- **`cli <name>`** — New CLI subcommand group (Typer sub-app)
- **`command <group> <name>`** — New command within an existing CLI group
- **`service <name>`** — New service module in `src/shoal/services/`
- **`core <name>`** — New core module in `src/shoal/core/`
- **`model <name>`** — New Pydantic model in `src/shoal/models/`
- **`mcp-tool <name>`** — New MCP tool in the shoal-orchestrator server
- **`template <name>`** — New session template in `examples/config/templates/`
- **`integration <name>`** — New integration test

## Scaffold Rules

For ALL types:
1. Read 2-3 existing files of the same type to learn the exact patterns
2. Use `mypy --strict` compatible type hints on every function signature
3. Use `async/await` for any I/O operation
4. Use `asyncio.to_thread()` for blocking subprocess calls in async contexts
5. Add a named logger: `logger = logging.getLogger("shoal.<module>")`
6. Line length: 100 chars max
7. Imports: absolute, sorted by ruff (stdlib -> third-party -> local)

## Type-Specific Patterns

### `cli <name>`
1. Read `src/shoal/cli/session.py` and `src/shoal/cli/mcp.py` for patterns
2. Create `src/shoal/cli/<name>.py` with Typer sub-app, Rich output, `asyncio.run(with_db(_impl()))` wrapper
3. Register in `src/shoal/cli/__init__.py`
4. Create `tests/test_cli_<name>.py` with CliRunner tests
5. Add fish completion stubs if applicable

### `service <name>`
1. Read `src/shoal/services/lifecycle.py` for canonical patterns
2. Async functions (not classes unless stateful), scoped exceptions, structured logging
3. Create `tests/test_<name>.py` with `@pytest.mark.asyncio`, mocked dependencies

### `core <name>`
1. Read `src/shoal/core/state.py` or `src/shoal/core/config.py` for patterns
2. Pure async functions, type-safe return values (Pydantic models or typed dicts)
3. Create `tests/test_<name>.py`

### `model <name>`
1. Read `src/shoal/models/config.py` and `src/shoal/models/state.py` for patterns
2. Pydantic v2 BaseModel with `extra="forbid"` on config models, field validators
3. Add tests to `tests/test_models.py` or create `tests/test_<name>_models.py`

### `mcp-tool <name>`
1. Read `src/shoal/services/mcp_shoal_server.py` for the FastMCP tool pattern
2. Add `@mcp.tool()` function, return dict, use `await asyncio.to_thread()` for blocking calls
3. Add tests to `tests/test_mcp_shoal_server.py`

### `template <name>`
1. Read `examples/config/templates/base-dev.toml` for canonical structure
2. Create `examples/config/templates/<name>.toml` with `[template]` section
3. Validate TOML syntax

### `integration <name>`
1. Read `tests/test_integration.py` for patterns
2. Mark with `@pytest.mark.integration`, include tmux setup/teardown, use real subprocess calls

## After Scaffolding

1. Show what was created (file list with line counts)
2. Run `just lint` and `just typecheck` on the new files
3. Run the new test file: `uv run pytest tests/test_<name>.py -x -q`
4. Report any issues and fix them
