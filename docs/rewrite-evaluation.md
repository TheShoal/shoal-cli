# Rewrite Evaluation: Zig vs Rust vs Stay on Python

**Date**: 2026-03-31
**Status**: Decision pending

## Context

Shoal is ~19K LOC Python (src) + ~22K LOC Python (tests), 77 modules, 1307 tests. It depends on: typer, pydantic, rich, fastapi, uvicorn, aiosqlite, httpx, and optionally fastmcp. It runs on Python 3.12+ and targets macOS (POSIX).

The question: should Shoal be rewritten in a compiled language for performance, distribution, or architectural reasons? This document evaluates Zig and Rust as candidates and compares them honestly against staying on Python.

---

## 1. Current Python Strengths

Before weighing alternatives, what Python gives Shoal today:

| Strength | Detail |
|----------|--------|
| **Velocity** | 19K LOC built by one person in ~5 weeks with full test coverage |
| **Ecosystem** | Pydantic, FastAPI, Rich, Typer, aiosqlite — mature, well-documented, battle-tested |
| **MCP compatibility** | FastMCP is Python-native; the entire MCP ecosystem leans Python/TypeScript |
| **Async model** | `asyncio` maps cleanly to Shoal's I/O profile (tmux subprocess calls, SQLite, HTTP) |
| **Agent integration** | Claude Code, Pi, and other agents can read/modify Python trivially during dogfooding |
| **Distribution** | `pipx install shoal-cli` works today via PyPI |
| **Test infrastructure** | pytest + 1307 tests + coverage gates + parallel execution in 21s |
| **Type safety** | mypy --strict enforced; Pydantic v2 runtime validation |

**Current pain points:**

| Pain | Detail |
|------|--------|
| **Startup latency** | `shoal status` cold start is ~300-500ms (Python import overhead) |
| **Binary distribution** | Requires Python 3.12+ runtime; `pipx`/`uv tool` is good but not `brew install` simple |
| **Memory footprint** | FastAPI server + uvicorn + aiosqlite baseline is ~60-90 MB RSS |
| **Concurrency ceiling** | GIL limits CPU-bound work (not a real issue today — Shoal is I/O-bound) |

---

## 2. Option A: Rewrite in Rust

### What Rust Brings

**Performance:**
- CLI cold start: ~5-10ms (vs 300-500ms Python)
- Memory: ~5-15 MB RSS for the full server (vs 60-90 MB)
- No GIL — true parallel execution (irrelevant today but matters if Shoal grows)

**Distribution:**
- Single static binary, no runtime dependency
- Cross-compilation via `cargo build --target` (macOS, Linux, Windows)
- `brew install shoal`, `cargo install shoal`, direct download — all trivial
- No Python version conflicts, no virtualenv management for end users

**Reliability:**
- Ownership/borrow checker catches entire classes of async bugs at compile time
- No runtime type errors (mypy catches most, but not all)
- `Result<T, E>` error handling is more rigorous than Python exceptions

**Ecosystem for Shoal's needs:**

| Need | Rust crate | Maturity |
|------|-----------|----------|
| CLI framework | `clap` | Excellent — industry standard |
| Terminal UI | `ratatui` | Excellent — could enable a real TUI dashboard |
| HTTP server | `axum` | Excellent — async, tower middleware |
| SQLite | `rusqlite` / `sqlx` | Excellent |
| Async runtime | `tokio` | Excellent |
| TOML parsing | `toml` / `serde` | Excellent |
| Subprocess mgmt | `tokio::process` | Good |
| Rich terminal output | `ratatui`, `comfy-table`, `console` | Good (not Rich-level) |
| JSON/serialization | `serde` | Best-in-class |
| MCP protocol | `mcp-rust-sdk` | Early-stage, partial |
| Pydantic equivalent | `serde` + validation crates | Serde is better for serialization, weaker for runtime validation |

### What Rust Costs

| Cost | Detail |
|------|--------|
| **Rewrite effort** | 19K LOC Python → estimated 25-35K LOC Rust. Rust is more verbose (error handling, lifetimes, type annotations are longer). Realistic timeline: 3-6 months for one developer. |
| **Test rewrite** | 22K LOC / 1307 tests to rewrite. Rust testing is good but lacks pytest's parametrize/fixture ergonomics. |
| **MCP ecosystem gap** | FastMCP has no Rust equivalent. The MCP Rust SDK exists but is early. The pool/proxy architecture would need reimplementation from scratch. |
| **Pydantic loss** | Shoal uses Pydantic v2 extensively for config parsing, validation, serialization. Rust's `serde` handles serialization well but runtime validation (coercion, custom validators, `extra="forbid"`) requires manual implementation. |
| **Rich/Typer loss** | Rich's terminal rendering (panels, tables, trees, progress bars, markdown) has no single Rust equivalent. Would need to combine multiple crates or build custom. Typer's auto-generated help + type-safe CLI is unmatched in Rust (`clap` is powerful but more verbose). |
| **Agent dogfooding** | AI agents can't easily modify Rust code during Shoal development sessions. Compile-edit cycle is slower. |
| **Compile times** | Full rebuild: 30-60s. Incremental: 5-15s. Adds friction to the rapid iteration Shoal currently enjoys. |
| **Async complexity** | Tokio + lifetimes + Pin<Box<dyn Future>> for async trait methods is significantly more complex than Python asyncio. |
| **Community** | Shoal's target users (AI-assisted developers) are more likely to contribute Python patches than Rust patches. |

