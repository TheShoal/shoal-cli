# Python Improvement Plan

**Date**: 2026-03-31
**Status**: Actionable
**Companion doc**: [rewrite-evaluation.md](rewrite-evaluation.md)

## Current Baseline (measured)

| Metric | Value | How measured |
|--------|-------|-------------|
| `shoal --help` cold start | 335ms | `time uv run shoal --help` |
| `shoal ls` (no sessions) | 305ms | `time uv run shoal ls` |
| `shoal status` (no sessions) | 341ms | `time uv run shoal status` |
| `uv run` overhead | ~45ms | `time uv run python -c "pass"` |
| Total imports on startup | 580 modules | `python -X importtime` |
| `shoal.cli` import time | 211ms | importtime self+cumulative |
| Biggest offender | `shoal.models.config` at 64ms cumulative | 22 Pydantic models, triggers full pydantic_core + asyncio import chain |
| Second offender | `rich.console` at 31ms cumulative | Pulled by every CLI module at top level |
| Third offender | `httpx` at 29ms cumulative | Pulled by config_cmd → core.config |
| Source LOC | 19K (src), 22K (tests) | `wc -l` |
| Test count | 1307 | `pytest --co -q` |
| Test wall time | ~21s | `pytest -n auto` |

---

## Improvement 1: Lazy Subcommand Imports

**Problem**: `cli/__init__.py` eagerly imports all 20+ CLI modules at top level. Every `shoal` invocation pays the cost of importing `session_create`, `config_cmd`, `fin`, `incident`, `remote`, `robo`, etc. — even if the user just typed `shoal ls`.

**Root cause** (lines 11–34 of `src/shoal/cli/__init__.py`):

```python
from shoal.cli.config_cmd import app as config_app
from shoal.cli.demo import app as demo_app
from shoal.cli.fin import app as fin_app
from shoal.cli.handoff import handoff_ls, handoff_show
# ... 15 more top-level imports
```

Each of these pulls in `rich.console`, `shoal.core.config` (which pulls `shoal.models.config` → Pydantic → pydantic_core), and various other heavy dependencies.

**Fix**: Use Typer's lazy loading pattern. Register subcommands with string references that resolve on invocation, not import.

**Approach A — Typer lazy groups** (cleanest):

```python
# cli/__init__.py — only import typer, nothing else
import typer

app = typer.Typer(name="shoal", no_args_is_help=True, rich_markup_mode="rich")

# Lazy-loaded subgroups — only imported when the subcommand is invoked
@app.command("ls")
def ls_cmd(**kwargs):
    from shoal.cli.session_view import ls
    ls(**kwargs)
```

This is verbose. Better option:

**Approach B — LazyGroup pattern** (used by pip, uv, and other large CLIs):

```python
# cli/lazy.py
import importlib
import typer

class LazyTyper(typer.Typer):
    """Typer subclass that defers subcommand module imports."""

    def __init__(self, *args, lazy_subcommands: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._lazy = lazy_subcommands or {}

    # Override invoke to import on demand
    ...
```

**Approach C — Split CLI entry point** (simplest, biggest win):

Keep the current `cli/__init__.py` structure but move all top-level imports inside functions:

```python
# Before (current):
from shoal.cli.session_view import info, logs, ls, status

# After:
def _ls(**kwargs):
    from shoal.cli.session_view import ls
    return ls(**kwargs)

app.command("ls")(_ls)
```

**Estimated impact**: Cuts startup from ~300ms to ~80-120ms for commands that don't need the full import tree. The hot path (`shoal ls`, `shoal status`, `shoal popup`) would only import what they actually use.

**Effort**: 1-2 days. Mechanical refactor of `cli/__init__.py` + verify all commands still work.

**Risk**: Low. Typer defers argument parsing until invocation, so lazy imports are safe as long as type annotations use `from __future__ import annotations`.

---

## Improvement 2: Split `models/config.py`

**Problem**: `shoal.models.config` is a 372-line file with 22 Pydantic models. Importing *any* config type pulls in *all* of them, and Pydantic model class creation is expensive (~19ms self-time for this module alone, ~64ms cumulative with pydantic_core).

**Fix**: Split into focused modules:

```
models/
├── config/
│   ├── __init__.py          # Re-exports for backwards compat
│   ├── general.py           # GeneralConfig, TmuxConfig, RoboConfig
│   ├── templates.py         # SessionTemplateConfig, TemplateMixinConfig, etc.
│   ├── tools.py             # ToolConfig, DetectionConfig
│   ├── mcp.py               # McpServerConfig, McpConfig
│   └── hooks.py             # ProjectHookEntry
```

