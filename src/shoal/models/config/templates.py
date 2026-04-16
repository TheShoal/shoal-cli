"""Session template models (templates/<name>.toml)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TemplateGitConfig(BaseModel):
    """Per-session git identity and commit conventions.

    All fields are optional.  Set only what the template needs to override.
    Values are applied at session creation time via ``git config --local``
    in the worktree, and as ``GIT_AUTHOR_*`` / ``GIT_COMMITTER_*`` env vars.
    """

    model_config = ConfigDict(extra="forbid")

    user_name: str = ""
    """git config user.name for commits made in this session."""
    user_email: str = ""
    """git config user.email for commits made in this session."""
    commit_template: str = ""
    """Path to a commit message template file (git config commit.template)."""
    branch_prefix: str = ""
    """Conventional prefix prepended when auto-naming branches, e.g. 'feat/' or 'fix/'.

    Applied during ``shoal new`` when a branch is auto-named from the session name.
    """
    pre_commit_config: str = ""
    """Path to a ``.pre-commit-config.yaml`` file to symlink into the session worktree.

    When set, ``_apply_template_git_config_async`` creates a symlink at
    ``<worktree>/.pre-commit-config.yaml -> <pre_commit_config>`` so that
    ``pre-commit`` picks up the shared config automatically.  The source path
    may be absolute or relative to the git root of the host repo.
    Silently skipped if the source path does not exist.
    """


class TemplateWorktreeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    create_branch: bool = False
    post_worktree_create: str = ""


class TemplatePaneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: Literal["root", "right", "down"] = "root"
    size: str = ""
    title: str = ""
    command: str = ""

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: str) -> str:
        if not v:
            return v
        stripped = v.strip().rstrip("%")
        if not stripped.isdigit() or not (1 <= int(stripped) <= 99):
            raise ValueError(f"Pane size must be 1-99% (got '{v}')")
        return v


class TemplateWindowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cwd: str = ""
    layout: str = ""
    focus: bool = False
    panes: list[TemplatePaneConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_first_pane_is_root(self) -> TemplateWindowConfig:
        if self.panes and self.panes[0].split != "root":
            raise ValueError(
                f"Window '{self.name}': first pane must have split='root', "
                f"got '{self.panes[0].split}'"
            )
        return self


class SessionTemplateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    extends: str | None = None
    mixins: list[str] = Field(default_factory=list)
    tool: str = "pi"
    mode: str = ""
    tags: list[str] = Field(default_factory=list)
    preferred_model: str | None = None
    allowed_models: list[str] = Field(default_factory=list)
    worktree: TemplateWorktreeConfig = Field(default_factory=TemplateWorktreeConfig)
    git: TemplateGitConfig = Field(default_factory=TemplateGitConfig)
    env: dict[str, str] = Field(default_factory=dict)
    mcp: list[str] = Field(default_factory=list)
    windows: list[TemplateWindowConfig] = Field(default_factory=list)
    setup_commands: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(f"Template name '{v}' must be alphanumeric with dashes/underscores")
        return v

    @model_validator(mode="after")
    def validate_has_windows(self) -> SessionTemplateConfig:
        if not self.windows and not self.extends:
            raise ValueError("Template must define at least one window or use 'extends'")
        return self


class TemplateMixinConfig(BaseModel):
    """A mixin template fragment: additive env, mcp, and windows."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    git: TemplateGitConfig = Field(default_factory=TemplateGitConfig)
    mcp: list[str] = Field(default_factory=list)
    windows: list[TemplateWindowConfig] = Field(default_factory=list)
    setup_commands: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(f"Mixin name '{v}' must be alphanumeric with dashes/underscores")
        return v
