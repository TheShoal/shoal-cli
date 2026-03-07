<div class="shoal-page-head" data-icon="launch">
  <p class="shoal-eyebrow">Start Here</p>
  <p class="shoal-page-lede">
    Follow this path when you want Shoal installed quickly and you want the next branching docs
    choices to stay obvious.
  </p>
</div>

# Getting Started

This path is optimized for a developer who wants Shoal working quickly and wants the next
documentation branch points to be obvious.

<div class="shoal-step-grid">
  <div class="shoal-step" data-icon="stack">
    <strong>Check the toolchain</strong>
    <p>Confirm `uv`, `tmux`, and `git` are available before you start layering templates and shells.</p>
  </div>
  <div class="shoal-step" data-icon="launch">
    <strong>Install the CLI</strong>
    <p>Use `uv tool install .` for the fast path or the development extras if you are working from source.</p>
  </div>
  <div class="shoal-step" data-icon="map">
    <strong>Initialize the control plane</strong>
    <p>Run `shoal init` and `shoal setup fish` to scaffold state, config, and the intended shell ergonomics.</p>
  </div>
  <div class="shoal-step" data-icon="control">
    <strong>Launch and supervise</strong>
    <p>Create the first worktrees, then use `shoal status`, `shoal popup`, and `shoal attach` to operate them.</p>
  </div>
</div>

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

### From PyPI (recommended)

```bash
pipx install shoal-cli

# or with uv
uv tool install shoal-cli

# With MCP support (enables shoal-orchestrator MCP server)
uv tool install "shoal-cli[mcp]"
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

<div class="shoal-card-grid">
  <a class="shoal-card shoal-icon-card" href="FISH_INTEGRATION/" data-icon="bolt">
    <strong>Better shell ergonomics</strong>
    <span>Set up completions, bindings, and helper functions that match the intended operator flow.</span>
  </a>
  <a class="shoal-card shoal-icon-card" href="LOCAL_TEMPLATES/" data-icon="stack">
    <strong>Reusable session layouts</strong>
    <span>Define stable templates and composition patterns instead of rebuilding pane topology by hand.</span>
  </a>
  <a class="shoal-card shoal-icon-card" href="ROBO_GUIDE/" data-icon="control">
    <strong>Agent supervision</strong>
    <span>Configure robo to shrink approval latency without turning automation into a black box.</span>
  </a>
  <a class="shoal-card shoal-icon-card" href="REMOTE_GUIDE/" data-icon="remote">
    <strong>Remote machines</strong>
    <span>Keep the same operating model while pushing work to another box over the remote transport.</span>
  </a>
  <a class="shoal-card shoal-icon-card" href="TROUBLESHOOTING/" data-icon="shield">
    <strong>Troubleshooting first</strong>
    <span>Jump straight to setup recovery and environment fixes if the fast path does not land cleanly.</span>
  </a>
</div>