Commands that only need `GeneralConfig` (most of them) won't pay the cost of defining `SessionTemplateConfig`, `TemplateMixinConfig`, `TemplateWindowConfig`, etc.

**Estimated impact**: Reduces per-command Pydantic overhead by ~40-60% depending on which models are actually needed. Combined with lazy imports, `shoal ls` would only instantiate `GeneralConfig` + `ToolConfig`.

**Effort**: 1-2 days. Split file, update imports across codebase, verify tests.

**Risk**: Medium. Import cycles need care. The `__init__.py` re-export pattern keeps backwards compatibility.

---

## Improvement 3: Lazy Rich and httpx

**Problem**: `rich.console.Console()` is instantiated at module top level in most CLI modules:

```python
# Top of nearly every cli/*.py file:
from rich.console import Console
console = Console()
```

`rich.console` alone is 31ms cumulative. `httpx` is 29ms cumulative (pulled in through config paths even for local-only commands).

**Fix**:

**For Rich** — Defer `Console()` creation to first use:

```python
# shoal/core/theme.py or cli/console.py
from functools import lru_cache

@lru_cache(maxsize=1)
def get_console():
    from rich.console import Console
    return Console()
```

CLI modules call `get_console()` instead of having a module-level `console = Console()`.

**For httpx** — Ensure it's only imported in code paths that actually make HTTP calls (remote commands, API client). Most local CLI commands don't need it. If `core/config.py` imports it at the top level, move to function-level import.

**Estimated impact**: ~50ms saved when combined (rich + httpx not loaded for fast-path commands).

**Effort**: Half day for Rich pattern. Quick grep + fix for httpx.

**Risk**: Low. `lru_cache` is thread-safe and the Console object is stateless enough for sharing.

---

## Improvement 4: Binary Distribution via PyApp

**Problem**: Installing Shoal requires Python 3.12+, `pipx` or `uv tool`, and familiarity with Python packaging. This is fine for Python developers but a barrier for anyone else.

