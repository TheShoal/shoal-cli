# Agent Reference

Shoal maintains first-class support for three agents. This document records their actual CLI surfaces — flags, input modes, session continuity, and MCP wiring — so that Shoal's tool profiles, prompt dispatch, and documentation stay accurate.

**Scope:** interactive (TUI) startup, initial prompt delivery, session continuation, MCP configuration, and permission/non-interactive modes.  
**Not covered:** every flag each tool exposes — only what Shoal needs to interact with.

---

## Prompt delivery overview

Shoal uses each tool's native input mechanism for initial session prompts rather than a generic `send_keys` post-launch sequence. The mechanism is configured via `input_mode` in the tool profile:

| `input_mode` | Mechanism | Tools |
|---|---|---|
| `"keys"` | `send_keys` after launch (legacy fallback) | unknown/custom tools, mid-session turns |
| `"arg"` | Positional CLI argument at launch; if `prompt_file_prefix` is set, writes to `~/.local/share/shoal/prompts/<name>.md` first | `claude`, `omp`, `pi` |
| `"flag"` | Named flag (`prompt_flag`) at launch | `opencode` |

Implementation: `src/shoal/core/prompt_delivery.py` — `build_tool_command_with_prompt()` and `write_prompt_file()`.

Prompt files written to disk are **never deleted** — they serve as an audit trail.

---

## claude (Claude Code)

**Binary:** `claude`  
**Install:** `npm install -g @anthropic-ai/claude-code`  
**Default mode:** Interactive TUI  
**Shoal tool profile:** `~/.config/shoal/tools/claude.toml`

### Startup

```sh
# Interactive TUI, no initial prompt
claude

# Interactive TUI with initial prompt (positional argument)
claude "Fix the failing tests"

# Non-interactive: print response and exit
claude -p "Summarise this file"
claude --print "Summarise this file"

# Continue the most recent session
claude --continue
claude -c

# Resume a specific session by ID (or opens picker)
claude --resume <session-id>
claude -r

# Skip all permission prompts (for agent use in sandboxes)
claude --dangerously-skip-permissions

# Bypass permissions as an option (safer — user can still approve)
claude --allow-dangerously-skip-permissions
```

### Delivering an initial prompt

The positional argument is the only supported mechanism for passing a startup prompt in TUI mode. There is **no `--prompt-file` or stdin prompt** for interactive sessions.

```sh
# Correct — positional arg
claude "Implement feature X per ROADMAP.md"

# Non-interactive stdin (pipe) — works only with -p
echo "Summarise the API" | claude -p --input-format text
```

> **Shoal implication:** `create_session` passes the initial prompt as a positional argument at launch time (`input_mode = "arg"` in the tool profile). This eliminates the post-launch `send_keys` race for initial prompts. Mid-session interactions still use `send_keys`. No file mechanism is used for `claude`; the prompt is inlined directly into the launch command via `shlex.quote`.

### `--file` flag — not a prompt file

`--file <file_id>:<path>` downloads a remote file resource to the worktree at startup. It is **not** a way to pass a prompt from disk. Do not confuse it with `omp`'s `@file` syntax.

### Session continuity

| Flag | Behaviour |
|---|---|
| `-c` / `--continue` | Resumes the most recent session in the current directory |
| `-r` / `--resume [id]` | Opens picker or resumes by session ID |
| `--fork-session` | Creates a new session ID when used with `--resume`/`--continue` |

Sessions are stored on disk by Claude Code; Shoal does not manage them directly.

### MCP

```sh
# Register an MCP server (used by shoal mcp attach)
claude mcp add <name> <command> [args...]

# List configured MCP servers
claude mcp list

# Remove a server
claude mcp remove <name>
```

Config is stored in Claude Code's own config directory (`~/.config/claude/`).  
Shoal's `config_cmd = "claude mcp add"` in the tool profile drives `shoal mcp attach`.

### Permission mode

For fully autonomous agent sessions (no human at the terminal):

```sh
claude --dangerously-skip-permissions "Do the work"
```

Shoal sets `SHOAL_AGENT=1` in agent sessions to bypass pre-commit hooks; coupling it with `--dangerously-skip-permissions` in the tool command is the recommended pattern for unattended robo sessions.

---

## omp (oh-my-pi)

**Binary:** `omp`  
**Install:** `bun install -g @oh-my-pi/pi-coding-agent`  
**Source:** <https://github.com/can1357/oh-my-pi>  
**Default mode:** Interactive TUI  
**Shoal tool profile:** `~/.config/shoal/tools/omp.toml`

### Startup

```sh
# Interactive TUI, no initial prompt
omp

# Interactive TUI with initial prompt (positional arguments)
omp "List all .ts files in src/"

# Attach file contents inline in the initial message
omp @prompt.md "Implement this spec"
omp @ROADMAP.md @src/core/tmux.py "Explain the send_keys flow"

# Non-interactive: process prompt and exit
omp -p "List all .ts files in src/"
omp --print "List all .ts files in src/"

# Continue the most recent session
omp --continue
omp -c

# Resume a specific session (by ID prefix, path, or picker)
omp --resume
omp -r
omp --resume <id-prefix>
omp --resume <path/to/session.jsonl>
```

### Delivering an initial prompt

Positional arguments are the prompt. The `@file` prefix is the native way to inject file contents inline — it is expanded by `omp` before the LLM sees the message.

```sh
# Pass a markdown spec as context alongside a directive
omp @spec.md "Implement this"

# Equivalent for non-interactive use
omp -p @spec.md "Implement this"
```

