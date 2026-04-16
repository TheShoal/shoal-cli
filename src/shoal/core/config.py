"""Configuration loading and XDG path helpers."""

from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shoal.models.config.hooks import ProjectHookEntry
    from shoal.models.config.workspace import ProjectConfig, SkillConfig, WorkspaceConfig

from shoal.core.status_provider import default_status_provider_for_tool
from shoal.models.config.general import ShoalConfig
from shoal.models.config.robo import RoboProfileConfig
from shoal.models.config.templates import (
    SessionTemplateConfig,
    TemplateGitConfig,
    TemplateMixinConfig,
    TemplatePaneConfig,
    TemplateWindowConfig,
    TemplateWorktreeConfig,
)
from shoal.models.config.tools import (
    DetectionPatterns,
    MCPToolConfig,
    ToolConfig,
)

logger = logging.getLogger("shoal.config")


class ConfigLoadError(Exception):
    """User-friendly error for malformed or invalid config files."""

    def __init__(self, path: Path | str, detail: str) -> None:
        self.path = Path(path)
        self.detail = detail
        super().__init__(f"{path}: {detail}")


def _examples_dir() -> Path:
    """Return the path to bundled example configs shipped with the package.

    In an installed wheel, examples live at ``shoal/examples/config`` (via
    hatchling force-include).  In an editable/dev install, they live at
    ``<repo>/examples/config``.
    """
    pkg_root = Path(__file__).resolve().parent.parent  # .../shoal/
    # Installed wheel path
    installed = pkg_root / "examples" / "config"
    if installed.is_dir():
        return installed
    # Dev / editable install: walk up to repo root
    repo_root = pkg_root.parent.parent  # .../src -> .../<repo>
    dev = repo_root / "examples" / "config"
    if dev.is_dir():
        return dev
    return installed  # fallback (will log warning in scaffold_defaults)


@lru_cache(maxsize=1)
def soul_text() -> str:
    """Return SOUL.md content, or empty string if not found."""
    pkg_root = Path(__file__).resolve().parent.parent
    for base in (pkg_root.parent.parent, pkg_root):
        path = base / "SOUL.md"
        if path.is_file():
            return path.read_text()
    return ""


def config_dir() -> Path:
    """Return Shoal config directory.

    Reads ``XDG_CONFIG_HOME`` env var, falling back to ``~/.config/shoal``.
    """
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "shoal"


def data_dir() -> Path:
    """Return Shoal persistent data directory (sessions, robo state).

    Reads ``XDG_DATA_HOME`` env var, falling back to ``~/.local/share/shoal``.
    """
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "shoal"


def state_dir() -> Path:
    """Return Shoal transient state directory (PIDs, logs).

    Reads ``XDG_STATE_HOME`` env var, falling back to ``~/.local/state/shoal``.
    """
    base = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "shoal"


def ensure_dirs() -> None:
    """Create all required data and state directories."""
    cfg = config_dir()
    for subdir in ("templates", "templates/mixins"):
        (cfg / subdir).mkdir(parents=True, exist_ok=True)

    base = data_dir()
    for subdir in (
        "sessions",
        "journals",
        "mcp-pool/pids",
        "mcp-pool/sockets",
        "delegation/sockets",
        "robo",
        "remote",
    ):
        (base / subdir).mkdir(parents=True, exist_ok=True)
    rt = state_dir()
    for subdir in ("logs",):
        (rt / subdir).mkdir(parents=True, exist_ok=True)


def scaffold_defaults() -> list[str]:
    """Copy bundled example configs into the user's config dir.

    Only writes files that do not already exist — never overwrites.
    Returns a list of relative paths that were created.
    """
    import shutil

    src = _examples_dir()
    if not src.is_dir():
        logger.warning("Bundled examples not found at %s", src)
        return []

    dst = config_dir()
    created: list[str] = []

    for src_file in sorted(src.rglob("*")):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        if dst_file.exists():
            logger.debug("Skipping existing: %s", rel)
            continue
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        created.append(str(rel))
        logger.debug("Scaffolded: %s", rel)

    return created


@lru_cache(maxsize=1)
def load_config() -> ShoalConfig:
    """Load and cache the main config.toml."""
    from pydantic import ValidationError

    path = config_dir() / "config.toml"
    logger.debug("Loading config from %s", path)
    if not path.exists():
        return ShoalConfig()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoadError(path, f"malformed TOML: {e}") from e
    try:
        return ShoalConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigLoadError(path, f"invalid config: {e}") from e