**Fix**: [PyApp](https://github.com/ofek/pyapp) embeds a Python interpreter + your wheel into a single self-extracting binary. The user downloads one file and runs it.

```bash
# Build a self-contained binary
PYAPP_PROJECT_NAME=shoal-cli PYAPP_PROJECT_VERSION=0.27.0 cargo install pyapp --force

# Result: single binary, ~30-50 MB, works on any macOS/Linux without Python
```

**Distribution channels this enables:**

| Channel | How |
|---------|-----|
| GitHub Releases | Upload binary per OS/arch to each release |
| Homebrew | Formula pointing to GitHub release binary |
| Direct download | `curl -fsSL https://shoal.dev/install.sh \| sh` |
| Existing | `pipx install shoal-cli` still works (unchanged) |

**Estimated impact**: Zero-dependency install for end users. First-run extracts in ~2s, subsequent runs are as fast as normal `pipx`.

**Effort**: 1-2 days. PyApp config, CI job for release builds, update install docs.

**Risk**: Low. PyApp is maintained by the Hatch creator (Ofek Lev), used by Hatch itself. Self-contained binaries are well-tested.

**Alternative**: Nuitka compiles Python to C, producing a truly native binary (~15-30 MB). More complex build but faster cold start (~50-80ms). Consider if PyApp's extraction overhead is unacceptable.

---

## Improvement 5: On-Demand Server Process

**Problem**: FastAPI + uvicorn are imported and available in every CLI invocation even though the HTTP server is only needed for `shoal serve` and API consumers. FastAPI alone contributes to the import chain.

**Current state**: `shoal serve` already lazy-imports uvicorn and the FastAPI app (good). But `shoal.api` types leak into other modules via shared models.

**Fix**: Audit and sever any import path from CLI modules → `shoal.api.*`. The API layer should be fully isolated — only loaded by `shoal serve`.

```bash
# Verify no CLI module pulls in API:
python -X importtime -c "from shoal.cli.session_view import ls" 2>&1 | grep "shoal.api"
# Should return nothing
```

**Estimated impact**: Small on its own (~5-10ms), but prevents future API growth from slowing CLI startup.

**Effort**: Half day. Trace imports, move any shared types to `models/`.

**Risk**: Low.

---

## Improvement 6: Homebrew Formula

**Problem**: `pipx install shoal-cli` works but isn't discoverable. Developers expect `brew install <tool>`.

**Fix**: Create a Homebrew tap (`TheShoal/homebrew-tap`) with a formula:

```ruby
class ShoalCli < Formula
  include Language::Python::Virtualenv

  desc "Terminal-first orchestration for parallel AI coding agents"
  homepage "https://github.com/TheShoal/shoal-cli"
  url "https://files.pythonhosted.org/packages/.../shoal_cli-0.27.0.tar.gz"
  sha256 "..."
  license "MIT"

  depends_on "python@3.12"
  depends_on "tmux"

  # ... resource blocks for dependencies
end
```

Or, with PyApp binary:

```ruby
class ShoalCli < Formula
  desc "Terminal-first orchestration for parallel AI coding agents"
  homepage "https://github.com/TheShoal/shoal-cli"

  on_macos do
    on_arm do
      url "https://github.com/TheShoal/shoal-cli/releases/download/v0.32.0/shoal-aarch64-apple-darwin"
      sha256 "..."
    end
    on_intel do
      url "https://github.com/TheShoal/shoal-cli/releases/download/v0.32.0/shoal-x86_64-apple-darwin"
      sha256 "..."
    end
  end

  def install
    bin.install "shoal-#{arch}-apple-darwin" => "shoal"
  end
end
```

**Effort**: Half day for tap + formula. Add to CI release workflow.

**Risk**: Low. Homebrew taps are well-documented.

---

## Improvement 7: Test Performance

**Problem**: 1307 tests run in ~21s with `pytest -n auto`. Not slow, but could be faster.

**Opportunities**:

| Improvement | Detail | Estimated savings |
|-------------|--------|-------------------|
| **Pydantic model caching in fixtures** | Many tests create the same config models repeatedly. A session-scoped fixture for common configs avoids repeated Pydantic validation. | ~2-3s |
| **DB fixture pooling** | If tests use separate in-memory DBs, the schema creation cost is paid per test. A shared schema with transaction rollback is faster. | ~1-2s |
| **Import caching** | `pytest-lazy-fixture` or module-level test setup to avoid re-importing heavy modules per test file. | ~1-2s |
| **Selective markers** | `@pytest.mark.slow` on known-slow tests (subprocess calls, MCP integration) for `pytest -m "not slow"` fast feedback. | Enables <5s for unit-only |

**Effort**: 1-2 days for meaningful gains.

**Risk**: Low. Additive changes.

---

## Improvement 8: Memory Footprint

**Problem**: Shoal processes (CLI invocations, server, status bar) use 60-90 MB RSS baseline due to Python interpreter + loaded libraries.

**Fixes**:

| Fix | Detail | Savings |
|-----|--------|---------|
| **Lazy imports** (above) | Fewer modules loaded = less RSS | ~10-20 MB for CLI-only |
| **Separate server process** | Don't embed FastAPI in CLI; `shoal serve` is its own process | CLI drops to ~30-40 MB |
| **`__slots__` on hot models** | Pydantic v2 supports `__slots__`-like behavior via `model_config`. SessionState and other frequently instantiated models. | Marginal (~1-2 MB) |
| **Process recycling for status bar** | `shoal-status` is invoked every N seconds by the fish prompt. If it's a long-running process instead of repeated cold starts, memory is amortized. | Eliminates repeated 30 MB allocs |

**Effort**: Mostly covered by other improvements. Status bar daemon is ~1 day.

---

## Priority Order

| # | Improvement | Effort | Impact | Dependencies |
|---|-----------|--------|--------|-------------|
| 1 | Lazy subcommand imports | 1-2 days | ~150ms startup reduction | None |
| 2 | Lazy Rich + httpx | 0.5 days | ~50ms startup reduction | None |
| 3 | Split `models/config.py` | 1-2 days | ~30ms startup reduction + cleaner architecture | None |
| 4 | PyApp binary distribution | 1-2 days | Zero-dep install | Release CI |
| 5 | Homebrew formula | 0.5 days | `brew install shoal` | #4 (for binary formula) or PyPI (for Python formula) |
| 6 | On-demand server isolation | 0.5 days | ~5-10ms + architectural cleanliness | None |
| 7 | Test performance | 1-2 days | Faster dev feedback | None |
| 8 | Memory footprint | 1 day | ~30 MB RSS reduction for CLI | #1, #6 |

**Total effort**: ~7-10 days for everything. Items 1-3 can be done in a single sprint and would bring `shoal ls` from 305ms to ~100-120ms.

---

## Target State

| Metric | Current | After improvements |
|--------|---------|-------------------|
| `shoal ls` cold start | 305ms | ~100-120ms |
| `shoal --help` cold start | 335ms | ~80-100ms |
| `shoal status` cold start | 341ms | ~100-130ms |
| Installation | `pipx install shoal-cli` (needs Python 3.12) | `brew install shoal` or download binary |
| CLI RSS | ~60 MB | ~30-40 MB |
| Server RSS | ~90 MB (embedded) | ~60 MB (separate process) |
| Test wall time | ~21s | ~15s (unit-only: <5s) |
