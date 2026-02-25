## ADDED Requirements

### Requirement: bootstrap.fish SHALL guard against non-interactive shells
The `bootstrap.fish` file MUST include `status is-interactive; or return` as its first executable line to prevent errors in non-interactive contexts (scripts, cron, etc.).

#### Scenario: Fish sources bootstrap.fish in non-interactive context
- **WHEN** fish sources `bootstrap.fish` during a non-interactive invocation (e.g., `fish -c "some command"`)
- **THEN** the script returns immediately without setting abbreviations, keybindings, or event handlers

#### Scenario: Fish sources bootstrap.fish in interactive shell
- **WHEN** fish sources `bootstrap.fish` during an interactive shell session
- **THEN** all abbreviations, keybindings, and event handlers are set up normally

### Requirement: bootstrap.fish SHALL use global variables instead of universal
The `bootstrap.fish` file MUST use `set -g` (global scope) instead of `set -U` (universal scope) for the `__shoal_last_session` variable to avoid filesystem writes on every command.

#### Scenario: Preexec handler updates last session variable
- **WHEN** the `fish_preexec` handler runs and updates `__shoal_last_session`
- **THEN** the variable is set with `set -g` (in-memory only, no disk write)

### Requirement: quick-attach.fish SHALL prevent shell injection in fzf preview
The `quick-attach.fish` function MUST use single-quoted `--preview` argument and `--` separator to prevent shell injection via fzf's `{}` placeholder.

#### Scenario: Session name with special characters in fzf preview
- **WHEN** fzf renders the preview for a session name
- **THEN** the session name is passed safely to `shoal info` without shell evaluation of metacharacters

### Requirement: quick-attach.fish SHALL use -- before session name in attach
The attach command in `quick-attach.fish` MUST include `--` before the session name to prevent flag injection from names starting with `-`.

#### Scenario: Attaching to a session via quick-attach
- **WHEN** a user selects a session in fzf and the script calls `shoal attach`
- **THEN** the session name is passed after `--` to prevent interpretation as a flag
