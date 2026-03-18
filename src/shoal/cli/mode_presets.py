"""Single-session mode defaults for `shoal new`."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shoal.core.config import available_templates

MODE_NAMES: tuple[str, ...] = (
    "feature-lane",
    "author-review",
    "remote-batch",
)


@dataclass(frozen=True)
class ModeDefaults:
    """Resolved defaults for a single `shoal new --mode ...` invocation."""

    mode: str
    template: str | None
    tool: str | None
    worktree: str
    branch: bool


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

    if mode not in MODE_NAMES:
        choices = ", ".join(MODE_NAMES)
        raise ValueError(f"Unknown mode '{mode}'. Choose one of: {choices}")

    preferred_template: str | None = None
    fallback_tool: str | None = None
    worktree_prefix = "feat"

    if mode == "feature-lane":
        preferred_template = "codex-dev"
        fallback_tool = "codex"
        worktree_prefix = "feat"
    elif mode == "author-review":
        preferred_template = "claude-review"
        fallback_tool = "claude"
        worktree_prefix = "review"
    elif mode == "remote-batch":
        preferred_template = "claude-dev"
        fallback_tool = "claude"
        worktree_prefix = "batch"

    resolved_template = template
    if resolved_template is None and tool is None and preferred_template in available_templates():
        resolved_template = preferred_template

    resolved_tool = tool
    if resolved_tool is None and resolved_template is None:
        resolved_tool = fallback_tool

    resolved_worktree = worktree or f"{worktree_prefix}/{_worktree_slug(name, project_name)}"

    return ModeDefaults(
        mode=mode,
        template=resolved_template,
        tool=resolved_tool,
        worktree=resolved_worktree,
        branch=branch or True,
    )


def _worktree_slug(name: str | None, project_name: str) -> str:
    """Build a branch-safe slug seed from an explicit session name or project name."""

    seed = name.split("/")[-1] if name else project_name
    normalized = seed.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9-]", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or project_name.lower()
