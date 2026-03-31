# Smorgasbord + Shoal CLI Integration

This document outlines the strategic integration between **Shoal CLI** (the parallel agent orchestrator) and **Smorgasbord** (the US Mobile meta-repository and domain context layer). 

## 1. Context & Objective

**Smorgasbord** is a centralized workspace that tracks all US Mobile microservices, frontend applications, and devops repositories. It uses a manifest (`repos.txt`) to clone dozens of repositories into structured directories (`backend/`, `frontend/`, `devops/`). It also contains cross-cutting architectural specifications (**OpenSpec**) and a local, git-backed issue tracker optimized for AI agents (**beads / bd**).

**Shoal CLI** is designed to run a fleet of coding agents with isolated worktrees, visible state, and recoverable handoffs. 

**The Objective:** Integrate the two so that Shoal acts as the "fleet commander" for Smorgasbord. Instead of opening multiple terminal tabs to run agents in isolated microservices, developers will use Shoal to launch, monitor, and coordinate parallel agents across the Smorgasbord landscape, ensuring every agent has access to global architectural context and automated issue tracking.

---

## 2. Desired Workflows

### 2.1 The Autonomous Task Dispatcher (Robo + Beads)
Smorgasbord uses `beads` (backed by a Dolt SQL database) to track granular agent tasks synced from Linear.
* **Workflow:** Shoal's Robo Supervisor polls `bd ready` in the Smorgasbord root. When a high-priority ticket appears, Robo automatically provisions a new Shoal session (`shoal new -t be-agent -w backend/emailservice`), assigns the ticket ID to the session, and triggers the agent to begin work.
* **State Syncing:** When the Shoal session enters a `waiting` state (needing human approval) or an `error` state, a Shoal extension automatically runs `bd update <id> --status=blocked --notes="Shoal session waiting on human"`. When the agent finishes, it triggers the `/beads:pr` command.

### 2.2 Global Context via Persistent MCP
Agents running in isolated microservices (e.g., `frontend/web-app`) often need to know about API contracts or architectural decisions stored in the root `smorgasbord/openspec/` directory.
* **Workflow:** Shoal mounts a root-level MCP (Model Context Protocol) server into every isolated session it spawns. This allows an agent working deep inside a microservice to query the global `OpenSpec` architecture docs or check the `beads` database without breaking its sandbox.

### 2.3 Meta-Repo Worktree Management
Smorgasbord is a git repository that ignores the sub-repositories it clones. 
* **Workflow:** When a user runs `shoal new -w backend/user-service`, Shoal must intelligently handle the creation of git worktrees *for the nested sub-repository*, not the Smorgasbord root. Furthermore, Shoal must ensure that symlinks or references to the root `AGENTS.md` and `.beads` database remain intact within the isolated worktree environment.

