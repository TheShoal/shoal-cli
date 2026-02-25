"""Tests for v0.8.0 features: Pi integration, template validation,
MCP name validation, failure compensation, and nvim diagnostics safety."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shoal.core.detection import detect_status
from shoal.models.config import (
    DetectionPatterns,
    SessionTemplateConfig,
    TemplatePaneConfig,
    TemplateWindowConfig,
    TemplateWorktreeConfig,
    ToolConfig,
)
from shoal.models.state import SessionStatus
from shoal.services.mcp_pool import validate_mcp_name

# ---------------------------------------------------------------------------
# Pi tool configuration
# ---------------------------------------------------------------------------


class TestPiToolConfig:
    def test_loads_pi_tool(self, mock_dirs):
        from shoal.core.config import load_tool_config

        cfg = load_tool_config("pi")
        assert cfg.name == "pi"
        assert cfg.command == "pi"
        assert cfg.icon == "🥧"
        assert cfg.status_provider == "pi"

    def test_pi_detection_patterns(self, mock_dirs):
        from shoal.core.config import load_tool_config

        cfg = load_tool_config("pi")
        assert "thinking" in cfg.detection.busy_patterns
        assert "generating" in cfg.detection.busy_patterns
        assert "Error:" in cfg.detection.error_patterns
        assert "permission" in cfg.detection.waiting_patterns
        assert "❯" not in cfg.detection.waiting_patterns

    def test_pi_available_tools(self, mock_dirs):
        from shoal.core.config import available_tools

        tools = available_tools()
        assert "pi" in tools
        assert "claude" in tools
        assert "opencode" in tools


class TestPiStatusDetection:
    """Test Pi coding agent detection patterns."""

    def _pi_tool(self) -> ToolConfig:
        return ToolConfig(
            name="pi",
            command="pi",
            icon="🥧",
            detection=DetectionPatterns(
                busy_patterns=[
                    "thinking",
                    "generating",
                    "executing",
                    "reading",
                    "writing",
                    "editing",
                ],
                waiting_patterns=["permission", "confirm", "approve", "y/n"],
                error_patterns=["Error:", "error:", "ERROR", "FAILED"],
            ),
        )

    def test_pi_busy_thinking(self):
        tool = self._pi_tool()
        assert detect_status("thinking about the code...", tool) == SessionStatus.running

    def test_pi_busy_generating(self):
        tool = self._pi_tool()
        assert detect_status("generating response\n...", tool) == SessionStatus.running

    def test_pi_busy_executing(self):
        tool = self._pi_tool()
        assert detect_status("executing bash command", tool) == SessionStatus.running

    def test_pi_waiting_permission(self):
        tool = self._pi_tool()
        assert detect_status("Do you confirm this action? (y/n)", tool) == SessionStatus.waiting

    def test_pi_waiting_approve(self):
        tool = self._pi_tool()
        assert detect_status("Please approve the edit", tool) == SessionStatus.waiting

    def test_pi_error(self):
        tool = self._pi_tool()
        assert detect_status("Error: file not found", tool) == SessionStatus.error

    def test_pi_error_failed(self):
        tool = self._pi_tool()
        assert detect_status("Build FAILED with 3 errors", tool) == SessionStatus.error

    def test_pi_idle(self):
        tool = self._pi_tool()
        assert detect_status("$ ls\nfile1.txt", tool) == SessionStatus.idle

    def test_pi_error_over_waiting(self):
        """Error should take priority over waiting."""
        tool = self._pi_tool()
        content = "Error: permission denied\nDo you approve?"
        assert detect_status(content, tool) == SessionStatus.error

    def test_pi_idle_at_prompt(self):
        """Prompt character should be idle, not waiting (pattern fix)."""
        tool = self._pi_tool()
        assert detect_status("❯", tool) == SessionStatus.idle

    def test_pi_waiting_only_on_explicit_prompts(self):
        """Waiting should only trigger on explicit confirmation prompts."""
        tool = self._pi_tool()
        assert detect_status("permission denied — confirm?", tool) == SessionStatus.waiting


# ---------------------------------------------------------------------------
# Template schema validation
# ---------------------------------------------------------------------------


class TestTemplateValidation:
    def test_valid_template(self):
        t = SessionTemplateConfig(
            name="my-template",
            description="Test template",
            tool="pi",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[TemplatePaneConfig(split="root", command="pi")],
                ),
            ],
        )
        assert t.name == "my-template"

    def test_template_name_validation(self):
        with pytest.raises(ValidationError, match="alphanumeric"):
            SessionTemplateConfig(
                name="bad name with spaces",
                windows=[
                    TemplateWindowConfig(
                        name="w",
                        panes=[TemplatePaneConfig(split="root", command="echo")],
                    ),
                ],
            )

    def test_template_empty_name(self):
        with pytest.raises(ValidationError):
            SessionTemplateConfig(
                name="",
                windows=[
                    TemplateWindowConfig(
                        name="w",
                        panes=[TemplatePaneConfig(split="root", command="echo")],
                    ),
                ],
            )

    def test_template_requires_windows(self):
        with pytest.raises(ValidationError, match="at least one window"):
            SessionTemplateConfig(name="no-windows", windows=[])

    def test_first_pane_must_be_root(self):
        with pytest.raises(ValidationError, match="first pane must have split='root'"):
            TemplateWindowConfig(
                name="bad",
                panes=[TemplatePaneConfig(split="right", command="echo")],
            )

    def test_pane_size_validation_valid(self):
        pane = TemplatePaneConfig(split="root", size="50%", command="echo")
        assert pane.size == "50%"

    def test_pane_size_validation_empty(self):
        pane = TemplatePaneConfig(split="root", size="", command="echo")
        assert pane.size == ""

    def test_pane_size_non_numeric(self):
        with pytest.raises(ValidationError, match="1-99%"):
            TemplatePaneConfig(split="root", size="abc%", command="echo")

    def test_pane_size_validation_invalid(self):
        with pytest.raises(ValidationError, match="1-99%"):
            TemplatePaneConfig(split="root", size="150%", command="echo")

    def test_pane_size_validation_zero(self):
        with pytest.raises(ValidationError, match="1-99%"):
            TemplatePaneConfig(split="root", size="0%", command="echo")

    def test_template_with_worktree(self):
        t = SessionTemplateConfig(
            name="feature-dev",
            tool="pi",
            worktree=TemplateWorktreeConfig(name="feat/{template_name}", create_branch=True),
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
                ),
            ],
        )
        assert t.worktree.create_branch is True

    def test_template_with_env(self):
        t = SessionTemplateConfig(
            name="with-env",
            tool="pi",
            env={"SHOAL_TOOL": "pi", "MY_VAR": "value"},
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="echo")],
                ),
            ],
        )
        assert t.env["SHOAL_TOOL"] == "pi"

    def test_pi_dev_template_loads(self, mock_dirs):
        """Test that pi-dev template can be loaded from config."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "pi-dev.toml").write_text(
            """
[template]
name = "pi-dev"
description = "Pi coding agent with terminal pane"
tool = "pi"

[template.worktree]
name = "feat/{template_name}"
create_branch = true

[[windows]]
name = "editor"
focus = true

[[windows.panes]]
split = "root"
size = "65%"
title = "pi-agent"
command = "{tool_command}"

[[windows.panes]]
split = "right"
size = "35%"
title = "terminal"
command = "echo terminal"

[[windows]]
name = "tools"

[[windows.panes]]
split = "root"
title = "runner"
command = "echo runner"
"""
        )

        from shoal.core.config import load_template

        t = load_template("pi-dev")
        assert t.name == "pi-dev"
        assert t.tool == "pi"
        assert len(t.windows) == 2
        assert len(t.windows[0].panes) == 2
        assert t.windows[0].panes[0].size == "65%"


