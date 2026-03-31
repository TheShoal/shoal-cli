"""Single-session mode defaults for `shoal new`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from shoal.core.config import available_templates


@dataclass(frozen=True)
class ModeSpec:
    """Specification for a named operating mode."""

    name: str
    description: str
    preferred_template: str
    fallback_tool: str
    worktree_prefix: str
    auto_tags: list[str] = field(default_factory=list)


MODE_REGISTRY: dict[str, ModeSpec] = {
    "feature-lane": ModeSpec(
        name="feature-lane",
        description="Default feature development with isolated worktree",
        preferred_template="codex-dev",
        fallback_tool="codex",
        worktree_prefix="feat",
    ),
    "author-review": ModeSpec(
        name="author-review",
        description="Author-review cycle with review tagging",
        preferred_template="claude-review",
        fallback_tool="claude",
        worktree_prefix="review",
        auto_tags=["review-ready"],
    ),
    "remote-batch": ModeSpec(
        name="remote-batch",
        description="Batch operations on remote hosts",
        preferred_template="claude-dev",
        fallback_tool="claude",
        worktree_prefix="batch",
    ),
    "planner": ModeSpec(
        name="planner",
        description="Scope and plan work before implementation",
        preferred_template="omp-dev",
        fallback_tool="omp",
        worktree_prefix="plan",
        auto_tags=["planner"],
    ),
    "implementer": ModeSpec(
        name="implementer",
        description="Execute implementation from a plan",
        preferred_template="omp-dev",
        fallback_tool="omp",
        worktree_prefix="impl",
        auto_tags=["implementer"],
    ),
    "reviewer": ModeSpec(
        name="reviewer",
        description="Review changes before merge",
        preferred_template="claude-review",
        fallback_tool="claude",
        worktree_prefix="review",
        auto_tags=["reviewer", "review-ready"],
    ),
}

MODE_NAMES: tuple[str, ...] = tuple(MODE_REGISTRY)


@dataclass(frozen=True)
class ModeDefaults:
    """Resolved defaults for a single `shoal new --mode ...` invocation."""

    mode: str
    template: str | None
    tool: str | None
    worktree: str
    branch: bool
    auto_tags: list[str] = field(default_factory=list)


def resolve_mode_defaults(
    mode: str,
    *,
    name: str | None,
    template: str | None,
    tool: str | None,
    worktree: str | None,
    branch: bool,
    project_name: str,
) -> ModeDefaults:
    """Resolve one-session defaults for a named operating mode.

    Explicit CLI values always win. Modes only fill in values the caller did not set.
    """
    spec = MODE_REGISTRY.get(mode)
    if spec is None:
        choices = ", ".join(MODE_NAMES)
        raise ValueError(f"Unknown mode '{mode}'. Choose one of: {choices}")

    resolved_template = template
    available = available_templates()
    if resolved_template is None and tool is None and spec.preferred_template in available:
        resolved_template = spec.preferred_template

    resolved_tool = tool
    if resolved_tool is None and resolved_template is None:
        resolved_tool = spec.fallback_tool

    resolved_worktree = worktree or f"{spec.worktree_prefix}/{_worktree_slug(name, project_name)}"

    return ModeDefaults(
        mode=mode,
        template=resolved_template,
        tool=resolved_tool,
        worktree=resolved_worktree,
        branch=branch or True,
        auto_tags=list(spec.auto_tags),
    )


def _worktree_slug(name: str | None, project_name: str) -> str:
    """Build a branch-safe slug seed from an explicit session name or project name."""

    seed = name.split("/")[-1] if name else project_name
    normalized = seed.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9-]", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or project_name.lower()
