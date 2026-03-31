---
name: shoal-scaffold
description: Scaffold new Shoal modules, CLI commands, services, models, and tests following project patterns. Use when adding new features, subcommands, or core modules.
---

# Scaffold Shoal Components

Generate boilerplate for new Shoal modules that follow existing patterns exactly.

## Types

- **`cli <name>`** — New CLI subcommand group (Typer sub-app)
- **`command <group> <name>`** — New command within an existing CLI group
- **`service <name>`** — New service module in `src/shoal/services/`
- **`core <name>`** — New core module in `src/shoal/core/`
- **`model <name>`** — New Pydantic model in `src/shoal/models/`
- **`mcp-tool <name>`** — New MCP tool in the shoal-orchestrator server
- **`template <name>`** — New session template in `examples/config/templates/`
- **`integration <name>`** — New integration test

If no type is specified, ask the user what they want to scaffold.

## Rules for ALL types

1. Read 2-3 existing files of the same type to learn the exact patterns (imports, docstrings, error handling, typing)
2. Use `mypy --strict` compatible type hints on every function signature
3. Use `async/await` for any I/O operation
4. Use `asyncio.to_thread()` for blocking subprocess calls in async contexts
5. Add a named logger: `logger = logging.getLogger("shoal.<module>")`
6. Line length: 100 chars max
7. Imports: absolute, sorted by ruff (stdlib → third-party → local)

## Scaffold patterns

### `cli <name>` — CLI Subcommand Group
1. Read `src/shoal/cli/session.py` and `src/shoal/cli/mcp.py` for patterns
2. Create `src/shoal/cli/<name>.py` with Typer sub-app, Rich console output, `asyncio.run(with_db(_impl()))` wrapper
3. Register in `src/shoal/cli/__init__.py`
4. Create `tests/test_cli_<name>.py` with CliRunner tests
5. Add fish completion stubs if applicable

### `service <name>` — Service Module
1. Read `src/shoal/services/lifecycle.py` for the canonical pattern
2. Async functions, scoped exception class, structured logging with timing
3. Create `tests/test_<name>.py` with `@pytest.mark.asyncio`, mocked dependencies, happy + error paths

### `core <name>` — Core Module
1. Read `src/shoal/core/state.py` or `src/shoal/core/config.py` for patterns
2. Pure async functions, type-safe return values (Pydantic models or typed dicts)
3. Create `tests/test_<name>.py`

### `model <name>` — Pydantic Model
1. Read `src/shoal/models/config.py` and `src/shoal/models/state.py` for patterns
2. Pydantic v2 `BaseModel` with `model_config = ConfigDict(...)`, field validators, `extra="forbid"` on config models
3. Add tests to `tests/test_models.py` or create `tests/test_<name>_models.py`

### `mcp-tool <name>` — New MCP Tool
1. Read `src/shoal/services/mcp_shoal_server.py` for the FastMCP tool pattern
2. `@mcp.tool()` function with docstring description, dict return, `await asyncio.to_thread()` for blocking calls
3. Add tests to `tests/test_mcp_shoal_server.py`

### `template <name>` — Session Template
1. Read `examples/config/templates/base-dev.toml` for structure
2. Create TOML with `[template]` section, validate with `tomllib`
3. Add to template validation test if applicable

### `integration <name>` — Integration Test
1. Read `tests/test_integration.py` for patterns
2. `@pytest.mark.integration` marker, real subprocess calls

## After Scaffolding

1. Show the user what was created (file list with line counts)
2. Run `just lint` and `just typecheck` on the new files
3. Run the new test file: `uv run pytest tests/test_<name>.py -x -q`
4. Report and fix any issues before finishing
