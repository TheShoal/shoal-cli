# SHOAL.md

## Purpose in the ecosystem

Shoal is the orchestration core. It coordinates parallel coding-agent sessions, worktrees, tool routing, and shared control-plane behaviors.

## Current state (medium-term snapshot)

- Maturity: high (feature-rich, production-like workflow coverage)
- Reality: core UX and architecture are strong, but tool status fidelity varies by backend
- Risk: capability sprawl without clear boundary docs for what belongs in Shoal vs external plugins/frameworks

## Tool strategy (2026 direction)

- Pi is the primary first-class agent backend for Shoal sessions.
- OpenCode remains supported for compatibility and migration, but status detection is best-effort.
- Fins/plugins are the preferred path for exposing additional agent runtimes and custom orchestration behavior.
- Goal: move status/lifecycle toward explicit tool event contracts (when available) and minimize regex-only scraping.

## Medium-term outcomes

- Stabilize extension boundaries for external components (Fins, Dotfiles, Periwinkle/Tidepool integrations)
- Keep a small, stable orchestration surface while evolving internals
- Formalize cross-repo integration contracts (session metadata, event hooks, MCP usage assumptions)
- Make Pi-backed sessions the reference implementation for accurate status transitions.
- Keep OpenCode integration stable without blocking Pi-forward architecture work.

## Integration points

- Consumes: local tool binaries and MCP servers
- Integrates with: Pisces (agent runtime), Tidepool/Periwinkle (knowledge and context tooling), Dotfiles (local defaults)
- Produces: session state, status, lifecycle events, and orchestration APIs for ecosystem tooling

## Public-readiness focus

- Make private operational assumptions explicit and optional
- Ensure docs describe stable external behaviors, not only implementation details
- Keep roadmap and architecture docs aligned with actual CLI behavior

## Next work (roadmap-aligned)

- Document current extension/plugin capabilities end-to-end (discovery, loading, runtime lifecycle, developer ergonomics).
- Identify concrete extension gaps, especially lifecycle hooks, isolation boundaries, and compatibility guarantees.
- Produce a recommendation for `shoal-cli` vs `shoal-core` responsibility boundaries with a phased migration sequence.
- Define the first milestone for extension system hardening and tie it to a minimal fin contract.
- Keep Pisces compatibility stable while extension boundaries are clarified.
- Add a status-provider abstraction so backend-specific adapters (Pi first, OpenCode compat) are explicit.
- Document degraded-status behavior for compatibility backends in CLI help/docs.

## Next planned review

- Revisit after extension capability map and CLI/core boundary recommendation are accepted.
