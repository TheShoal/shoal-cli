# Remote Sessions Guide

Monitor and control Shoal agents running on remote machines via SSH tunnel.

## Overview

Remote sessions let you manage AI coding agents on any SSH-accessible machine from your local terminal. Shoal opens an SSH tunnel to the remote host's API server, then proxies all commands through it. You get the same `shoal remote` CLI experience whether the agents are local or across the network.

**When to use remote sessions:**

- Running long overnight batch jobs on a powerful server
- Monitoring a fleet of agents across multiple machines
- Coordinating work between your laptop and a dev server

## Prerequisites

1. **SSH access** to the remote machine (key-based auth recommended)
2. **Shoal installed** on the remote machine
3. **API server running** on the remote machine (`shoal serve`)
4. **tmux running** on the remote machine with active Shoal sessions

## Quick Start

### 1. Configure a Remote Host

Add a host entry to `~/.config/shoal/config.toml`:

```toml
[remote.devbox]
host = "devbox.example.com"
api_port = 8000
```

### 2. Connect

```bash
shoal remote connect devbox
# Connected to devbox (localhost:54321 -> devbox.example.com:8000)
```

### 3. List Remote Sessions

```bash
shoal remote sessions devbox
```

### 4. Attach

```bash
shoal remote attach devbox my-session
```

This opens an SSH connection and attaches your terminal to the remote tmux session.

## Configuration

Remote hosts are configured in `~/.config/shoal/config.toml` under `[remote.<name>]` sections.

### Fields

| Field           | Type   | Default | Description                          |
|-----------------|--------|---------|--------------------------------------|
| `host`          | string | —       | Hostname or IP address (required)    |
| `api_port`      | int    | `8000`  | Port the Shoal API listens on        |
| `port`          | int    | `22`    | SSH port                             |
| `user`          | string | —       | SSH username (omit to use default)   |
| `identity_file` | string | —       | Path to SSH private key              |

### Examples

```toml
# Minimal
[remote.devbox]
host = "devbox.local"

# Full configuration
[remote.prod-server]
host = "10.0.1.50"
port = 2222
user = "deploy"
identity_file = "~/.ssh/prod_key"
api_port = 8080
```

### Multiple Hosts

```toml
[remote.laptop]
host = "macbook.local"

[remote.server]
host = "server.example.com"
user = "nick"
api_port = 8000

[remote.pi]
host = "192.168.1.100"
user = "pi"
port = 22
```

## Commands Reference

All remote commands are under the `shoal remote` subgroup.

### `shoal remote ls`

List all configured remote hosts and their connection status.

```bash
shoal remote ls
# Shows host name, address, ports, and connected/disconnected status

shoal remote ls --format plain
# Outputs host names one per line (for scripting)
```

### `shoal remote connect <host>`

Open an SSH tunnel to the remote host's API server.

```bash
shoal remote connect devbox
# Auto-selects a local port

shoal remote connect devbox --port 9000
# Use a specific local port
```

The tunnel runs in the background. It forwards `localhost:<port>` to the remote API.

### `shoal remote disconnect <host>`

Close the SSH tunnel to a remote host.

```bash
shoal remote disconnect devbox
```

### `shoal remote status <host>`

Show aggregate session status on the remote host (total, running, waiting, error, idle).

```bash
shoal remote status devbox
```

### `shoal remote sessions <host>`

List all sessions on the remote host with ID, name, tool, status, and branch.

```bash
shoal remote sessions devbox

shoal remote sessions devbox --format plain
# Outputs session names one per line (for scripting)
```

### `shoal remote send <host> <session> <keys>`

Send keystrokes to a session on the remote host.

```bash
shoal remote send devbox my-session "y"
shoal remote send devbox my-session "Enter"
```

### `shoal remote attach <host> <session>`

Attach your terminal to a remote tmux session via SSH.

```bash
shoal remote attach devbox my-session
```

This runs `ssh -t <host> tmux attach-session -t <prefix><session>` under the hood.

## Fish Integration

### `shoal-remote` Interactive Function

After running `shoal setup fish`, the `shoal-remote` function is available. It provides an fzf-based interactive workflow:

1. Lists configured remote hosts via fzf
2. Auto-connects the tunnel if not already connected
3. Lists remote sessions on the selected host via fzf
4. Attaches to the selected session

```fish
shoal-remote
# Pick a host -> auto-connect -> pick a session -> attach
```

## Workflows

### Monitoring a Remote Fleet

Check on all agents running on a server:

```bash
shoal remote connect server
shoal remote status server    # Quick overview
shoal remote sessions server  # Detailed session list
```

### Multi-Host Setup

Manage agents across multiple machines:

```bash
# Connect to all hosts
shoal remote connect laptop
shoal remote connect server

# Check status across fleet
shoal remote status laptop
shoal remote status server

# Send approval to a waiting agent
shoal remote send server auth-feature "y"
```

### Robo on Remote

Run a robo supervisor locally that controls agents on a remote machine:

```bash
# On remote: start agents
shoal new -t claude -w feat/auth -b

# Locally: connect and send instructions
shoal remote connect server
shoal remote send server feat/auth "implement the auth module"
```

## Troubleshooting

### Tunnel Won't Connect

```bash
# Verify SSH access works
ssh devbox echo "ok"

# Check if the API is running on the remote
ssh devbox curl -s http://localhost:8000/status

# Try connecting with verbose SSH
ssh -v -N -L 0:localhost:8000 devbox
```

### Connection Refused

The remote Shoal API server may not be running:

```bash
# On the remote machine
shoal serve &
# or
shoal serve --port 8080
```

### Permission Denied

- Check SSH key permissions: `chmod 600 ~/.ssh/id_rsa`
- Verify `user` field in config matches the remote user
- Ensure `identity_file` path is correct

### Tunnel Already Connected

```bash
# Check current status
shoal remote ls

# Force disconnect and reconnect
shoal remote disconnect devbox
shoal remote connect devbox
```

### Session Not Found

Session names are case-sensitive. List sessions to see exact names:

```bash
shoal remote sessions devbox
```

## See Also

- [Shoal Overview](index.md) — General documentation
- [Fish Integration Guide](FISH_INTEGRATION.md) — Fish shell setup
- [Robo Guide](ROBO_GUIDE.md) — Supervisor patterns
- [Architecture](architecture.md) — System design
