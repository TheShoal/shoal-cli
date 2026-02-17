# Fish Shell Integration

Shoal provides native integration with the [fish shell](https://fishshell.com/) to enhance your developer experience with intelligent completions, key bindings, and helper functions.

## Features

- **Command Completions**: Tab-complete all `shoal` commands and options
- **Dynamic Session Completions**: Auto-complete session names from your active sessions
- **Key Bindings**: Quick access to dashboard and attach functions
- **Abbreviations**: Short aliases for common commands
- **Helper Functions**: Convenience functions for frequent workflows

## Installation

### Prerequisites

Fish shell must be installed on your system. Install it using your package manager:

```bash
# macOS
brew install fish

# Ubuntu/Debian
sudo apt install fish

# Fedora
sudo dnf install fish

# Arch Linux
sudo pacman -S fish
```

### Install Shoal Fish Integration

Once fish is installed, run:

```bash
shoal setup fish
```

This command will install the following files to `~/.config/fish/`:

- `completions/shoal.fish` - Command and session name completions
- `conf.d/shoal.fish` - Bootstrap script (auto-loaded on shell start)
- `functions/shoal-quick-attach.fish` - Quick attach helper
- `functions/shoal-dashboard.fish` - Dashboard launcher

### Activate Integration

Restart your fish shell or source the configuration:

```fish
source ~/.config/fish/conf.d/shoal.fish
```

## Usage

### Command Completions

Tab-complete `shoal` commands and their options:

```fish
shoal <TAB>           # Shows all commands
shoal new --<TAB>     # Shows options for 'new' command
shoal attach <TAB>    # Shows active session names
```

### Dynamic Session Completions

Commands that operate on sessions will auto-complete session names:

```fish
shoal attach <TAB>    # grove, shoal, feature/foo, ...
shoal info <TAB>      # grove, shoal, feature/foo, ...
shoal kill <TAB>      # grove, shoal, feature/foo, ...
shoal logs <TAB>      # grove, shoal, feature/foo, ...
shoal rename <TAB>    # grove, shoal, feature/foo, ...
shoal fork <TAB>      # grove, shoal, feature/foo, ...
```

### Abbreviations

The integration provides convenient abbreviations for common commands:

| Abbreviation | Expands to       | Description                 |
|--------------|------------------|-----------------------------|
| `sa`         | `shoal attach`   | Attach to a session         |
| `sl`         | `shoal ls`       | List all sessions           |
| `ss`         | `shoal status`   | Show status overview        |
| `sp`         | `shoal popup`    | Launch popup dashboard      |
| `sn`         | `shoal new`      | Create new session          |
| `sk`         | `shoal kill`     | Kill a session              |
| `si`         | `shoal info`     | Show session info           |

Example usage:

```fish
# Instead of typing 'shoal attach grove'
sa grove

# Instead of typing 'shoal ls'
sl
```

### Key Bindings

The following key bindings are available (inside fish shell):

| Key Binding | Action                        | Description                              |
|-------------|-------------------------------|------------------------------------------|
| `Ctrl+S`    | `shoal popup`                 | Launch interactive dashboard             |
| `Alt+A`     | `shoal-quick-attach`          | Quick attach using fzf (if available)    |

### Helper Functions

#### `shoal-quick-attach`

Launches an interactive fzf picker to select and attach to a session:

```fish
shoal-quick-attach
```

Features:
- Full-screen fzf interface
- Live preview of session details
- Arrow keys to navigate, Enter to attach

Also bound to `Alt+A` for quick access.

#### `shoal-dashboard`

Launches the shoal popup dashboard directly:

```fish
shoal-dashboard
```

Also bound to `Ctrl+S` for quick access.

### Event Handlers

The integration automatically tracks your current shoal session using fish event handlers:

- **`fish_preexec`**: Detects when you're inside a shoal tmux session and stores it
- The last session is saved in a universal variable (`__shoal_last_session`) for cross-session access

## Customization

### Changing Key Bindings

To customize key bindings, add your own bindings in `~/.config/fish/config.fish`:

```fish
# Disable default Ctrl+S binding
bind -e \cs

# Add your own custom binding
bind \c] 'shoal popup; commandline -f repaint'
```

### Customizing Abbreviations

You can add your own abbreviations or remove existing ones:

```fish
# Add custom abbreviations
abbr -a sw 'shoal watcher start'
abbr -a sd 'shoal demo start'

# Remove an abbreviation
abbr -e sa  # Removes 'sa' abbreviation
```

### Adding Shoal Status to Fish Prompt

Uncomment the example in `~/.config/fish/conf.d/shoal.fish` to show the current shoal session in your right prompt:

```fish
function fish_right_prompt
    if set -q TMUX
        set -l session (tmux display-message -p '#S' 2>/dev/null)
        if test -n "$session"
            echo -n (set_color cyan)"[$session]"(set_color normal)
        end
    end
end
```

This will display `[session-name]` in cyan on the right side of your prompt when you're inside a shoal session.

## Updating the Integration

To update the fish integration files (e.g., after upgrading shoal), use the `--force` flag:

```fish
shoal setup fish --force
```

This will overwrite existing integration files with the latest versions.

## Troubleshooting

### Completions Not Working

1. Make sure fish shell is installed and you're running in a fish session
2. Verify integration files exist:
   ```fish
   ls ~/.config/fish/completions/shoal.fish
   ls ~/.config/fish/conf.d/shoal.fish
   ```
3. Restart your fish shell or run:
   ```fish
   source ~/.config/fish/conf.d/shoal.fish
   ```

### Key Bindings Not Working

Check if the bindings are registered:

```fish
bind | grep shoal
```

You should see output like:

```
bind \cs 'shoal popup; commandline -f repaint'
bind \ea 'shoal-quick-attach; commandline -f repaint'
```

If not, source the bootstrap script manually:

```fish
source ~/.config/fish/conf.d/shoal.fish
```

### Session Names Not Completing

Make sure `shoal ls --format plain` works:

```fish
shoal ls --format plain
```

This should output session names one per line without Rich formatting.

## Uninstallation

To remove fish integration, delete the installed files:

```fish
rm ~/.config/fish/completions/shoal.fish
rm ~/.config/fish/conf.d/shoal.fish
rm ~/.config/fish/functions/shoal-quick-attach.fish
rm ~/.config/fish/functions/shoal-dashboard.fish
```

Then restart your fish shell.

## Technical Details

### Plain Format Output

The fish integration uses `--format plain` for completions to avoid Rich rendering overhead:

```fish
# Fast, plain-text output for completions
shoal ls --format plain
# grove
# shoal
# feature/foo

# Rich formatted output (slower, for humans)
shoal ls
# [beautiful tables and panels]
```

### Performance

- Completions query `shoal ls --format plain` on each tab press
- This is typically fast (<50ms) but may slow down with hundreds of sessions
- If you experience slowness, consider implementing completion caching (future enhancement)

### Fish Version Compatibility

The integration is tested with fish 3.x and should work with any recent version.

## See Also

- [Shoal README](../README.md) - General documentation
- [Robo Guide](ROBO_GUIDE.md) - Robo workflow documentation
- [Fish Shell Documentation](https://fishshell.com/docs/current/) - Official fish docs
- [Fish Completions Guide](https://fishshell.com/docs/current/completions.html) - How fish completions work
