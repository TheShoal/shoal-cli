---
description: Create a new shoal session template for a described workflow.
---

You are creating a new shoal session template. Before generating anything, ask the user:

1. What is the workflow this template is for? (brief description)
2. Which tool should the session use? Options: `pi`, `claude`, `omp`, `opencode`, `codex`
3. Should it extend a base template? Options: `base-dev`, `pi-dev`, `claude-dev`, `codex-dev`, `robo-orchestrator` (or none)
4. Should it mix in any other templates? (list names, or none)
5. Which MCP servers should be available? (list names, or none)
6. What env vars does the session need? (KEY=VALUE pairs, or none)
7. Any setup commands to run before agent launch? (e.g. `uv sync`, `npm install`, or none)

---

## Session template schema — complete shape

Templates are TOML files stored in `~/.config/shoal/templates/`.

```toml
name        = "<template-name>"
description = "One line description of what this template is for."

# Optional: inherit from a single parent template (scalars: child wins if set)
extends = "base-dev"

# Optional: additive mixins (env merged in, mcp union, windows appended)
mixins = ["some-mixin"]

# Required: tool reference → ~/.config/shoal/tools/<tool>.toml
tool = "pi"

# Optional: MCP servers to attach (union-dedup'd with parent/mixins)
mcp = ["filesystem", "memory"]

# Optional: env vars injected into the session
[template.env]
MY_VAR = "value"
ANOTHER = "value"

# Optional: shell commands sent to the pane before the agent launches
setup_commands = [
    "uv sync",
    "source .env",
]
```

### Available tools

| Name | Description |
|---|---|
| `pi` | Oh My Pi (OMP) — event-based status, most accurate |
| `claude` | Claude CLI |
| `omp` | OMP variant |
| `opencode` | OpenCode — use `opencode_compat` status provider |
| `codex` | OpenAI Codex CLI |

Tool definitions live in `~/.config/shoal/tools/`.

### Base templates

| Name | Use case |
|---|---|
| `base-dev` | Minimal base, no tool assumption |
| `pi-dev` | OMP/pi sessions |
| `claude-dev` | Claude sessions |
| `codex-dev` | Codex sessions |
| `robo-orchestrator` | Orchestrator sessions that spawn sub-agents |

### Merge semantics

**`extends`** (single parent, hierarchical):
- Scalars: child wins if set, parent fills gaps
- `env`: parent + child merged, child key wins on conflict
- `mcp`: union, deduped
- `windows`: child replaces entirely if child defines any

**`mixins`** (list, additive, applied after extends):
- `env`: mixin wins on conflict
- `mcp`: union, deduped
- `windows`: appended to existing windows

---

## After generating the template

1. Show where to save it:
   ```
   ~/.config/shoal/templates/<name>.toml
   ```

2. Test the resolved template (shows the final merged result):
   ```bash
   shoal template show <name>
   ```

3. Create a session from it:
   ```bash
   shoal new <session-name> --template <name>
   ```
