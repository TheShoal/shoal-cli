# Shoal Heartbeat Hooks

Hooks that allow AI agents to push status updates to the Shoal API at the end of
every turn and when the agent finishes.  All hooks are silent-fail — heartbeat
errors never disrupt the agent.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOAL_SESSION` | Yes | — | Shoal session name or ID. Hook is a no-op if unset. |
| `SHOAL_PORT` | No | `8080` | Port the Shoal HTTP API listens on. |

---

## omp Heartbeat Extension (`omp_heartbeat.ts`)

For [oh-my-pi (omp)](https://github.com/can1357/oh-my-pi) agents.

### Install

Copy or symlink the extension into your Shoal config directory:

```bash
mkdir -p ~/.config/shoal/hooks
cp src/shoal/integrations/hooks/omp_heartbeat.ts ~/.config/shoal/hooks/
```

Then register it in `~/.omp/agent/config.yml`:

```yaml
extensions:
  - ~/.config/shoal/hooks/omp_heartbeat.ts
```

### What it does

- **`onTurnEnd`** — fires after each turn, pushes `status=waiting`
- **`onAgentEnd`** — fires when the agent exits, pushes `status=stopped`

Both events include an optional `summary` (truncated to 200 chars).

---

## Claude Code Heartbeat Hook (`claude_heartbeat.sh`)

For [Claude Code](https://claude.ai/code) sessions.

### Install

Register in `~/.claude/settings.json` (see `claude_settings_snippet.json` for the
exact snippet to add):

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "~/.config/shoal/hooks/claude_heartbeat.sh" }] }
    ]
  }
}
```

Copy the script:

```bash
mkdir -p ~/.config/shoal/hooks
cp src/shoal/integrations/hooks/claude_heartbeat.sh ~/.config/shoal/hooks/
chmod +x ~/.config/shoal/hooks/claude_heartbeat.sh
```

---

## Legacy: Pisces Heartbeat Hook (`shoal_heartbeat.ts`)

The original Pisces-era hook.  Uses port **8484** (Pisces API) instead of **8080**
(Shoal API).  Kept for backward compatibility with existing Pisces configurations.

For new setups, use `omp_heartbeat.ts` instead.
