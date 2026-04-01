"""General, tmux, status-bar, notifications, operator, and root config models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shoal.models.config.claw import ClawConfig


class GeneralConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_tool: str = "omp"
    worktree_dir: str = ".worktrees"
    use_nerd_fonts: bool = True
    auto_commit: bool = False
    """Automatically commit dirty worktrees when a session is killed."""


class TmuxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_prefix: str = "_"
    popup_width: str = "90%"
    popup_height: str = "90%"
    popup_key: str = "S"
    startup_commands: list[str] = Field(
        default_factory=lambda: ["send-keys -t {tmux_session} '{tool_command}' Enter"]
    )


class StatusBarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_display: int = 5
    separator: str = "  "
    flash_waiting: bool = True


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    timeout_seconds: int = 300


class RoboGlobalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_tool: str = "omp"
    default_profile: str = "default"
    session_prefix: str = "__"


class RemoteHostConfig(BaseModel):
    """Configuration for a remote Shoal host."""

    model_config = ConfigDict(extra="forbid")

    host: str
    port: int = 22
    user: str = ""
    identity_file: str = ""
    api_port: int = 8080


class OperatorConfig(BaseModel):
    """Operator-board display thresholds — maps to [operator] in config.toml."""

    model_config = ConfigDict(extra="forbid")

    # A waiting session is promoted to 'blocked' after this many minutes.
    blocked_after_minutes: int = 5
    # An idle session is flagged as 'stale' after this many minutes.
    stale_after_minutes: int = 30


class DreamerConfig(BaseModel):
    """Dreamer pane configuration — maps to [dreamer] in config.toml."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str = "gpt-oss-20b"
    log_lines: int = 50
    summary_interval_seconds: int = 300


class ShoalConfig(BaseModel):
    """Root config — maps to ~/.config/shoal/config.toml."""

    model_config = ConfigDict(extra="forbid")

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    status_bar: StatusBarConfig = Field(default_factory=StatusBarConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    robo: RoboGlobalConfig = Field(default_factory=RoboGlobalConfig)
    remote: dict[str, RemoteHostConfig] = Field(default_factory=dict)
    operator: OperatorConfig = Field(default_factory=OperatorConfig)
    dreamer: DreamerConfig = Field(default_factory=DreamerConfig)
    claw: ClawConfig = Field(default_factory=ClawConfig)
