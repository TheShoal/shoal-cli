"""Pydantic models for shoal configuration files."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeneralConfig(BaseModel):
    default_tool: str = "claude"
    state_dir: str = "~/.local/share/shoal"
    worktree_dir: str = ".worktrees"


class TmuxConfig(BaseModel):
    session_prefix: str = "shoal"
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


# Backward compatibility alias
ConductorGlobalConfig = RoboGlobalConfig


class ShoalConfig(BaseModel):
    """Root config — maps to ~/.config/shoal/config.toml."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    status_bar: StatusBarConfig = Field(default_factory=StatusBarConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    robo: RoboGlobalConfig = Field(default_factory=RoboGlobalConfig, alias="conductor")


# --- Tool config models (tools/<name>.toml) ---


class DetectionPatterns(BaseModel):
    busy_patterns: list[str] = Field(default_factory=list)
    waiting_patterns: list[str] = Field(default_factory=list)
    error_patterns: list[str] = Field(default_factory=list)
    idle_patterns: list[str] = Field(default_factory=list)


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


# Backward compatibility alias
ConductorProfileConfig = RoboProfileConfig
