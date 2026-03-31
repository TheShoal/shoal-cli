"""Meta-repo workspace manifest model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceConfig(BaseModel):
    """Meta-repo workspace manifest — maps to ``.shoal/workspace.toml``.

    Defines named sub-repositories so Shoal can route ``git worktree``
    commands to the correct nested repo instead of the meta-repo root.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    repos: dict[str, str] = Field(default_factory=dict)
    """Logical name → relative path (e.g. ``emailservice = "backend/emailservice"``)."""

    @field_validator("repos")
    @classmethod
    def validate_repos(cls, v: dict[str, str]) -> dict[str, str]:
        for key, path in v.items():
            if not key or not path:
                raise ValueError(
                    f"Workspace repo entry must have non-empty key and path (got '{key}': '{path}')"
                )
            if ".." in path.split("/") or path.startswith("/"):
                raise ValueError(f"Workspace repo path must be relative without '..': '{path}'")
        return v
