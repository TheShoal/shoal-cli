"""Pydantic models for shoal configuration files.

Re-exports all config models so ``from shoal.models.config import X`` continues
to work unchanged across the codebase.
"""

from shoal.models.config.general import (
    GeneralConfig,
    NotificationsConfig,
    OperatorConfig,
    RemoteHostConfig,
    RoboGlobalConfig,
    ShoalConfig,
    StatusBarConfig,
    TmuxConfig,
)
from shoal.models.config.hooks import ProjectHookEntry
from shoal.models.config.robo import (
    EscalationConfig,
    MonitoringConfig,
    RoboProfileConfig,
    TasksConfig,
)
from shoal.models.config.templates import (
    SessionTemplateConfig,
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
from shoal.models.config.workspace import ProjectConfig, SkillConfig, WorkspaceConfig

__all__ = [
    "DetectionPatterns",
    "EscalationConfig",
    "GeneralConfig",
    "MCPToolConfig",
    "MonitoringConfig",
    "NotificationsConfig",
    "OperatorConfig",
    "ProjectConfig",
    "ProjectHookEntry",
    "RemoteHostConfig",
    "RoboGlobalConfig",
    "RoboProfileConfig",
    "SessionTemplateConfig",
    "ShoalConfig",
    "SkillConfig",
    "StatusBarConfig",
    "TasksConfig",
    "TemplateMixinConfig",
    "TemplatePaneConfig",
    "TemplateWindowConfig",
    "TemplateWorktreeConfig",
    "TmuxConfig",
    "ToolConfig",
    "WorkspaceConfig",
]
