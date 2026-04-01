# Shoal Features

Shoal provides the control plane for parallel coding agents.

## Core Capabilities

- **Worktree Isolation**: Spins up temporary git worktrees to keep complex multi-agent parallel operations independent and clean.
- **Tmux Session Management**: Provides deterministic terminal interfaces attached to each generated worktree.
- **Parallel Operation Pipelines**: Launch multiple agents in tandem to independently traverse, code, test, and merge into branches.
- **Chronological Status Parsing**: Regex evaluations and monitoring logic capture status updates directly via standard out logic without tightly coupling codebases.
- **MCP Server Validation**: Advanced name validation techniques to safely map to system processes.
- **Watcher Lock Protocol**: Reliable file watcher protocols.

## Agent Teams & Journal Dreaming

- **Subagent Coordination**: Safely orchestrates massive scale tasks across overlapping repositories dynamically by mapping `$SHOAL_PANE_ID`, enforcing isolation with `git worktree add`, and disabling direct inter-agent polling to prevent loops. Automatically merges and drops squashed branches via `shoal.services.coordinator`.
- **Dreamer Observer Pane**: Actively condenses large memory streams, episodic DB traces from SQLite WAL, and fast-flowing Tmux chunks down to structured `'/Users/ricardoroche/.omp/agent/memories/--Users-ricardoroche-sanctum-opus-proprium-the-shoal-shoal-cli--/memory_summary.md'` and `context.md` files passively. Implemented securely through `shoal.services.dreamer`.

