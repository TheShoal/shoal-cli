"""Configuration loading and XDG path helpers."""

from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from shoal.models.config import (
    DetectionPatterns,
    MCPToolConfig,
    RoboProfileConfig,
    SessionTemplateConfig,
    ShoalConfig,
    TemplateMixinConfig,
    TemplateWorktreeConfig,
    ToolConfig,
)

logger = logging.getLogger("shoal.config")


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


def config_dir() -> Path:
    """Return Shoal config directory.

    Reads ``XDG_CONFIG_HOME`` env var, falling back to ``~/.config/shoal``.
    """
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "shoal"


def state_dir() -> Path:
    """Return Shoal persistent data directory (sessions, robo state).

    Reads ``XDG_DATA_HOME`` env var, falling back to ``~/.local/share/shoal``.
    """
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "shoal"


def runtime_dir() -> Path:
    """Return Shoal transient runtime directory (PIDs, logs).

    Reads ``XDG_STATE_HOME`` env var, falling back to ``~/.local/state/shoal``.
    """
    base = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "shoal"


def ensure_dirs() -> None:
    """Create all required state and runtime directories."""
    cfg = config_dir()
    for subdir in ("templates", "templates/mixins"):
        (cfg / subdir).mkdir(parents=True, exist_ok=True)

    base = state_dir()
    for subdir in ("sessions", "journals", "mcp-pool/pids", "mcp-pool/sockets", "robo", "remote"):
        (base / subdir).mkdir(parents=True, exist_ok=True)
    rt = runtime_dir()
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
    path = config_dir() / "config.toml"
    logger.debug("Loading config from %s", path)
    if not path.exists():
        return ShoalConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return ShoalConfig.model_validate(data)


def load_tool_config(name: str) -> ToolConfig:
    """Load a tool config, flattening [tool] + [detection] + [mcp] sections."""
    logger.debug("Loading tool config: %s", name)
    path = config_dir() / "tools" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No tool config: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    tool_section = data.get("tool", {})
    detection_section = data.get("detection", {})
    mcp_section = data.get("mcp", {})

    return ToolConfig(
        name=tool_section.get("name", name),
        command=tool_section.get("command", name),
        icon=tool_section.get("icon", "●"),
        detection=DetectionPatterns.model_validate(detection_section),
        mcp=MCPToolConfig.model_validate(mcp_section),
    )


def load_robo_profile(name: str) -> RoboProfileConfig:
    """Load a robo profile TOML."""
    path = config_dir() / "robo" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No robo profile: {name}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    robo_section = data.get("robo", {})
    return RoboProfileConfig(
        name=robo_section.get("name", name),
        tool=robo_section.get("tool", "opencode"),
        auto_approve=robo_section.get("auto_approve", False),
        monitoring=data.get("monitoring", {}),
        escalation=data.get("escalation", {}),
        tasks=data.get("tasks", {}),
    )


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


def load_mcp_registry() -> dict[str, str]:
    """Load MCP server registry: user file merged over built-in defaults.

    Reads ``~/.config/shoal/mcp-servers.toml``.  Each top-level key is a
    server name whose value is a table with a ``command`` key.  Built-in
    defaults are used as a fallback for servers not overridden by the user.

    Returns:
        Mapping of server name → command string.
    """
    from shoal.services.mcp_pool import _DEFAULT_SERVERS

    registry: dict[str, str] = dict(_DEFAULT_SERVERS)

    user_file = config_dir() / "mcp-servers.toml"
    if user_file.exists():
        with open(user_file, "rb") as f:
            data = tomllib.load(f)
        for name, entry in data.items():
            if isinstance(entry, dict) and "command" in entry:
                registry[name] = entry["command"]

    return registry


def load_mcp_registry_full() -> dict[str, dict[str, str]]:
    """Load the full MCP server registry with all fields per entry.

    Returns raw dicts so callers can read ``transport`` and other fields.
    """
    user_file = config_dir() / "mcp-servers.toml"
    registry: dict[str, dict[str, str]] = {}
    if user_file.exists():
        with open(user_file, "rb") as f:
            data = tomllib.load(f)
        for name, entry in data.items():
            if isinstance(entry, dict):
                registry[name] = {k: str(v) for k, v in entry.items()}
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
            with open(local_path, "rb") as f:
                return tomllib.load(f)
    path = templates_dir() / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No template config: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_template_data(
    data: dict[str, Any],
    name: str,
) -> SessionTemplateConfig:
    """Parse raw TOML dict into SessionTemplateConfig."""
    template_section = data.get("template", {})
    worktree_section = template_section.get("worktree", {})
    env_section = template_section.get("env", {})
    mcp_section = template_section.get("mcp", [])
    windows_section = data.get("windows", [])

    return SessionTemplateConfig(
        name=template_section.get("name", name),
        description=template_section.get("description", ""),
        extends=template_section.get("extends"),
        mixins=template_section.get("mixins", []),
        tool=template_section.get("tool", "opencode"),
        worktree=TemplateWorktreeConfig.model_validate(worktree_section),
        env=env_section,
        mcp=mcp_section,
        windows=windows_section,
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
    - env: parent | child (child wins on conflicts)
    - mcp: union, deduplicated, sorted
    - windows: child replaces parent entirely if child defines any
    """
    child_tmpl = child_raw.get("template", {})

    description = child.description if "description" in child_tmpl else parent.description
    tool = child.tool if "tool" in child_tmpl else parent.tool
    worktree = child.worktree if "worktree" in child_tmpl else parent.worktree
    merged_env = {**parent.env, **child.env}
    merged_mcp = sorted(set(parent.mcp) | set(child.mcp))
    merged_windows = child.windows if child.windows else parent.windows

    return SessionTemplateConfig(
        name=child.name,
        description=description,
        extends=None,
        mixins=child.mixins,
        tool=tool,
        worktree=worktree,
        env=merged_env,
        mcp=merged_mcp,
        windows=merged_windows,
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

    return child


def load_mixin(name: str) -> TemplateMixinConfig:
    """Load a template mixin TOML from local or global mixins dir."""
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
    with open(path, "rb") as f:
        data = tomllib.load(f)

    mixin_section = data.get("mixin", {})
    windows_section = data.get("windows", [])

    return TemplateMixinConfig(
        name=mixin_section.get("name", name),
        description=mixin_section.get("description", ""),
        env=mixin_section.get("env", {}),
        mcp=mixin_section.get("mcp", []),
        windows=windows_section,
    )


def _apply_mixin(
    template: SessionTemplateConfig,
    mixin: TemplateMixinConfig,
) -> SessionTemplateConfig:
    """Apply a mixin additively to a resolved template.

    Additive rules:
    - env: mixin values merge in (mixin wins on conflict)
    - mcp: union, deduplicated, sorted
    - windows: mixin windows appended
    """
    return template.model_copy(
        update={
            "env": {**template.env, **mixin.env},
            "mcp": sorted(set(template.mcp) | set(mixin.mcp)),
            "windows": list(template.windows) + list(mixin.windows),
        }
    )


def load_template(name: str) -> SessionTemplateConfig:
    """Load a session template TOML with full inheritance resolution."""
    return resolve_template(name)
