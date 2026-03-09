---
description: Scaffold a new shoal fin from scratch following the fin contract-v1 shape.
---

You are scaffolding a new shoal fin. Before generating any files, ask the user:

1. What should this fin do? (describe the capability in plain English)
2. What is the capability name? (dot-namespaced string, e.g. `llm.openai`, `infra.k8s`, `storage.s3`)
3. What is the fin directory name? (e.g. `fin-openai`)

Once you have that information, generate the full scaffold below. The canonical reference for the expected shape is `~/sanctum/opus/proprium/the-shoal/fins-template/`.

---

## Fin contract-v1 — complete shape

### `fin.toml` required fields

```toml
name = "<fin-name>"
version = "0.1.0"
fin_contract_version = 1
capability = "<dot.namespaced.string>"

[entrypoints]
install   = "bin/install.fish"
configure = "bin/configure.fish"
run       = "bin/run.fish"
validate  = "bin/validate.fish"
```

Optional:
```toml
default_timeout_seconds = 30
```

### Environment variables injected before every entrypoint

| Variable | Always set? | Value |
|---|---|---|
| `SHOAL_FIN_ROOT` | Yes | Absolute path to the fin directory |
| `SHOAL_OUTPUT_FORMAT` | Yes | `"text"` or `"json"` |
| `SHOAL_FIN_CONFIG` | Only if a config file is set | Path to the config file |
| `SHOAL_LOG_LEVEL` | Yes | Inherited from shoal's log level |

### Exit code contract

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure |
| `2` | Missing prerequisite (`install`) |
| `3` | Config error (`configure`) |
| other non-zero | Unexpected error |

### Entrypoint responsibilities

- **`bin/install.fish`**: Check prerequisites (binaries, network access, OS deps). Exit 0 if all satisfied, exit 2 if any are missing.
- **`bin/configure.fish`**: Read `SHOAL_FIN_CONFIG` if set; fall back to `config/example.env`. Apply or validate configuration. Exit 3 on config error.
- **`bin/run.fish`**: The main entrypoint. `argv[1]` is the action. Read `SHOAL_OUTPUT_FORMAT` and emit JSON or plain text accordingly.
- **`bin/validate.fish`**: Validate `fin.toml` required fields and that all entrypoints are executable. With `--strict`, also check that `README.md` and `config/example.env` exist.

---

## Files to generate

Generate all of the following files under the fin directory:

### `fin.toml`

Fill in `name`, `version`, `capability`, and all four entrypoints. Use the shape above exactly.

### `bin/install.fish`

```fish
#!/usr/bin/env fish

# Install entrypoint — check prerequisites
# Exit 2 if any prerequisite is missing

set -l required_bins <list any required binaries here>

for bin in $required_bins
    if not command -q $bin
        echo "Missing prerequisite: $bin" >&2
        exit 2
    end
end

echo "All prerequisites satisfied."
exit 0
```

### `bin/configure.fish`

```fish
#!/usr/bin/env fish

# Configure entrypoint — load config
# Exit 3 on config error

set -l config_file $SHOAL_FIN_CONFIG
if test -z "$config_file"
    set config_file $SHOAL_FIN_ROOT/config/example.env
end

if not test -f "$config_file"
    echo "Config file not found: $config_file" >&2
    exit 3
end

# Source the env file
while read -l line
    if string match -qr '^[A-Z_]+=.*' -- $line
        set -gx (string split -m1 '=' -- $line)[1] (string split -m1 '=' -- $line)[2]
    end
end < $config_file

echo "Configuration loaded from $config_file"
exit 0
```

### `bin/run.fish`

```fish
#!/usr/bin/env fish

# Run entrypoint — main capability logic
# argv[1] is the action

set -l action $argv[1]

switch $action
    case help ''
        if test "$SHOAL_OUTPUT_FORMAT" = json
            echo '{"actions": ["help"]}'
        else
            echo "Usage: shoal fin run <fin-name> <action>"
        end
    case '*'
        echo "Unknown action: $action" >&2
        exit 1
end

exit 0
```

### `bin/validate.fish`

```fish
#!/usr/bin/env fish

# Validate entrypoint — check fin.toml and entrypoints

set -l strict 0
if contains -- --strict $argv
    set strict 1
end

set -l toml $SHOAL_FIN_ROOT/fin.toml
if not test -f "$toml"
    echo "Missing fin.toml" >&2
    exit 1
end

for ep in install configure run validate
    set -l script $SHOAL_FIN_ROOT/bin/$ep.fish
    if not test -x "$script"
        echo "Entrypoint not executable: $script" >&2
        exit 1
    end
end

if test $strict -eq 1
    if not test -f "$SHOAL_FIN_ROOT/README.md"
        echo "--strict: Missing README.md" >&2
        exit 1
    end
    if not test -f "$SHOAL_FIN_ROOT/config/example.env"
        echo "--strict: Missing config/example.env" >&2
        exit 1
    end
end

echo "Validation passed."
exit 0
```

### `config/example.env`

Generate a commented example env file with the config keys the fin needs.

---

## After generating all files

1. Make all scripts executable:
   ```bash
   chmod +x <fin-path>/bin/*.fish
   ```

2. Run validation:
   ```bash
   shoal fin validate <fin-path>
   ```

3. Show the install command:
   ```bash
   shoal fin install <fin-path>
   ```
