# CLI Reference

Shoal is a Typer-based CLI with a small set of top-level session commands and feature-specific
subcommand groups.

## Top-level commands

| Command | Purpose |
| ------- | ------- |
| `shoal new` | Create a new session, optionally with a worktree and branch |
| `shoal ls` | List sessions, with filters like `--tree` and `--tag` |
| `shoal info` | Show detailed metadata for one session |
| `shoal attach` | Jump into a session |
| `shoal logs` | Read recent terminal output |
| `shoal status` | Show a quick fleet summary |
| `shoal popup` | Open the tmux dashboard |
| `shoal history` | Show status transition history |
| `shoal journal` | Read or append to a session journal |
| `shoal diag` | Check component health |
| `shoal init` | Scaffold config and state directories |
| `shoal check` | Re-run dependency and environment checks |
| `shoal serve` | Start the FastAPI server for HTTP access |

Hidden aliases exist for speed, including `a` for `attach`, `rm` for `kill`, and `pop` for `popup`.

## Session lifecycle

```bash
shoal new -t claude -w auth -b
shoal fork auth review-auth
shoal rename review-auth review-api
shoal kill review-api
shoal prune
```

Use `new` when you are starting fresh, `fork` when you need lineage from an existing session,
and `prune` to clear stopped sessions from the database after cleanup.

## Worktrees

| Command | Purpose |
| ------- | ------- |
| `shoal wt ls` | List Shoal-managed worktrees |
| `shoal wt finish` | Merge, optionally open a PR, and clean up a worktree |
| `shoal wt cleanup` | Remove stale Shoal worktrees |

## MCP pool

| Command | Purpose |
| ------- | ------- |
| `shoal mcp ls` | List configured MCP servers |
| `shoal mcp start` | Start the shared MCP pool |
| `shoal mcp stop` | Stop pool processes |
| `shoal mcp attach` | Attach a server to a session |
| `shoal mcp status` | Inspect runtime state |
| `shoal mcp logs` | Read server logs |
| `shoal mcp doctor` | Run protocol-level diagnostics |
| `shoal mcp registry` | Inspect transport and registry data |

## Robo automation

| Command | Purpose |
| ------- | ------- |
| `shoal robo setup` | Create or update robo profile scaffolding |
| `shoal robo start` | Start a robo worker session |
| `shoal robo stop` | Stop a robo worker |
| `shoal robo send` | Send instructions to robo |
| `shoal robo approve` | Approve a pending action |
| `shoal robo status` | Inspect a robo worker |
| `shoal robo ls` | List robo workers |
| `shoal robo watch` | Start supervision loop |
| `shoal robo watch-stop` | Stop watcher mode |
| `shoal robo watch-status` | Check watcher health |

For patterns and safety rules, read [Robo Supervisor](ROBO_GUIDE.md).

## Remote control

| Command | Purpose |
| ------- | ------- |
| `shoal remote connect` | Open an SSH tunnel to a remote host |
| `shoal remote disconnect` | Tear down the tunnel |
| `shoal remote status` | Inspect the remote control-plane state |
| `shoal remote sessions` | List sessions on a remote host |
| `shoal remote send` | Send keys to a remote session |
| `shoal remote attach` | Attach to a remote session |

## Templates, tags, and config

| Command | Purpose |
| ------- | ------- |
| `shoal template ls` | List available templates |
| `shoal template show` | Render an expanded template |
| `shoal template validate` | Validate a template file |
| `shoal template mixins` | List mixins available to templates |
| `shoal tag add` | Add a tag to a session |
| `shoal tag remove` | Remove a tag from a session |
| `shoal tag ls` | List tags for sessions |
| `shoal config show` | Render merged configuration |
| `shoal config paths` | Show config, state, and runtime paths |

## Extensions and integrations

| Command | Purpose |
| ------- | ------- |
| `shoal fin inspect` | Inspect a fin manifest |
| `shoal fin validate` | Validate a fin package |
| `shoal fin install` | Run fin install entrypoint |
| `shoal fin configure` | Run fin configure entrypoint |
| `shoal fin ls` | Discover fins |
| `shoal fin run` | Execute a fin |
| `shoal nvim send` | Send content to Neovim |
| `shoal nvim diagnostics` | Inspect Neovim integration |
| `shoal watcher start` | Start background status watcher |
| `shoal watcher stop` | Stop watcher |
| `shoal watcher status` | Check watcher status |
| `shoal demo ...` | Launch or step through the guided demo |

## Recommended operator flow

1. Run `shoal init` on a fresh machine.
2. Use `shoal new` or `shoal fork` to create isolated sessions.
3. Monitor the fleet with `shoal status` or `shoal popup`.
4. Add `shoal mcp`, `shoal robo`, or `shoal remote` only when the base loop is stable.
