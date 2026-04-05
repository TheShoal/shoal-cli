# Security Policy

## Overview

Shoal is a local-first, single-user orchestration tool. It runs entirely on your machine and does not transmit data to external services unless you explicitly configure a remote host or external provider.

## Threat model

| Surface | Notes |
|---------|-------|
| SQLite database | Stored at `$XDG_DATA_HOME/shoal/shoal.db`. No network exposure. |
| Unix sockets | MCP pool sockets in `$XDG_STATE_HOME/shoal/mcp-pool/sockets/`. Local only. |
| FastAPI server | Binds to `localhost` by default. Do not expose to the network without auth. |
| SSH tunnels | Remote sessions use SSH — standard SSH security model applies. |
| External providers | Optional integrations you configure are your responsibility to authenticate and secure. |
| Dreamer LLM | Optional. If using AWS Bedrock, standard IAM auth applies. No data sent without config. |

## Reporting vulnerabilities

Report security issues via [GitHub Issues](https://github.com/TheShoal/shoal-cli/issues) with the `security` label.

There is no formal bug bounty program. This is a personal workflow tool with a small user base.

## Known limitations

- No authentication on the FastAPI server — do not expose it to untrusted networks
- Session names and journal content are stored in plaintext in SQLite
- MCP tool `read_worktree_file` has path traversal protection, but only within the worktree

## Security scanning

The CI pipeline runs `bandit` on every push (`just security`). No known CVEs in the current dependency set.
