# Extensions (Fins) Capability Map

This document captures Shoal's current extension surface, known gaps, and a practical
boundary recommendation for `shoal-cli` vs `shoal-core`.

Related review:

- `docs/EXTENSIONS_REVIEW.md` (2026-02-25 performer review: spec compliance,
  user exposure analysis, and hardening plan)

## Contract Baseline

- Shoal targets Fin contract v1 manifests (`fin.toml`) with:
  - `name`, `version`, `fin_contract_version`, `capability`
  - `[entrypoints] install|configure|run|validate`
- Current support window: v1 only.
- Contract references:
  - `../fins-template/docs/fin-contract-v1.md`
  - `../fins-template/docs/shoal-cli-fin-integration-handoff.md`

## Current Capabilities (End-to-End)

### Discovery

- Path-based discovery is available now:
  - `shoal fin ls [--path <dir-or-fin.toml>]`
  - `shoal fin inspect <fin-path>`
  - `shoal fin install <fin-path>`
  - `shoal fin configure <fin-path> [--config <path>]`
  - `shoal fin validate <fin-path> [--strict]`
  - `shoal fin run <fin-path> [--config <path>] [--output text|json] -- [args...]`
- Registry/distribution discovery is not implemented yet (`fin install` from sources is pending).

### Loading and Validation

- Manifest parsing and schema validation for contract-v1 are implemented.
- Entry points are resolved to absolute paths under fin root.
- Shoal validates that each invoked entrypoint exists and is executable.
- Contract-version mismatch fails fast with a user-facing error.

### Runtime Lifecycle

- Shoal invokes fin wrappers as subprocesses (cwd = fin root).
- Environment handshake for run/validate includes:
  - `SHOAL_LOG_LEVEL` (when available)
  - `SHOAL_FIN_ROOT` (required)
  - `SHOAL_FIN_CONFIG` (optional)
  - `SHOAL_OUTPUT_FORMAT` (`text` or `json`)
- Install/configure lifecycle commands use the same subprocess/env/exit behavior.
- `run` pass-through behavior preserves arguments after `--` in-order.
- Policy: `run` does not require prior `validate`; validation is recommended but not enforced.
- Fin non-zero exits propagate back to CLI as non-zero exit codes.

### Developer Ergonomics

- `inspect` returns contract version, capability, and resolved entrypoints.
- `validate --strict` forwards strict mode to fin wrappers.
- Runtime failures are reported as actionable CLI errors.

## Known Gaps

1. **Discovery/packaging gaps**
   - No registry or install source management yet.
2. **Hook integration gaps**
   - No first-class lifecycle hook package loading for fins.
3. **Isolation and trust model gaps**
   - No sandboxing/permission boundary beyond subprocess execution.
4. **Compatibility policy gaps**
   - No explicit N/N-1 fin contract support policy yet.

## Boundary Recommendation

### `shoal-cli` owns

- Human-facing command UX and help semantics.
- Fin discovery UX (path-based now; registry UX later).
- Invocation routing from command to contract entrypoint.
- Human-readable diagnostics and output formatting.

### `shoal-core` owns

- Contract schema and version compatibility logic.
- Lifecycle execution semantics and exit-code guarantees.
- Machine-oriented validation and error taxonomy.
- Backward-compat migration policy for contract versions.

## Milestone 1: Minimal Fin Contract Hardening

Goal: make contract-v1 reliable enough for early external fin authors.

Scope:

- Keep v1 parsing/execution stable (inspect/validate/run).
- Add contract tests for malformed manifests and exit-code propagation.
- Add explicit docs for unsupported surfaces (`install/configure`, registry).
- Publish initial version policy (v1 only) and migration intent for v2.

Out of scope:

- Marketplace/distribution.
- Multi-fin dependency resolution.
- Sandboxing beyond subprocess isolation.

## Pisces Compatibility Notes

- Treat Pisces-facing behavior as adapter-only for now (no hard dependency in contract).
- Avoid introducing contract fields that require Pisces internals.
- Keep status/lifecycle integration stable through existing Shoal event and MCP surfaces.
