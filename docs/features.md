# Shoal Features

Shoal provides the control plane for parallel coding agents.

## Core Capabilities

- **Worktree Isolation**: Spins up temporary git worktrees to keep complex multi-agent parallel operations independent and clean.
- **Tmux Session Management**: Provides deterministic terminal interfaces attached to each generated worktree.
- **Parallel Operation Pipelines**: Launch multiple agents in tandem to independently traverse, code, test, and merge into branches.
- **Chronological Status Parsing**: Regex evaluations and monitoring logic capture status updates directly via standard out logic without tightly coupling codebases.
- **MCP Server Validation**: Advanced name validation techniques to safely map to system processes.
- **Watcher Lock Protocol**: Reliable file watcher protocols.