There is **no `--prompt-file` flag**. The `@file` expansion works for any positional argument, so writing a prompt to a temp file and passing it as `@/tmp/shoal-prompt-<id>.md` is a viable pattern for audit-trailed prompt delivery:

```sh
# Shoal writes prompt to tmp file, agent reads it via @ expansion
omp "@/tmp/shoal-abc123.md"
```

This is the **recommended file-based input mechanism** for `omp`. The file is kept on disk as an audit trail; Shoal is responsible for writing it before session launch.

> **Shoal implication:** `create_session` writes the prompt to `~/.local/share/shoal/prompts/<session-name>.md` and passes `@<path>` as the startup argument (`input_mode = "arg"`, `prompt_file_prefix = "@"` in the tool profile). This eliminates the Enter-racing problem entirely for initial prompts. The file is kept on disk as an audit trail. Mid-session `send_keys` still applies for interactive turns. Robo escalation uses the same file-path mechanism to avoid garbling long multi-line prompts.

### Session continuity

| Flag | Behaviour |
|---|---|
| `-c` / `--continue` | Resumes the most recent session |
| `-r` / `--resume [id]` | Opens picker or resumes by ID prefix or path |
| `--no-session` | Ephemeral mode — session is not saved to disk |
| `--session-dir <dir>` | Override storage location |

Sessions are stored as JSONL under `~/.omp/agent/sessions/` (grouped by working directory).

### MCP

`omp` uses config files rather than a registration CLI. Add servers to:

- `~/.omp/agent/config.yml` (user-level)
- `.omp/config.yml` (project-level)

```yaml
mcpServers:
  memory:
    type: stdio
    command: memory-server
    args: []
```

Shoal's `config_cmd = ""` and `config_file` in the tool profile reflect that there is no single-command registration path. Use a template or startup command to pre-populate the config file.

---

## opencode

**Binary:** `opencode`  
**Install:** See <https://opencode.ai/docs>  
**Default mode:** Interactive TUI  
**Shoal tool profile:** `~/.config/shoal/tools/opencode.toml`

### Startup

```sh
# Interactive TUI, no initial prompt
opencode

# Interactive TUI in a specific directory
opencode /path/to/project

# Interactive TUI with initial prompt (--prompt flag)
opencode --prompt "Fix the failing tests"

# Non-interactive: run with a message and exit
opencode run "Fix the failing tests"
opencode run --continue "What did we do?"

# Attach files to the message in run mode
opencode run -f spec.md -f notes.txt "Implement this"
opencode run --file spec.md "Implement this"

# Continue the most recent session
opencode --continue
opencode -c

# Resume a specific session by ID
opencode --session <session-id>
opencode -s <session-id>

# Fork when continuing
opencode --continue --fork
```

### Delivering an initial prompt

Two mechanisms are available depending on the mode:

```sh
# TUI mode — --prompt is sent as the first message after launch
opencode --prompt "Implement feature X"

# Non-interactive — positional args to `run`
opencode run "Implement feature X"

# Non-interactive with file attachments
opencode run -f /tmp/shoal-prompt.txt "See attached"
```

The `run -f` flag attaches files as message context, not as a replacement for the prompt text. There is no TUI-mode `--file` equivalent that reads a prompt from disk.

> **Shoal implication:** `create_session` passes `--prompt "..."` at launch time (`input_mode = "flag"`, `prompt_flag = "--prompt"` in the tool profile), avoiding `send_keys` entirely for session startup. Mid-session interactions still use `send_keys`.

### Session continuity

| Flag | Behaviour |
|---|---|
| `-c` / `--continue` | Resumes the most recent session |
| `-s` / `--session <id>` | Resumes a specific session by ID |
| `--fork` | Forks the session when continuing |

### MCP

`opencode` uses a JSON config file:

- `.opencode.json` (project-level, preferred)
- `~/.config/opencode/opencode.json` (user-level)

```json
{
  "mcp": {
    "memory": {
      "type": "local",
      "command": "memory-server",
      "args": []
    }
  }
}
```

Shoal's `config_file = ".opencode.json"` in the tool profile is used by `shoal mcp attach` to write server entries into this file.

---

## Summary table

| | claude | omp | opencode |
|---|---|---|---|
| **Binary** | `claude` | `omp` | `opencode` |
| **TUI initial prompt** | positional arg | positional arg | `--prompt` flag |
| **File-based prompt** | not supported in TUI | `@/path/to/file.md` (native) | not supported in TUI |
| **Non-interactive** | `-p` / `--print` | `-p` / `--print` | `opencode run` |
| **Session continue** | `-c` / `--continue` | `-c` / `--continue` | `-c` / `--continue` |
| **Session resume** | `-r` / `--resume [id]` | `-r [id-prefix\|path]` | `-s <id>` |
| **MCP config** | `claude mcp add` (CLI) | `config.yml` (file) | `.opencode.json` (file) |
| **Skip permissions** | `--dangerously-skip-permissions` | n/a | n/a |
| **Status provider** | `regex` | `pi` | `opencode_compat` |
| **Auto-enter (send_keys)** | yes | yes | no |
| **Shoal `input_mode`** | `"arg"` | `"arg"` + `prompt_file_prefix="@"` | `"flag"` + `prompt_flag="--prompt"` |

---

## Maintenance notes

This document must be updated whenever:

- A tool releases a new version that changes the flags above
- Shoal adds or changes how it invokes a tool (tool profile `command`, `config_cmd`, `config_file`)
- A new primary agent is added to the supported set

The source of truth for each tool's flags is `<tool> --help`. Verified against:

- `claude` (Claude Code) — checked 2026-03-07
- `omp` v13.9.2 (oh-my-pi) — checked 2026-03-07  
- `opencode` — checked 2026-03-07
