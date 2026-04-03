"""Pydantic models for shoal configuration files.

Re-exports all config models so ``from shoal.models.config import X`` continues
to work unchanged across the codebase.
"""

from shoal.models.config.claw import ClawConfig
from shoal.models.config.general import (
    ClawSchedulerConfig,
    DreamerAIConfig,
    DreamerConfig,
    GeneralConfig,
    NotificationsConfig,
    OperatorConfig,
    ProactiveConfig,
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
    ProactiveSupervisorConfig,
    RoboProfileConfig,
    TasksConfig,
)
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
from shoal.models.config.workspace import (
    CoordinatorConfig,
    ProjectConfig,
    SkillConfig,
    WorkspaceConfig,
)

__all__ = [
    "ClawConfig",
    "ClawSchedulerConfig",
    "CoordinatorConfig",
    "DetectionPatterns",
    "DreamerAIConfig",
    "DreamerConfig",
    "EscalationConfig",
    "GeneralConfig",
    "MCPToolConfig",
    "MonitoringConfig",
    "NotificationsConfig",
    "OperatorConfig",
    "ProactiveConfig",
    "ProactiveSupervisorConfig",
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
    "TemplateGitConfig",
    "TemplateMixinConfig",
    "TemplatePaneConfig",
    "TemplateWindowConfig",
    "TemplateWorktreeConfig",
    "TmuxConfig",
    "ToolConfig",
    "WorkspaceConfig",
]
