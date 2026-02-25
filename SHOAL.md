# SHOAL.md

## Purpose in the ecosystem

Shoal is the orchestration core. It coordinates parallel coding-agent sessions, worktrees, tool routing, and shared control-plane behaviors.

## Current state (medium-term snapshot)

- Maturity: high (feature-rich, production-like workflow coverage)
- Reality: core UX and architecture are strong, but integration contracts with sibling repos are still implicit
- Risk: capability sprawl without clear boundary docs for what belongs in Shoal vs external plugins/frameworks

## Medium-term outcomes

- Stabilize extension boundaries for external components (Fins, Dotfiles, Periwinkle/Tidepool integrations)
- Keep a small, stable orchestration surface while evolving internals
- Formalize cross-repo integration contracts (session metadata, event hooks, MCP usage assumptions)

## Integration points

- Consumes: local tool binaries and MCP servers
- Integrates with: Pisces (agent runtime), Tidepool/Periwinkle (knowledge and context tooling), Dotfiles (local defaults)
- Produces: session state, status, lifecycle events, and orchestration APIs for ecosystem tooling

## Public-readiness focus

- Make private operational assumptions explicit and optional
- Ensure docs describe stable external behaviors, not only implementation details
- Keep roadmap and architecture docs aligned with actual CLI behavior

## Next planned review

- Revisit after next integration milestone across Driftwood Template/Tidepool/Fins