### 2.4 "Review Lanes" (Mode 01)
* **Workflow:** An agent finishes implementing a feature in a backend service. Before the PR is created, Shoal automatically spins up an ephemeral "reviewer" agent. This reviewer agent is pre-loaded with the Smorgasbord `AGENTS.md` (which enforces US Mobile's commit logic, atomic PR sizes, and code standards). If the reviewer approves, the original agent creates the PR.

---

## 3. Required Changes in Shoal CLI

To natively support this integration, the following enhancements are required in Shoal:

1. **Meta-Repo / Nested Workspace Support:** 
   Shoal needs a mechanism (e.g., a `.shoal-workspace.yml` manifest reader) to understand that it is operating inside a meta-repo. It must correctly route `git worktree` commands to the nested repositories (`backend/emailservice`) rather than the root directory.

2. **State Hook Extensions (The Beads Sync):**
   Shoal's SQLite state tracker needs extension hooks for lifecycle events (`on_session_start`, `on_agent_waiting`, `on_session_complete`). This allows a custom Smorgasbord extension to translate Shoal states into `bd update` commands.

3. **Persistent Parent-Level MCP Injection:**
   Shoal templates must support defining an MCP server that runs at the *parent* workspace level, effectively allowing isolated sessions to communicate with a shared, centralized context server (for OpenSpec and Beads).

4. **Template Inheritance:**
   Shoal should support template hierarchies so Smorgasbord can define a base `usm-agent` template (containing global rules like `AGENTS.md`), which is then inherited by `be-agent` (adds Spring Boot context) and `fe-agent` (adds React context).
## 4. Template & Lifecycle Specifications
Based on the concrete scaffolding implemented in the `smorgasbord` repository, Shoal must support the following explicit template keys and lifecycles:

### 4.1 Schema Expectations for `.shoal/templates/*.yml`
Shoal's template parser needs to recognize and act upon these specific YAML keys that we scaffolded:
* `workspace_override:` A string (e.g., `"backend/"`) that forces the `shoal new -w <path>` command to resolve relative to a specific sub-directory.
* `context:` An array of relative file paths (e.g., `["AGENTS.md", "backend/CLAUDE.md"]`) that Shoal injects directly into the agent's initial prompt context.
* `mcp_servers:` An array of objects defining standard `stdio` MCP server commands.
  ```yaml
  mcp_servers:
    - name: beads
      command: python
      args: ["scripts/mcp/beads-server.py"]
  ```

### 4.2 Post-Worktree Hooks
We created a `scripts/shoal-sync.sh` script in Smorgasbord to symlink the `.beads` database and `AGENTS.md` context into nested microservice worktrees.
* **Shoal Requirement:** Shoal should introduce a `post_worktree_create` hook (either globally in `.shoal/config.yml` or at the template level). When Shoal finishes provisioning an isolated git worktree, it automatically executes this script, passing the new worktree's absolute path as an argument. This removes the need for humans to manually sync the meta-repo state before the agent boots.



---

## 5. Implementation Status

| Requirement | Status | Notes |
|---|---|---|
| §3.4 Template inheritance (`extends`) | **Done** | Shoal core — `extends` + `mixins` on `SessionTemplateConfig` |
| §4.1 TOML template schema (`usm-be-agent`, etc.) | **Done** | Smorgasbord — replaced non-functional YML with TOML templates |
| §4.2 `post_worktree_create` hook | **Done** | Shoal core — `TemplateWorktreeConfig.post_worktree_create: str`; lifecycle executes script with worktree abs path as `$1` |
| §3.2 State hook extensions (beads sync) | **Done** | Shoal core — `.shoal/hooks.toml` loaded at API startup; `[[hooks]]` entries bind shell commands to `LifecycleEvent` with optional `when_status` filter; smorgasbord example at `.shoal/hooks.toml` |
| §2.1 Incident supervision (Robo + Beads) | **Done** | Shoal core — `shoal incident ingest/spawn/resolve/show`; smorgasbord wrappers at `scripts/incident/`; incident templates at `.shoal/templates/usm-incident-*.toml` |
| §3.3 Persistent parent-level MCP injection | **Deferred** | Templates reference registered server names only. Inline `mcp_servers:` (command + args) in templates is not supported. Workaround: register servers in `~/.config/shoal/mcp-servers.toml`; the `usm-workspace` fin's `install` phase can automate this |
| §3.1 Meta-repo / nested workspace routing | **Done** | `.shoal/workspace.toml` manifest maps logical names to sub-repo paths; `--repo` flag for explicit targeting; auto-match by worktree hint or path prefix; wired in CLI + API |
| §4.1 `workspace_override` / `context` YAML keys | **Deferred** | These were non-standard keys in the original YML files. Shoal's TOML template schema does not include them. Equivalent coverage: `post_worktree_create` handles context injection; `mcp` handles tool context |

### Nested workspace routing (§3.1)

Place a `.shoal/workspace.toml` in the meta-repo root:

```toml
[workspace]
name = "smorgasbord"

[workspace.repos]
emailservice = "backend/emailservice"
user-service = "backend/user-service"
web-app = "frontend/web-app"
```

Then from the smorgasbord root:

```bash
# Explicit --repo flag
shoal new -w feat/my-feature --repo emailservice -b

# Auto-match: worktree hint matches a repo key
shoal new -w emailservice -b

# Auto-match: resolved path is inside a known sub-repo
cd backend/emailservice && shoal new -w feat/my-feature -b
```

Matching priority: `--repo` > worktree hint key match > path prefix match > fall through to meta-repo.

### Wiring post_worktree_create for shoal-sync.sh

Add to any incident or agent template:

```toml
[template.worktree]
post_worktree_create = "scripts/shoal-sync.sh"
```

Shoal executes `scripts/shoal-sync.sh <worktree-abs-path>` after the git
worktree is created, before the agent starts. This symlinks `.beads`,
`AGENTS.md`, and `openspec` into the new worktree.

### Wiring lifecycle hooks for beads sync

`.shoal/hooks.toml` is loaded by the Shoal API at startup. The smorgasbord
example at `.shoal/hooks.toml` wires three hooks:

- `status_changed` + `when_status = "waiting"` → `bd update` notes
- `status_changed` + `when_status = "error"` → `bd update` notes
- `session_completed` → `scripts/incident/sync-beads` for `inc-*` sessions