def load_tool_config(name: str) -> ToolConfig:
    """Load a tool config, flattening [tool] + [detection] + [mcp] sections."""
    from pydantic import ValidationError

    logger.debug("Loading tool config: %s", name)
    path = config_dir() / "tools" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No tool config: {path}")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoadError(path, f"malformed TOML: {e}") from e

    tool_section = data.get("tool", {})
    detection_section = data.get("detection", {})
    mcp_section = data.get("mcp", {})

    try:
        tool_name = tool_section.get("name", name)
        return ToolConfig(
            name=tool_name,
            command=tool_section.get("command", name),
            icon=tool_section.get("icon", "●"),
            status_provider=tool_section.get(
                "status_provider", default_status_provider_for_tool(tool_name)
            ),
            send_keys_delay=tool_section.get("send_keys_delay", 0.0),
            input_mode=tool_section.get("input_mode", "keys"),
            prompt_flag=tool_section.get("prompt_flag", ""),
            prompt_file_prefix=tool_section.get("prompt_file_prefix", ""),
            detection=DetectionPatterns.model_validate(detection_section),
            mcp=MCPToolConfig.model_validate(mcp_section),
        )
    except ValidationError as e:
        raise ConfigLoadError(path, f"invalid tool config: {e}") from e


def load_robo_profile(name: str) -> RoboProfileConfig:
    """Load a robo profile TOML."""
    from pydantic import ValidationError

    path = config_dir() / "robo" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No robo profile: {name}")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoadError(path, f"malformed TOML: {e}") from e

    robo_section = data.get("robo", {})
    try:
        return RoboProfileConfig(
            name=robo_section.get("name", name),
            tool=robo_section.get("tool", "pi"),
            auto_approve=robo_section.get("auto_approve", False),
            monitoring=data.get("monitoring", {}),
            escalation=data.get("escalation", {}),
            tasks=data.get("tasks", {}),
        )
    except ValidationError as e:
        raise ConfigLoadError(path, f"invalid robo profile: {e}") from e


def available_tools() -> list[str]:
    """List available tool names from config/tools/*.toml."""
    tools_dir = config_dir() / "tools"
    if not tools_dir.exists():
        return []
    return sorted(p.stem for p in tools_dir.glob("*.toml"))


def templates_dir() -> Path:
    """Return ~/.config/shoal/templates."""
    return config_dir() / "templates"


def project_templates_dir() -> Path | None:
    """Return ``<git-root>/.shoal/templates`` if inside a git repo and the dir exists."""
    from shoal.core import git

    try:
        root = git.git_root(".")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    candidate = Path(root) / ".shoal" / "templates"
    return candidate if candidate.is_dir() else None


def available_templates() -> list[str]:
    """List available template names from local and global template dirs."""
    names: set[str] = set()
    local = project_templates_dir()
    if local and local.exists():
        names.update(p.stem for p in local.glob("*.toml"))
    global_dir = templates_dir()
    if global_dir.exists():
        names.update(p.stem for p in global_dir.glob("*.toml"))
    return sorted(names)


def template_source(name: str) -> str:
    """Return 'local' if the template exists in project-local dir, else 'global'."""
    local = project_templates_dir()
    if local and (local / f"{name}.toml").exists():
        return "local"
    return "global"


def _load_hermes_mcp_servers() -> dict[str, dict[str, Any]]:
    """Load MCP servers from Hermes config if available.

    Reads ``~/.hermes/config.yaml`` and extracts the ``mcp_servers`` section.
    Supports both HTTP servers (have ``url`` key) and stdio servers (have ``command`` key).

    Returns:
        Dict of server name -> config dict with keys like ``url``, ``command``, ``transport``.
    """
    hermes_home = Path.home() / ".hermes"
    config_path = hermes_home / "config.yaml"
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed, skipping hermes MCP servers")
        return {}

    try:
        data = yaml.safe_load(config_path.read_text())
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load hermes config: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        # Determine transport type
        if "url" in cfg:
            # HTTP server
            result[name] = {
                "url": cfg["url"],
                "transport": "http",
                "timeout": cfg.get("timeout"),
                "connect_timeout": cfg.get("connect_timeout"),
            }
        elif "command" in cfg:
            # stdio server - build command string
            cmd_parts = [cfg["command"]]
            if "args" in cfg:
                cmd_parts.extend(cfg["args"])
            result[name] = {
                "command": " ".join(cmd_parts),
                "transport": "stdio",
            }

    return result


