"""Tool configuration models (tools/<name>.toml)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class DetectionPatterns(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    config_cmd: str = ""
    config_file: str = ""
    socket_env: str = ""


class ToolConfig(BaseModel):
    """Flattened tool config — merges [tool], [detection], [mcp] sections."""

    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    icon: str = "●"
    status_provider: Literal["regex", "pi", "opencode_compat"] | None = None
    send_keys_delay: float = 0.0
    # Prompt delivery mode for initial session prompts:
    #   "keys"  — send_keys after launch (default, works with any tool)
    #   "arg"   — bake prompt into the launch command as a positional argument
    #             if prompt_file_prefix is set (e.g. "@"), writes to a file first
    #   "flag"  — bake prompt into the launch command via prompt_flag (e.g. "--prompt")
    input_mode: Literal["keys", "arg", "flag"] = "keys"
    prompt_flag: str = ""  # flag name for "flag" mode, e.g. "--prompt"
    prompt_file_prefix: str = ""  # prefix for "arg" mode file path, e.g. "@" for omp
    detection: DetectionPatterns = Field(default_factory=DetectionPatterns)
    mcp: MCPToolConfig = Field(default_factory=MCPToolConfig)
