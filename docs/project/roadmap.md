# Roadmap

The canonical roadmap lives in [ROADMAP.md](https://github.com/TheShoal/shoal-cli/blob/main/ROADMAP.md) in the repository root.

## Milestone summary

| Version | Theme | Status |
|---------|-------|--------|
| v0.15.0 | FastMCP integration, `shoal-orchestrator` MCP server | Released |
| v0.16.0 | Remote sessions via SSH tunnel | Released |
| v0.17.0 | Demo overhaul, diagnostics, observability | Released |
| v0.18.0 | Lifecycle hooks, robo supervisor, session graph | Released |
| v0.19.0 | XDG compliance, branch naming, archived journals | Released |
| v0.20.0 | `setup_commands`, agent readiness, batch MCP ops | Released |
| v0.21.0 | PyPI publish (`shoal-cli`), trusted publisher | Released |
| v0.22.0 | Auto-commit on kill, dashboard fzf actions | Released |
| v0.23.0 | Urgency tiers, attention-first `shoal status` | Released |
| v0.24.0 | Worker completion signals, git MCP tools | Released |
| v0.25.0 | Runtime provider abstraction, `SessionState.runtime` | Released |
| v0.26.0 | Incident supervision, project-local hooks | Released |
| v0.27.0 | Meta-repo workspace routing, handoff packets, modes | Released |
| v0.28.0 | Fleet demo, skills, `.shoal.toml`, cross-agent skill setup | Released |
| v0.29.0 | MCP robo tools, PyApp binary, omp as default tool | Released |
| v0.30.0 | Lobster/Claw runtime provider, A2A bridge | Released |
| v0.34.0 | Web dashboard (`/ui`) | Released |
| v0.35.0 | Dashboard JSON API, Pisces tool support | Released |
| v0.36.0 | Proactive assistance (Dreamer, FsWatcher, Agent Bus, KAIROS) | Released |
| v0.37.0 | Agent Bus enrichment, QMD memory, Lobster rename | Released |
| v0.37.2 | FsWatcher+ProactiveSupervisor tests, pre-commit hook profile | Released |
| v1.0.0 | Stable public surface for personal-first workflows | Planned |

## Active backlog

- **Live Lobster gRPC validation**: end-to-end smoke test against a real Lobster endpoint
- **Server Composition Gateway**: per-session MCP aggregation via FastMCP `mount()` — deferred pending UDS transport support
- **direnv/mise integration**: opt-in `env_manager` field on templates (explicit opt-in only)

See the full [ROADMAP.md](https://github.com/TheShoal/shoal-cli/blob/main/ROADMAP.md) for session handoff notes and detailed milestone history.
