# Implementation Audit

This page captures a documentation-to-implementation review completed on 2026-03-06.

## Summary

The core command surface described by the docs is real and present: `shoal demo`, `shoal remote`,
`shoal setup fish`, journals, robo supervision, and the docs site itself all build against the
current codebase. The main issues found were not missing flagship features, but drift in the
human-facing contract around filesystem paths, shell assumptions, and contributor guidance.

## Findings resolved in this pass

### XDG path drift in top-level docs

- The code stores persistent state under `state_dir()`, which maps to `XDG_DATA_HOME`
  or `~/.local/share/shoal/`.
- The README previously described the database and MCP pool as living under
  `~/.local/state/shoal/`, which is the runtime directory instead.

Status: fixed in the docs.

### Fish integration claimed XDG support but printed a hardcoded source path

- The fish installer already respected `XDG_CONFIG_HOME`.
- The success message and several docs examples still hardcoded `~/.config/fish/conf.d/shoal.fish`.

Status: fixed in code and docs.

### Robo guide pointed users at the wrong storage root

- `shoal robo setup` creates `AGENTS.md` and `task-log.md` under
  `state_dir() / "robo" / <name>`, which resolves to `~/.local/share/shoal/robo/<name>/`.
- The guide previously taught `~/.local/state/shoal/robo/...`.

Status: fixed in the docs.

### Contributor onboarding had stale repo references

- Contributor-facing clone instructions still referenced an older repository path.
- `CONTRIBUTING.md` also referenced a `CODE_REVIEW.md` file that is not present.

Status: fixed in the docs.

## Claims verified directly against the implementation

### CLI surface

- `shoal demo` exposes `start`, `stop`, `tour`, and `tutorial`.
- `shoal remote` exposes `ls`, `connect`, `disconnect`, `status`, `sessions`, `send`, and `attach`.
- `shoal setup fish` exists and routes through the fish installer.

### Journals

- Journals are append-only Markdown files under `~/.local/share/shoal/journals/`.
- Archiving on session kill is implemented.
- MCP tools for `append_journal` and `read_journal` exist.

### Robo supervision

- Robo profile scaffolding writes config under `~/.config/shoal/robo/`.
- Robo working files are created under `~/.local/share/shoal/robo/`.
- Robo daemon logs and PID files live under `~/.local/state/shoal/`.

## Remaining design truth

Shoal is fish-first in experience, but not fish-hard-required in the core control plane. The docs
now reflect that distinction more clearly:

- Core orchestration works without fish.
- The intended shell ergonomics and flow-state UX assume fish.
