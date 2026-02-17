## ADDED Requirements

### Requirement: MCP proxy name validation
The MCP proxy entry point (`mcp_proxy.py`) SHALL validate the server name argument (`sys.argv[1]`) against the pattern `^[a-zA-Z0-9_-]+$` before passing it to `execvp`. If the name does not match, the process SHALL exit with a non-zero status and log an error message.

#### Scenario: Valid MCP server name
- **WHEN** mcp_proxy is invoked with name `my-server_1`
- **THEN** the proxy proceeds to resolve and exec the server command

#### Scenario: Invalid MCP server name with shell metacharacters
- **WHEN** mcp_proxy is invoked with name `; rm -rf /`
- **THEN** the proxy exits with non-zero status and prints an error without executing any command

#### Scenario: Empty MCP server name
- **WHEN** mcp_proxy is invoked with no name argument or an empty string
- **THEN** the proxy exits with non-zero status and prints a usage error

### Requirement: Socat EXEC argument quoting
The MCP pool (`mcp_pool.py`) SHALL use `shlex.quote()` on each argument in the socat EXEC command string to prevent shell injection through MCP server configuration values.

#### Scenario: Server config with shell metacharacters
- **WHEN** an MCP server config contains arguments with shell metacharacters (e.g., `$(whoami)`)
- **THEN** the socat EXEC command treats them as literal strings, not shell expansions

#### Scenario: Server config with spaces in arguments
- **WHEN** an MCP server config contains arguments with spaces
- **THEN** the socat EXEC command preserves them as single arguments

### Requirement: Session status unknown count
The session summary (`session.py`) SHALL include `unknown` in the status counts dictionary so that sessions with unrecognized status values are counted rather than raising a KeyError.

#### Scenario: Session with unknown status
- **WHEN** the session list includes a session with a status not in the known set
- **THEN** the summary counts dict includes an `unknown` key with the correct count

#### Scenario: No unknown sessions
- **WHEN** all sessions have recognized status values
- **THEN** the `unknown` count is 0 or absent, and no error occurs

### Requirement: Fish config respects XDG_CONFIG_HOME
The fish installer (`installer.py`) and config module SHALL check the `XDG_CONFIG_HOME` environment variable when determining the fish configuration directory, falling back to `~/.config/fish` when unset.

#### Scenario: XDG_CONFIG_HOME is set
- **WHEN** `XDG_CONFIG_HOME` is set to `/custom/config`
- **THEN** the fish config directory resolves to `/custom/config/fish`

#### Scenario: XDG_CONFIG_HOME is unset
- **WHEN** `XDG_CONFIG_HOME` is not set
- **THEN** the fish config directory resolves to `~/.config/fish`

### Requirement: Fish completion helpers are wired
The fish completions template SHALL connect the `__shoal_mcp_servers` and `__shoal_robo_profiles` helper functions to the appropriate `complete` commands so that tab completion returns actual MCP server names and robo profile names.

#### Scenario: Tab completing MCP server argument
- **WHEN** user types `shoal mcp <TAB>` in fish shell
- **THEN** the completion system calls `__shoal_mcp_servers` and lists available server names

#### Scenario: Tab completing robo profile argument
- **WHEN** user types `shoal session add --robo-profile <TAB>` in fish shell
- **THEN** the completion system calls `__shoal_robo_profiles` and lists available profile names

### Requirement: Deduplicated init/check commands
The CLI SHALL have a single shared implementation of the init/check logic rather than duplicated code in `cli/__init__.py` and `cli/session.py`. Both call sites SHALL delegate to the shared helper.

#### Scenario: Init from root CLI
- **WHEN** user runs `shoal init`
- **THEN** it invokes the shared init logic and produces the same output as before

#### Scenario: Init from session subcommand
- **WHEN** user runs `shoal session init` (if applicable)
- **THEN** it invokes the same shared init logic

### Requirement: Startup command KeyError guard
The session startup logic SHALL catch `KeyError` exceptions from `cmd.format()` template expansion and log a warning instead of crashing the session creation.

#### Scenario: Startup command with missing template variable
- **WHEN** a startup command template references `{undefined_var}` and the context dict does not contain that key
- **THEN** the system logs a warning with the command and missing key, and skips that command without crashing

#### Scenario: Startup command with valid template
- **WHEN** a startup command template references only available context variables
- **THEN** the command is formatted and executed normally