### Verdict: Rust

Rust makes sense if Shoal's primary value proposition becomes **distribution and performance** — i.e., it's a tool that thousands of developers install and expect to "just work" like `ripgrep` or `fd`. The single-binary story is compelling.

Rust does NOT make sense if Shoal's value is **rapid feature iteration for a personal/small-audience tool**. The 3-6 month rewrite cost is enormous relative to what's gained, and the MCP ecosystem gap is a real blocker.

---

## 3. Option B: Rewrite in Zig

### What Zig Brings

**Performance:**
- Same ballpark as Rust: ~5-10ms cold start, ~5-15 MB RSS
- Compiles to native code, no runtime dependency
- Cross-compilation is Zig's flagship feature — `zig build -Dtarget=x86_64-linux` trivially

**Distribution:**
- Single static binary (same benefit as Rust)
- Zig's cross-compilation story is arguably better than Rust's (no linker headaches)
- Can produce C-ABI libraries easily (FFI bridge to Python if needed for gradual migration)

**Simplicity:**
- No borrow checker — manual memory management but with safety features (optional safety checks, `defer` for cleanup)
- Simpler language than Rust — faster to learn, less ceremony
- No hidden allocations, no hidden control flow
- Comptime (compile-time execution) is powerful for code generation

**Ecosystem for Shoal's needs:**

| Need | Zig solution | Maturity |
|------|-------------|----------|
| CLI framework | `zig-clap`, `yazap` | Early — no `clap` equivalent |
| Terminal UI | `libvaxis` | Emerging — not ratatui-level |
| HTTP server | `zap`, `http.zig` (std) | Usable but young |
| SQLite | `zig-sqlite` (C interop) | Good (wraps C SQLite directly) |
| Async runtime | `std.io` (evented I/O) | Evolving — no tokio equivalent |
| TOML parsing | Community libraries | Immature |
| Subprocess mgmt | `std.process` | Adequate |
| Terminal output | Manual or thin wrappers | No Rich equivalent at all |
| JSON/serialization | `std.json` | Functional but manual |
| MCP protocol | Nothing exists | Would build from scratch |
| Pydantic equivalent | Nothing exists | Would build from scratch |

### What Zig Costs

| Cost | Detail |
|------|--------|
| **Ecosystem immaturity** | Zig's package ecosystem is where Rust's was in 2016. No mature CLI framework, no terminal UI library at Rich's level, no HTTP server framework at axum's level. Almost everything would be built from scratch or wrapped from C. |
| **Rewrite effort** | Higher than Rust — you're building more infrastructure yourself. Estimated 30-45K LOC. Timeline: 4-8 months. |
| **Async story** | Zig's async is in flux. The `std.io` evented I/O model changed between versions. No equivalent to tokio's mature async ecosystem. Shoal is async-first — this is a fundamental mismatch. |
| **No Pydantic, no serde** | Manual serialization/deserialization for every model. TOML, JSON, SQLite row mapping — all by hand. |
| **Stability** | Zig hasn't reached 1.0. Language semantics can change between releases. Building production software on a pre-1.0 language is a risk. |
| **Community size** | Zig community is ~1/10th Rust's. Fewer libraries, fewer Stack Overflow answers, fewer people who can contribute. |
| **Memory management** | No borrow checker means memory bugs are possible. `defer` helps but doesn't prevent use-after-free or double-free in complex async code. |
| **MCP from scratch** | No MCP SDK in Zig. Would need to implement JSON-RPC 2.0, the MCP protocol, transport layers — all from scratch. This alone is weeks of work. |

### Verdict: Zig

Zig makes sense if Shoal were a **performance-critical systems tool** (like a terminal multiplexer itself, a file watcher, or a build system) where C interop and zero-overhead abstractions matter.

Zig does NOT make sense for Shoal. The ecosystem gaps are too wide. You'd spend more time building infrastructure (CLI framework, HTTP server, TOML parser, terminal renderer, MCP protocol) than building Shoal features. The async story is immature for an async-first application.

---

## 4. Option C: Stay on Python (with targeted improvements)

### Address the real pain points without a rewrite

**Startup latency (300-500ms → ~100ms):**
- Lazy imports — don't load FastAPI/uvicorn for CLI-only commands
- `python -X importtime` to identify heavy imports
- Consider `shoal` CLI as a thin wrapper that lazy-loads subcommands

