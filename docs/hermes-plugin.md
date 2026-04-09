# Hermes Plugin

Shoal ships a [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that exposes the Shoal HTTP API as native Hermes tools and injects session context into each LLM turn.

## Install

```bash
mkdir -p ~/.hermes/plugins/shoal
# Plugin ships with Shoal — copy from the installed package:
cp -r "$(python -c 'import shoal; import pathlib; print(pathlib.Path(shoal.__file__).parent)')"/../../../hermes/plugins/shoal/ ~/.hermes/plugins/shoal/
```

Or install manually by copying from the repo:

```bash
cp ~/.hermes/plugins/shoal/plugin.yaml ~/.hermes/plugins/shoal/__init__.py
```

The plugin files are also shipped at `~/.hermes/plugins/shoal/` after running `shoal setup`.

## Requirements

- `httpx` must be available in the Hermes venv (`pip install httpx`). If missing, all tools return unavailable via `check_fn`.
- Shoal API must be running (`shoal api start` or via `shoal-orchestrator`).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SHOAL_SESSION` | — | Session name/ID. Enables `pre_llm_call` context injection. |
| `SHOAL_PORT` | `8080` | Port the Shoal HTTP API listens on. |

## Tools

All tools are gated behind a `check_fn` — they only appear in `hermes tools` when the Shoal API is reachable. They are grouped under the `shoal` toolset.

| Tool | Method | Description |
|---|---|---|
| `shoal_list_sessions` | GET `/sessions` | List sessions. Optional `path` filter by git root. |
| `shoal_session_status` | GET `/sessions/{id}` | Status and details for one session. |
| `shoal_create_session` | POST `/sessions` | Create a session. Params: `name`, `tool?`, `template?`, `prompt?`, `model?`. |
| `shoal_kill_session` | DELETE `/sessions/{id}` | Kill a session and clean up its worktree. |
| `shoal_send_keys` | POST `/sessions/{id}/send` | Send keystrokes to a session's tmux pane. |
| `shoal_heartbeat` | POST `/sessions/{id}/heartbeat` | Push a status update. Values: `running`, `waiting`, `idle`, `error`. |

## `pre_llm_call` Hook

When `SHOAL_SESSION` is set, the hook fetches the session from the API and prepends a context line to the current turn:

```
[Shoal context] session=my-session | tool=omp | status=waiting | branch=feat/auth | worktree=/repo/.worktrees/auth
```

Silent-fails if the API is unreachable or the session is not found — no disruption to the Hermes loop.

## Hermes as an external supervisor

With the plugin active, Hermes can act as a scheduling layer above Shoal:

```
Hermes (scheduler + cron) → shoal_list_sessions / shoal_create_session / shoal_send_keys
                          → Shoal (execution control plane)
                          → omp / Claude Code / OpenCode sessions
```

!!! warning "Experimental"
    Bounded team spawning and write operations remain experimental. Start with read-only fleet digests (`shoal_list_sessions`, `shoal_session_status`) and validate the round-trip before enabling session creation.
