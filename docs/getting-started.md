# Getting Started

This path is optimized for a developer who wants Shoal working quickly and wants the next
documentation branch points to be obvious.

## Prerequisites

Shoal assumes a terminal-centric workflow and relies on a small set of system tools.

| Tool | Why it matters |
| ---- | -------------- |
| `uv` | Installs Shoal and manages the Python environment |
| `tmux` | Runs each agent in an isolated session or pane |
| `git` | Creates worktrees and branches safely |
| `fish` | Recommended reference shell for completions, key bindings, and helper functions |
| `fzf` | Enables interactive selection in commands like `shoal attach` |

Optional but useful:

- `gh` for `shoal wt finish --pr`
- `fish` if you want the intended shell ergonomics
- `nvr` for Neovim integration

## Install

### Recommended

```bash
uv tool install .
```

### With MCP support

```bash
uv tool install ".[mcp]"
```

### From source for development

```bash
git clone https://github.com/TheShoal/shoal-cli.git
cd shoal-cli
uv tool install -e ".[dev,mcp]"
uv tool install pre-commit
just setup
```

## Initialize Shoal

```bash
shoal init
shoal setup fish
```

`shoal init` creates the XDG config, state, and runtime directories, scaffolds bundled
tool and template files, and checks the local environment. `shoal setup fish` installs the
interactive shell integration on top of that baseline.

## Launch your first sessions

```bash
shoal new -t claude -w auth -b
shoal new -t codex -w api-refactor -b
shoal new -t gemini -w docs-refresh -b
```

What those flags do:

- `-t` selects the tool profile.
- `-w` names the worktree and session.
- `-b` creates a dedicated branch automatically.

## Check the fleet

```bash
shoal status
shoal popup
shoal attach auth
shoal ls --tree
```

Use `shoal status` for a fast summary, `shoal popup` for the interactive dashboard, and
`shoal attach` when you need to drop into a specific session directly.

## Common next steps

### You want better shell ergonomics

Read [Fish Integration](FISH_INTEGRATION.md).

### You want reusable session layouts

Read [Local Templates](LOCAL_TEMPLATES.md) and [Architecture](architecture.md#template-inheritance-and-composition).

### You want agents supervising other agents

Read [Robo Supervisor](ROBO_GUIDE.md).

### You want to drive remote machines

Read [Remote Sessions](REMOTE_GUIDE.md).

### You want troubleshooting first

Read [Troubleshooting](TROUBLESHOOTING.md).