# ---------------------------------------------------------------------------
# MCP name validation
# ---------------------------------------------------------------------------


class TestMcpNameValidation:
    def test_valid_names(self):
        for name in ["memory", "filesystem", "my-server", "test_123", "a"]:
            validate_mcp_name(name)  # should not raise

    def test_empty_name(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_mcp_name("")

    def test_special_characters(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("bad/name")

    def test_shell_metacharacters(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("$(whoami)")

    def test_dot_in_name(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("my.server")

    def test_space_in_name(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("my server")

    def test_leading_dash(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("-badname")

    def test_too_long(self):
        with pytest.raises(ValueError, match="Invalid MCP name"):
            validate_mcp_name("a" * 65)

    def test_max_length(self):
        validate_mcp_name("a" * 64)  # should not raise


# ---------------------------------------------------------------------------
# Nvim diagnostics Lua script safety
# ---------------------------------------------------------------------------


class TestNvimDiagnosticsLua:
    def test_lua_script_is_valid(self):
        """Verify the Lua diagnostics script is a well-formed string."""
        from shoal.cli.nvim import _DIAGNOSTICS_LUA

        assert "vim.diagnostic.get" in _DIAGNOSTICS_LUA
        assert "table.concat" in _DIAGNOSTICS_LUA
        assert "return" in _DIAGNOSTICS_LUA
        # Ensure no single-quote wrapping issues
        assert "luaeval" not in _DIAGNOSTICS_LUA

    def test_lua_script_no_shell_injection_vectors(self):
        """Ensure the Lua script doesn't contain shell-unsafe patterns."""
        from shoal.cli.nvim import _DIAGNOSTICS_LUA

        # No backtick execution
        assert "`" not in _DIAGNOSTICS_LUA
        # No $() command substitution
        assert "$(" not in _DIAGNOSTICS_LUA
