---
description: Authoritative reference for the shoal fin contract-v1 — schema, exit codes, env vars, and change rules.
---

## fin.toml schema

All fields at the top level unless noted.

| Field | Required | Type | Notes |
|---|---|---|---|
| `name` | Yes | string | Human-readable fin name |
| `version` | Yes | string | Semver string, e.g. `"0.1.0"` |
| `fin_contract_version` | Yes | integer | Must be `1` |
| `capability` | Yes | string | Dot-namespaced capability identifier, e.g. `llm.openai` |
| `[entrypoints].install` | Yes | string | Path to install script, relative to fin root |
| `[entrypoints].configure` | Yes | string | Path to configure script |
| `[entrypoints].run` | Yes | string | Path to run script |
| `[entrypoints].validate` | Yes | string | Path to validate script |
| `default_timeout_seconds` | No | integer | Per-entrypoint timeout; shoal default applies if omitted |

All entrypoints are fish scripts and must live under `bin/`. The canonical scaffold is at `~/sanctum/opus/proprium/the-shoal/fins-template/`.

---

## What belongs in shoal vs a fin

**Shoal** owns orchestration: session create/kill/status, tmux lifecycle, MCP pool management, daemon, template resolution, worktree management. If it needs to run inside a session or coordinate across sessions, it is shoal's responsibility.

**A fin** owns extensions: custom capabilities, integrations with external services, additional tools or APIs that augment what an agent inside a session can do. If it augments shoal's behavior rather than running sessions, it is a fin.

Rule of thumb: if the feature needs to run _in_ a session, it belongs in shoal; if it extends what shoal can _offer_ to a session, it belongs in a fin.

---

## Exit code contract

| Code | Meaning | Typical entrypoint |
|---|---|---|
| `0` | Success | Any |
| `1` | Generic failure | Any |
| `2` | Missing prerequisite | `install` |
| `3` | Config error | `configure` |
| Other non-zero | Unexpected error | Any |

Shoal surfaces the exit code in session logs and status. Non-zero from `install` or `configure` blocks subsequent entrypoint execution.

---

## Environment variable contract

These vars are injected by shoal before every entrypoint invocation.

| Variable | Set? | Value |
|---|---|---|
| `SHOAL_FIN_ROOT` | Always | Absolute path to the fin directory |
| `SHOAL_OUTPUT_FORMAT` | Always | `"text"` or `"json"` |
| `SHOAL_FIN_CONFIG` | If configured | Absolute path to the config file |
| `SHOAL_LOG_LEVEL` | Always | Inherited from shoal's log level |

Entrypoints must not assume any other shoal-specific vars are present. External env vars (API keys, etc.) come from the session's template env or the user's shell.

---

## Entrypoint responsibilities

- **`bin/install.fish`**: Check that all prerequisites exist (binaries, libraries, network access). Exit `2` for any missing prerequisite. Exit `0` only when the fin is fully installable.
- **`bin/configure.fish`**: Read `SHOAL_FIN_CONFIG` if set; fall back to `config/example.env`. Validate required config keys. Exit `3` on any config error.
- **`bin/run.fish`**: Main capability logic. `argv[1]` is the action string. Emit JSON when `SHOAL_OUTPUT_FORMAT=json`, plain text otherwise.
- **`bin/validate.fish`**: Check `fin.toml` required fields and that all four entrypoints exist and are executable. With `--strict`, also assert `README.md` and `config/example.env` are present.

---

## Breaking vs non-breaking changes

**Breaking** (requires a capability version bump or coordinated migration):
- Removing or renaming an entrypoint
- Changing the `capability` string
- Removing or renaming a required config key
- Changing exit code semantics

**Non-breaking** (safe to ship):
- Adding new actions to `run`
- Adding new optional config keys with documented defaults
- New optional features gated behind env vars
- Adding output fields to JSON responses (consumers must tolerate extra fields)
- Updating `default_timeout_seconds`

---

## Validation

Always validate before registering a fin:

```bash
shoal fin validate --strict <fin-path>
```

CI must call this. The `--strict` flag additionally requires `README.md` and `config/example.env`.

Fish-specific: all entrypoints must pass a dry-run syntax check. Run:

```bash
just fish-check
```

This covers all `.fish` files in the repo. A fin that fails `fish -n` will not be accepted.