**Distribution (pip → single binary):**
- **PyApp**: Embeds Python + your app into a single binary (~30-50 MB). User downloads one file, it self-extracts and runs. No Python install needed.
- **Nuitka**: Compiles Python to C, produces a native binary. Preserves all Python semantics.
- **PyInstaller**: Bundles Python + deps. Larger output but well-understood.
- **uv**: Already supports `uv tool install shoal-cli` with automatic Python management — this may be "good enough" distribution.
- **Homebrew formula**: `brew install shoal` pointing to PyPI is straightforward.

**Memory footprint:**
- Only start FastAPI server on demand (`shoal server start`), not embedded in every CLI invocation
- Lazy-load heavy dependencies (rich, fastapi) only when needed

**Performance-critical hot paths (if they emerge):**
- Write specific hot functions in Rust via PyO3/maturin (e.g., status detection regex, pane output parsing)
- This is the incremental path: keep Python for 95% of code, Rust for the 5% that matters

### What this looks like

| Improvement | Effort | Impact |
|-------------|--------|--------|
| Lazy imports for CLI | 1-2 days | Halve startup time |
| PyApp binary distribution | 1-2 days | Single downloadable binary |
| Homebrew formula | Half day | `brew install shoal` |
| Lazy FastAPI loading | 1 day | Reduce baseline memory |
| PyO3 hot path (if needed) | 1-2 weeks | Native speed where it matters |

Total: ~1-2 weeks vs 3-8 months for a full rewrite.

---

## 5. Comparison Matrix

| Dimension | Python (current) | Python (improved) | Rust | Zig |
|-----------|-----------------|-------------------|------|-----|
| **Cold start** | 300-500ms | ~100-150ms | ~5-10ms | ~5-10ms |
| **Memory** | 60-90 MB | 30-50 MB | 5-15 MB | 5-15 MB |
| **Binary distribution** | pip/pipx/uv | Single binary (PyApp) | Single binary | Single binary |
| **Rewrite cost** | 0 | 1-2 weeks | 3-6 months | 4-8 months |
| **Feature velocity after** | High | High | Medium | Low |
| **MCP ecosystem** | Native (FastMCP) | Native | Partial (early SDK) | None |
| **CLI ergonomics** | Excellent (Typer+Rich) | Excellent | Good (clap) | Build from scratch |
| **Async maturity** | Mature (asyncio) | Mature | Mature (tokio) | Immature |
| **Test rewrite** | 0 | 0 | 1307 tests to port | 1307 tests to port |
| **Agent modifiability** | Trivial | Trivial | Hard | Hard |
| **Contributor accessibility** | High | High | Medium | Low |

---

## 6. Recommendation

**Stay on Python. Invest 1-2 weeks in targeted improvements.**

The honest assessment:

1. **Shoal is I/O-bound, not CPU-bound.** It calls tmux, reads SQLite, serves HTTP. A compiled language doesn't make these faster — the bottleneck is always the subprocess call or disk read, not Python overhead.

2. **The MCP ecosystem is Python/TypeScript.** Rewriting means abandoning FastMCP and reimplementing protocol handling. This is the single biggest practical blocker for both Rust and Zig.

3. **Distribution is solvable without a rewrite.** PyApp or Nuitka produce single binaries. `uv tool install` already manages Python automatically. A Homebrew formula is trivial.

4. **Startup latency is solvable with lazy imports.** The 300ms is import overhead, not interpretation overhead. Lazy-loading FastAPI/Rich for commands that don't need them cuts this significantly.

5. **Velocity matters more than performance.** Shoal ships features weekly. A 3-8 month rewrite means 3-8 months of no new features, while the AI agent ecosystem moves fast.

6. **The rewrite trap is real.** Most rewrites take 2-3x longer than estimated, ship with fewer features than the original, and introduce new bugs that the original had already fixed. 1307 tests is a lot of behavior to reimplement.

### When to reconsider

A compiled rewrite becomes worth it if:

- Shoal gains a large user base (1000+ daily users) where distribution friction matters at scale
- Performance profiling reveals Python-specific bottlenecks that lazy imports and PyO3 can't solve
- The MCP ecosystem matures in Rust (a production-quality Rust MCP SDK with FastMCP-equivalent features)
- Shoal needs to run as a system daemon or in resource-constrained environments where 60 MB RSS is unacceptable

None of these conditions are true today.

---

## 7. If You Did Rewrite: Rust > Zig

If the decision is to rewrite regardless:

**Rust wins on every axis that matters for Shoal:**
- Mature async (tokio) vs immature async (Zig)
- MCP SDK exists (early but real) vs nothing in Zig
- `clap` + `ratatui` vs build-from-scratch
- `serde` + `sqlx` vs manual everything
- 1.0 stable language vs pre-1.0 moving target
- 10x larger community and ecosystem

**Zig's advantages (C interop, simpler language, better cross-compilation) don't address Shoal's needs.** Shoal doesn't need C interop. Shoal's complexity is in orchestration logic, not systems programming. Cross-compilation is nice but Rust's is adequate.

The only scenario where Zig wins: if Shoal were being reimagined as a **tmux replacement** (the runtime provider itself, not the orchestration layer above it). For a terminal multiplexer, Zig's systems-level control and C interop with ncurses/termios would be relevant. But that's not what Shoal is.
