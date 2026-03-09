---
description: Take a full status snapshot of all shoal sessions and summarize what needs attention.
---

Run the following commands in sequence and collect their output:

```bash
shoal status
```

```bash
shoal ls
```

```bash
shoal diag
```

Then, for any session reported in `waiting` or `error` state, run:

```bash
shoal logs <session> -n 30
```

Replace `<session>` with each affected session name.

---

Once you have all output, produce a structured summary covering:

1. **Session counts** — how many sessions are in each state: `idle`, `running`, `waiting`, `error`, `stopped`.

2. **Sessions needing attention** — for each session in `waiting` or `error`:
   - Session name and current status
   - Last 30 lines of pane output (from `shoal logs`)
   - What likely caused the state (e.g. approval prompt, crash, config issue)

3. **Component health** — from `shoal diag` output:
   - Daemon status (running / not running)
   - tmux server status
   - MCP pool status
   - Any components reporting unhealthy

4. **Suggested next actions** — concrete commands the user can run to resolve issues, ordered by priority. Examples:
   - Resume a waiting session: `shoal send <session> "y"`
   - Restart a crashed session: `shoal restart <session>`
   - Kill and prune a stopped session: `shoal kill <session> && shoal prune`
   - Restart daemon if unhealthy: `shoal daemon restart`
