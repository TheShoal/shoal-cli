"""Pydantic models for shoal configuration files."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator


class GeneralConfig(BaseModel):
    default_tool: str = "opencode"
    state_dir: str = "~/.local/share/shoal"
    worktree_dir: str = ".worktrees"


class TmuxConfig(BaseModel):
    session_prefix: str = "_"
    popup_width: str = "90%"
    popup_height: str = "90%"
    popup_key: str = "S"
    startup_commands: list[str] = Field(
        default_factory=lambda: ["send-keys -t {tmux_session} '{tool_command}' Enter"]
    )


class StatusBarConfig(BaseModel):
    max_display: int = 5
    separator: str = "  "
    flash_waiting: bool = True


class NotificationsConfig(BaseModel):
    enabled: bool = True
    timeout_seconds: int = 300


class RoboGlobalConfig(BaseModel):
    default_tool: str = "opencode"
    default_profile: str = "default"
    session_prefix: str = "__"


class RemoteHostConfig(BaseModel):
    """Configuration for a remote Shoal host."""

    host: str
    port: int = 22
    user: str = ""
    identity_file: str = ""
    api_port: int = 8080


class ShoalConfig(BaseModel):
    """Root config — maps to ~/.config/shoal/config.toml."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    status_bar: StatusBarConfig = Field(default_factory=StatusBarConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    robo: RoboGlobalConfig = Field(default_factory=RoboGlobalConfig)
    remote: dict[str, RemoteHostConfig] = Field(default_factory=dict)


# --- Tool config models (tools/<name>.toml) ---


class DetectionPatterns(BaseModel):
    busy_patterns: list[str] = Field(default_factory=list)
    waiting_patterns: list[str] = Field(default_factory=list)
    error_patterns: list[str] = Field(default_factory=list)
    idle_patterns: list[str] = Field(default_factory=list)

    _compiled_error: list[re.Pattern[str]] = PrivateAttr(default_factory=list)
    _compiled_waiting: list[re.Pattern[str]] = PrivateAttr(default_factory=list)
    _compiled_busy: list[re.Pattern[str]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def compile_patterns(self) -> DetectionPatterns:
        """Pre-compile all pattern lists as regex for efficient matching."""
        self._compiled_error = _compile_patterns(self.error_patterns)
        self._compiled_waiting = _compile_patterns(self.waiting_patterns)
        self._compiled_busy = _compile_patterns(self.busy_patterns)
        return self


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    """Compile string patterns into regex Pattern objects."""
    compiled: list[re.Pattern[str]] = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{p}': {e}") from e
    return compiled


class MCPToolConfig(BaseModel):
    config_cmd: str = ""
    config_file: str = ""
    socket_env: str = ""


class ToolConfig(BaseModel):
    """Flattened tool config — merges [tool], [detection], [mcp] sections."""

    name: str
    command: str
    icon: str = "●"
    detection: DetectionPatterns = Field(default_factory=DetectionPatterns)
    mcp: MCPToolConfig = Field(default_factory=MCPToolConfig)


# --- Robo profile models (robo/<name>.toml) ---


class MonitoringConfig(BaseModel):
    poll_interval: int = 10
    waiting_timeout: int = 300


class EscalationConfig(BaseModel):
    notify: bool = True
    auto_respond: bool = False


class TasksConfig(BaseModel):
    log_file: str = "task-log.md"


class RoboProfileConfig(BaseModel):
    """Robo profile — maps to ~/.config/shoal/robo/<name>.toml."""

    name: str = "default"
    tool: str = "opencode"
    auto_approve: bool = False
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)


# --- Session template models (templates/<name>.toml) ---


class TemplateWorktreeConfig(BaseModel):
    name: str = ""
    create_branch: bool = False


class TemplatePaneConfig(BaseModel):
    split: Literal["root", "right", "down"] = "root"
    size: str = ""
    title: str = ""
    command: str

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
    name: str
    description: str = ""
    extends: str | None = None
    mixins: list[str] = Field(default_factory=list)
    tool: str = "opencode"
    worktree: TemplateWorktreeConfig = Field(default_factory=TemplateWorktreeConfig)
    env: dict[str, str] = Field(default_factory=dict)
    mcp: list[str] = Field(default_factory=list)
    windows: list[TemplateWindowConfig] = Field(default_factory=list)

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

    name: str
    description: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    mcp: list[str] = Field(default_factory=list)
    windows: list[TemplateWindowConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(f"Mixin name '{v}' must be alphanumeric with dashes/underscores")
        return v