def load_mcp_registry() -> dict[str, str]:
    """Load MCP server registry: user file merged over built-in defaults.

    Reads ``~/.config/shoal/mcp-servers.toml`` and ``~/.hermes/config.yaml``.
    Each top-level key is a server name whose value is a table with a ``command`` key.
    Built-in defaults are used as a fallback for servers not overridden by the user.

    Precedence (highest to lowest):
    1. User mcp-servers.toml
    2. Hermes config.yaml mcp_servers (stdio only - HTTP servers are not command-based)
    3. Built-in defaults

    Returns:
        Mapping of server name → command string.
    """
    from shoal.services.mcp_pool import _DEFAULT_SERVERS

    registry: dict[str, str] = dict(_DEFAULT_SERVERS)

    # Merge hermes MCP servers (stdio only)
    hermes_servers = _load_hermes_mcp_servers()
    for name, cfg in hermes_servers.items():
        if "command" in cfg:
            registry[name] = cfg["command"]

    # User file takes highest precedence
    user_file = config_dir() / "mcp-servers.toml"
    if user_file.exists():
        try:
            with open(user_file, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigLoadError(user_file, f"malformed TOML: {e}") from e
        for name, entry in data.items():
            if isinstance(entry, dict) and "command" in entry:
                registry[name] = entry["command"]

    return registry


def load_mcp_registry_full() -> dict[str, dict[str, Any]]:
    """Load the full MCP server registry with all fields per entry.

    Seeds with built-in defaults, then merges hermes config, then user overrides.
    Returns raw dicts so callers can read ``transport``, ``url``, and other fields.
    """
    from shoal.services.mcp_pool import _DEFAULT_SERVERS

    registry: dict[str, dict[str, Any]] = {
        name: {"command": cmd} for name, cmd in _DEFAULT_SERVERS.items()
    }

    # Merge hermes MCP servers
    hermes_servers = _load_hermes_mcp_servers()
    for name, cfg in hermes_servers.items():
        if name in registry:
            registry[name].update(cfg)
        else:
            registry[name] = cfg

    # User file takes highest precedence
    user_file = config_dir() / "mcp-servers.toml"
    if user_file.exists():
        try:
            with open(user_file, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigLoadError(user_file, f"malformed TOML: {e}") from e
        for name, entry in data.items():
            if isinstance(entry, dict):
                user_entry = dict(entry.items())
                if name in registry:
                    registry[name].update(user_entry)
                else:
                    registry[name] = user_entry
    return registry


def mixins_dir() -> Path:
    """Return ~/.config/shoal/templates/mixins."""
    return templates_dir() / "mixins"


def available_mixins() -> list[str]:
    """List available mixin names from local and global mixin dirs."""
    names: set[str] = set()
    local = project_templates_dir()
    if local:
        local_mixins = local / "mixins"
        if local_mixins.exists():
            names.update(p.stem for p in local_mixins.glob("*.toml"))
    global_dir = mixins_dir()
    if global_dir.exists():
        names.update(p.stem for p in global_dir.glob("*.toml"))
    return sorted(names)


def _load_template_raw(name: str) -> dict[str, Any]:
    """Load raw TOML data for a template without resolving inheritance.

    Checks project-local ``.shoal/templates/`` first, then global.
    """
    local = project_templates_dir()
    if local:
        local_path = local / f"{name}.toml"
        if local_path.exists():
            try:
                with open(local_path, "rb") as f:
                    return tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise ConfigLoadError(local_path, f"malformed TOML: {e}") from e
    path = templates_dir() / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No template config: {path}")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoadError(path, f"malformed TOML: {e}") from e


def _parse_template_data(
    data: dict[str, Any],
    name: str,
) -> SessionTemplateConfig:
    """Parse raw TOML dict into SessionTemplateConfig."""
    from pydantic import ValidationError

    template_section = data.get("template", {})
    worktree_section = template_section.get("worktree", {})
    git_section = template_section.get("git", {})
    env_section = template_section.get("env", {})
    mcp_section = template_section.get("mcp", [])
    # Windows can appear as top-level [[windows]] or nested [[template.windows]].
    # Support both conventions; template-nested takes precedence if present.
    windows_section = template_section.get("windows", data.get("windows", []))

    try:
        return SessionTemplateConfig(
            name=template_section.get("name", name),
            description=template_section.get("description", ""),
            extends=template_section.get("extends"),
            mixins=template_section.get("mixins", []),
            tool=template_section.get("tool", "pi"),
            mode=template_section.get("mode", ""),
            tags=template_section.get("tags", []),
            worktree=TemplateWorktreeConfig.model_validate(worktree_section),
            git=TemplateGitConfig.model_validate(git_section),
            env=env_section,
            mcp=mcp_section,
            windows=windows_section,
            setup_commands=template_section.get("setup_commands", []),
        )
    except ValidationError as e:
        raise ConfigLoadError(f"template '{name}'", f"invalid template: {e}") from e


def _merge_pane(
    parent: TemplatePaneConfig,
    child: TemplatePaneConfig,
) -> TemplatePaneConfig:
    """Deep-merge a child pane over a parent pane.

    Child fields that are non-empty win; parent fills gaps.
    When a child pane omits ``command`` (empty string), it inherits the
    parent pane's command — this allows child templates to override only
    structural fields (``split``, ``size``, ``title``) or ``cwd`` without
    repeating the tool command.
    """
    return TemplatePaneConfig(
        split=child.split if child.split != "root" or parent.split == "root" else parent.split,
        size=child.size or parent.size,
        title=child.title or parent.title,
        command=child.command or parent.command,
    )


def _merge_window(
    parent: TemplateWindowConfig,
    child: TemplateWindowConfig,
) -> TemplateWindowConfig:
    """Deep-merge a child window over a parent window.

    Child window-level fields (name, cwd, layout, focus) override parent.
    Panes are merged by index: each child pane inherits missing fields from
    the parent pane at the same position.  Extra child or parent panes are
    appended.
    """
    merged_panes: list[TemplatePaneConfig] = []
    max_panes = max(len(parent.panes), len(child.panes))
    for i in range(max_panes):
        p_pane = parent.panes[i] if i < len(parent.panes) else None
        c_pane = child.panes[i] if i < len(child.panes) else None
        if p_pane and c_pane:
            merged_panes.append(_merge_pane(p_pane, c_pane))
        else:
            merged_panes.append(c_pane or p_pane)

    return TemplateWindowConfig(
        name=child.name or parent.name,
        cwd=child.cwd or parent.cwd,
        layout=child.layout or parent.layout,
        focus=child.focus or parent.focus,
        panes=merged_panes,
    )


def _merge_templates(
    parent: SessionTemplateConfig,
    child: SessionTemplateConfig,
    child_raw: dict[str, Any],
) -> SessionTemplateConfig:
    """Merge child template over parent.

    Merge rules:
    - scalars (description, tool): child wins if explicitly set in TOML
    - worktree: child wins if [template.worktree] present in TOML
    - git: child wins if [template.git] present in TOML
    - env: parent | child (child wins on conflicts)
    - mcp: union, deduplicated, sorted
    - windows: deep-merge by name; child panes inherit from parent panes
    - setup_commands: child replaces parent if explicitly set in TOML
    """
    child_tmpl = child_raw.get("template", {})

    description = child.description if "description" in child_tmpl else parent.description
    tool = child.tool if "tool" in child_tmpl else parent.tool
    worktree = child.worktree if "worktree" in child_tmpl else parent.worktree
    git = child.git if "git" in child_tmpl else parent.git
    merged_env = {**parent.env, **child.env}
    merged_mcp = sorted(set(parent.mcp) | set(child.mcp))

    # Deep-merge windows: match by name, inherit pane layout from parent
    if child.windows:
        parent_by_name = {w.name: w for w in parent.windows}
        merged_windows: list[TemplateWindowConfig] = []
        used_parent_names: set[str] = set()
        for cw in child.windows:
            pw = parent_by_name.get(cw.name)
            if pw:
                merged_windows.append(_merge_window(pw, cw))
                used_parent_names.add(cw.name)
            else:
                merged_windows.append(cw)
        # Append parent windows not overridden by child
        merged_windows.extend(pw for pw in parent.windows if pw.name not in used_parent_names)
    else:
        merged_windows = parent.windows

    setup_commands = (
        child.setup_commands if "setup_commands" in child_tmpl else parent.setup_commands
    )

    mode = child.mode if "mode" in child_tmpl else parent.mode
    merged_tags = sorted(set(parent.tags) | set(child.tags))

    return SessionTemplateConfig(
        name=child.name,
        description=description,
        extends=None,
        mixins=child.mixins,
        tool=tool,
        mode=mode,
        tags=merged_tags,
        worktree=worktree,
        git=git,
        env=merged_env,
        mcp=merged_mcp,
        windows=merged_windows,
        setup_commands=setup_commands,
    )


def resolve_template(
    name: str,
    _chain: set[str] | None = None,
) -> SessionTemplateConfig:
    """Load and fully resolve a template: extends -> mixins -> final.

    Raises ValueError on inheritance cycles or unknown mixins.
    """
    if _chain is None:
        _chain = set()

    if name in _chain:
        cycle = " -> ".join(_chain) + f" -> {name}"
        raise ValueError(f"Template inheritance cycle detected: {cycle}")
    _chain.add(name)
    logger.debug("Resolving template: %s (chain=%s)", name, _chain)

    raw = _load_template_raw(name)
    child = _parse_template_data(raw, name)

    # 1. Resolve extends chain
    if child.extends is not None:
        parent = resolve_template(child.extends, _chain)
        child = _merge_templates(parent, child, raw)

    # 2. Apply mixins in order
    for mixin_name in child.mixins:
        mixin = load_mixin(mixin_name)
        child = _apply_mixin(child, mixin)

    # 3. Validate that all resolved pane commands are non-empty.
    #    Empty commands are allowed during merge (child inherits from parent),
    #    but the final resolved template must have a command for every pane.
    for w in child.windows:
        for p in w.panes:
            if not p.command:
                raise ConfigLoadError(
                    f"template '{name}'",
                    f"window '{w.name}' pane has empty command after resolution",
                )

    return child


def load_mixin(name: str) -> TemplateMixinConfig:
    """Load a template mixin TOML from local or global mixins dir."""
    from pydantic import ValidationError

    path: Path | None = None
    local = project_templates_dir()
    if local:
        candidate = local / "mixins" / f"{name}.toml"
        if candidate.exists():
            path = candidate
    if path is None:
        path = mixins_dir() / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No mixin config: {path}")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoadError(path, f"malformed TOML: {e}") from e

    mixin_section = data.get("mixin", {})
    # Windows in mixins can appear as [[windows]] or [[mixin.windows]].
    # Support both conventions; mixin-nested takes precedence if present.
    windows_section = mixin_section.get("windows", data.get("windows", []))

    try:
        return TemplateMixinConfig(
            name=mixin_section.get("name", name),
            description=mixin_section.get("description", ""),
            git=TemplateGitConfig.model_validate(mixin_section.get("git", {})),
            env=mixin_section.get("env", {}),
            mcp=mixin_section.get("mcp", []),
            windows=windows_section,
            setup_commands=mixin_section.get("setup_commands", []),
        )
    except ValidationError as e:
        raise ConfigLoadError(path, f"invalid mixin: {e}") from e


def _apply_mixin(
    template: SessionTemplateConfig,
    mixin: TemplateMixinConfig,
) -> SessionTemplateConfig:
    """Apply a mixin additively to a resolved template.

    Additive rules:
    - git: non-empty mixin fields overwrite template fields
    - env: mixin values merge in (mixin wins on conflict)
    - mcp: union, deduplicated, sorted
    - windows: mixin windows appended
    - setup_commands: mixin commands appended
    """

    merged_git = TemplateGitConfig(
        user_name=mixin.git.user_name or template.git.user_name,
        user_email=mixin.git.user_email or template.git.user_email,
        commit_template=mixin.git.commit_template or template.git.commit_template,
        branch_prefix=mixin.git.branch_prefix or template.git.branch_prefix,
    )
    return template.model_copy(
        update={
            "git": merged_git,
            "env": {**template.env, **mixin.env},
            "mcp": sorted(set(template.mcp) | set(mixin.mcp)),
            "windows": list(template.windows) + list(mixin.windows),
            "setup_commands": list(template.setup_commands) + list(mixin.setup_commands),
        }
    )


def load_template(name: str) -> SessionTemplateConfig:
    """Load a session template TOML with full inheritance resolution."""
    return resolve_template(name)


def refresh_tools() -> list[str]:
    """Re-copy bundled tool profiles to the user's config dir, overwriting existing files.

    Unlike ``scaffold_defaults()``, this always overwrites.  Use it when bundled tool
    profiles have been updated and the user wants to pull in the latest version.

    Returns:
        Sorted list of relative filenames that were refreshed (e.g. ``["omp.toml", "pi.toml"]``).
        Returns an empty list and logs a warning if the bundled source dir is missing.
    """
    import shutil

    src = _examples_dir() / "tools"
    if not src.is_dir():
        logger.warning("Bundled tool profiles not found at %s", src)
        return []

    dst = config_dir() / "tools"
    dst.mkdir(parents=True, exist_ok=True)

    refreshed: list[str] = []
    for src_file in sorted(src.glob("*.toml")):
        dst_file = dst / src_file.name
        shutil.copy2(src_file, dst_file)
        refreshed.append(src_file.name)
        logger.debug("Refreshed tool profile: %s", src_file.name)

    return refreshed


def load_project_config(git_root: str) -> ProjectConfig | None:
    """Load project-level config from ``<git_root>/.shoal.toml``.

    Returns ``None`` if the file does not exist.
    """
    from pydantic import ValidationError

    from shoal.models.config import ProjectConfig

    path = Path(git_root) / ".shoal.toml"
    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(path, f"TOML parse error: {exc}") from exc

    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, f"validation error: {exc}") from exc


def discover_skills(git_root: str | None = None) -> list[SkillConfig]:
    """Discover skills from project-local and global paths.

    Search order:
    1. ``<git_root>/.shoal/skills/*/SKILL.md`` (project-local)
    2. ``~/.config/shoal/skills/*/SKILL.md`` (global)

    Returns parsed ``SkillConfig`` for each valid skill found.
    Duplicates (same name) resolved by local-wins.
    """
    import re

    from shoal.models.config import SkillConfig

    _FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    seen: dict[str, SkillConfig] = {}

    search_paths: list[Path] = []
    if git_root:
        local = Path(git_root) / ".shoal" / "skills"
        if local.is_dir():
            search_paths.append(local)
    global_skills = config_dir() / "skills"
    if global_skills.is_dir():
        search_paths.append(global_skills)

    for skills_dir in search_paths:
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_md.read_text()
            m = _FM_RE.match(text)
            if not m:
                logger.debug("Skipping skill without frontmatter: %s", skill_md)
                continue
            fm: dict[str, str] = {}
            for line in m.group(1).splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
            name = fm.get("name", skill_md.parent.name)
            description = fm.get("description", "")
            raw_tools = fm.get("allowed-tools", fm.get("allowed_tools", ""))
            tools = [s.strip() for s in raw_tools.split(",") if s.strip()] if raw_tools else []
            if name not in seen:
                seen[name] = SkillConfig(
                    name=name,
                    description=description,
                    allowed_tools=tools,
                    path=str(skill_md),
                )

    return list(seen.values())


def load_workspace_config(git_root: str) -> WorkspaceConfig | None:
    """Load workspace manifest from ``<git_root>/.shoal/workspace.toml``.

    Returns ``None`` if the file does not exist.  Raises ``ConfigLoadError``
    on parse or validation errors so the caller can surface them.
    """
    from pydantic import ValidationError

    from shoal.models.config import TeamConfig, WorkspaceConfig

    ws_path = Path(git_root) / ".shoal" / "workspace.toml"
    if not ws_path.exists():
        return None

    try:
        with open(ws_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(ws_path, f"TOML parse error: {exc}") from exc

    ws_data = data.get("workspace", {})

    # Parse [teams.*] section (top-level, not nested under [workspace])
    teams_data = data.get("teams", {})
    teams: dict[str, TeamConfig] = {}
    for slug, team_values in teams_data.items():
        teams[slug] = TeamConfig.model_validate(team_values)
    ws_data["teams"] = teams

    try:
        return WorkspaceConfig.model_validate(ws_data)
    except ValidationError as exc:
        raise ConfigLoadError(ws_path, f"validation error: {exc}") from exc


def load_project_hooks() -> list[ProjectHookEntry]:
    """Load project-local lifecycle hooks from ``.shoal/hooks.toml``.

    Returns an empty list if the file does not exist or the git root cannot
    be determined.  Validation errors are logged and that entry is skipped.
    """
    from shoal.core import git
    from shoal.models.config import ProjectHookEntry

    try:
        root = git.git_root(".")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    hooks_path = Path(root) / ".shoal" / "hooks.toml"
    if not hooks_path.exists():
        return []

    try:
        data = tomllib.loads(hooks_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        logger.warning("hooks.toml parse error: %s", exc)
        return []

    entries: list[ProjectHookEntry] = []
    for raw in data.get("hooks", []):
        try:
            entries.append(ProjectHookEntry.model_validate(raw))
        except Exception as exc:
            logger.warning("Skipping invalid hooks.toml entry %r: %s", raw, exc)
    return entries
