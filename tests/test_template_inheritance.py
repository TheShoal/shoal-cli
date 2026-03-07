"""Tests for template inheritance (extends) and mixin composition."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from shoal.cli.template import app as template_app
from shoal.core.config import (
    _apply_mixin,
    _load_template_raw,
    _parse_template_data,
    available_mixins,
    load_mixin,
    load_template,
)
from shoal.models.config import (
    SessionTemplateConfig,
    TemplateMixinConfig,
    TemplatePaneConfig,
    TemplateWindowConfig,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_template(templates_dir: Path, name: str, content: str) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / f"{name}.toml").write_text(content)


def _write_mixin(templates_dir: Path, name: str, content: str) -> None:
    mixins = templates_dir / "mixins"
    mixins.mkdir(parents=True, exist_ok=True)
    (mixins / f"{name}.toml").write_text(content)


BASE_TEMPLATE = """\
[template]
name = "base"
description = "Base template"
tool = "opencode"
mcp = ["memory"]

[template.worktree]
name = "feat/{template_name}"
create_branch = true

[template.env]
BASE_VAR = "base-value"
SHARED = "from-base"

[[windows]]
name = "editor"
focus = true

[[windows.panes]]
split = "root"
size = "65%"
command = "{tool_command}"
"""


CHILD_TEMPLATE = """\
[template]
name = "child"
description = "Child template"
extends = "base"
tool = "claude"
mcp = ["github"]

[template.env]
CHILD_VAR = "child-value"
SHARED = "from-child"
"""


# ---------------------------------------------------------------------------
# extends tests
# ---------------------------------------------------------------------------


class TestExtendsResolution:
    """Template inheritance via extends field."""

    def test_template_without_extends(self, mock_dirs: tuple[Path, Path]) -> None:
        """Templates without extends work unchanged (backward compat)."""
        tmp_config, _ = mock_dirs
        _write_template(tmp_config / "templates", "standalone", BASE_TEMPLATE)
        t = load_template("standalone")
        assert t.name == "base"
        assert t.extends is None
        assert len(t.windows) == 1

    def test_scalar_override(self, mock_dirs: tuple[Path, Path]) -> None:
        """Child overrides tool and description from parent."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert t.tool == "claude"
        assert t.description == "Child template"
        assert t.name == "child"

    def test_env_merge(self, mock_dirs: tuple[Path, Path]) -> None:
        """Parent env merges with child env; child wins on conflict."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert t.env["BASE_VAR"] == "base-value"
        assert t.env["CHILD_VAR"] == "child-value"
        assert t.env["SHARED"] == "from-child"

    def test_mcp_union(self, mock_dirs: tuple[Path, Path]) -> None:
        """Parent and child MCP lists are unioned and deduplicated."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert sorted(t.mcp) == ["github", "memory"]

    def test_windows_replace_when_child_defines(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child windows replace parent windows entirely."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(
            templates,
            "child-with-windows",
            """\
[template]
name = "child-with-windows"
extends = "base"

[[windows]]
name = "custom"

[[windows.panes]]
split = "root"
command = "my-tool"
""",
        )
        t = load_template("child-with-windows")
        assert len(t.windows) == 1
        assert t.windows[0].name == "custom"

    def test_windows_inherit_when_child_empty(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child without windows inherits parent windows."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert len(t.windows) == 1
        assert t.windows[0].name == "editor"

    def test_worktree_replace_when_child_defines(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child worktree section replaces parent entirely."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(
            templates,
            "child-wt",
            """\
[template]
name = "child-wt"
extends = "base"

[template.worktree]
name = "fix/{template_name}"
create_branch = false

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        t = load_template("child-wt")
        assert t.worktree.name == "fix/{template_name}"
        assert t.worktree.create_branch is False

    def test_worktree_inherit_when_not_set(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child without worktree section inherits parent worktree."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert t.worktree.name == "feat/{template_name}"
        assert t.worktree.create_branch is True

    def test_cycle_detection_two_nodes(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """A extends B extends A raises ValueError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "a",
            """\
[template]
name = "a"
extends = "b"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        _write_template(
            templates,
            "b",
            """\
[template]
name = "b"
extends = "a"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        with pytest.raises(ValueError, match="cycle"):
            load_template("a")

    def test_self_reference(self, mock_dirs: tuple[Path, Path]) -> None:
        """Template extending itself raises ValueError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "self-ref",
            """\
[template]
name = "self-ref"
extends = "self-ref"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        with pytest.raises(ValueError, match="cycle"):
            load_template("self-ref")

    def test_missing_parent(self, mock_dirs: tuple[Path, Path]) -> None:
        """Extending a nonexistent template raises FileNotFoundError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "orphan",
            """\
[template]
name = "orphan"
extends = "nonexistent"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        with pytest.raises(FileNotFoundError):
            load_template("orphan")

    def test_three_level_inheritance(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """A extends B extends C resolves correctly."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "grandparent",
            """\
[template]
name = "grandparent"
tool = "opencode"
mcp = ["memory"]

[template.env]
LEVEL = "grandparent"

[[windows]]
name = "gp-window"

[[windows.panes]]
split = "root"
command = "gp-cmd"
""",
        )
        _write_template(
            templates,
            "parent",
            """\
[template]
name = "parent"
extends = "grandparent"
mcp = ["github"]

[template.env]
LEVEL = "parent"
""",
        )
        _write_template(
            templates,
            "child",
            """\
[template]
name = "child"
extends = "parent"
tool = "claude"

[template.env]
EXTRA = "yes"
""",
        )
        t = load_template("child")
        assert t.tool == "claude"
        assert sorted(t.mcp) == ["github", "memory"]
        assert t.env["LEVEL"] == "parent"
        assert t.env["EXTRA"] == "yes"
        assert t.windows[0].name == "gp-window"

    def test_tool_inherited_when_not_set(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child without explicit tool inherits parent's tool."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "base-pi",
            """\
[template]
name = "base-pi"
tool = "pi"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        _write_template(
            templates,
            "child-no-tool",
            """\
[template]
name = "child-no-tool"
extends = "base-pi"
""",
        )
        t = load_template("child-no-tool")
        assert t.tool == "pi"

    def test_tool_override_to_default(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child explicitly setting 'opencode' overrides parent's tool."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "base-pi",
            """\
[template]
name = "base-pi"
tool = "pi"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        _write_template(
            templates,
            "child-opencode",
            """\
[template]
name = "child-opencode"
extends = "base-pi"
tool = "opencode"
""",
        )
        t = load_template("child-opencode")
        assert t.tool == "opencode"

    def test_description_inherited_when_not_set(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child without description inherits parent's."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(
            templates,
            "no-desc",
            """\
[template]
name = "no-desc"
extends = "base"
""",
        )
        t = load_template("no-desc")
        assert t.description == "Base template"

    def test_resolved_extends_is_none(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """After resolution, extends field is cleared to None."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        t = load_template("child")
        assert t.extends is None

    def test_setup_commands_child_replaces_parent(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child setup_commands replaces parent's when explicitly set."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(
            templates,
            "child-cmds",
            """\
[template]
name = "child-cmds"
extends = "base"
setup_commands = ["uv sync", "source .venv/bin/activate.fish"]
""",
        )
        t = load_template("child-cmds")
        assert t.setup_commands == ["uv sync", "source .venv/bin/activate.fish"]

    def test_setup_commands_inherits_from_parent(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Child without setup_commands inherits parent's."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "base-cmds",
            """\
[template]
name = "base-cmds"
setup_commands = ["echo setup"]

[[windows]]
name = "main"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        _write_template(
            templates,
            "child-no-cmds",
            """\
[template]
name = "child-no-cmds"
extends = "base-cmds"
""",
        )
        t = load_template("child-no-cmds")
        assert t.setup_commands == ["echo setup"]


# ---------------------------------------------------------------------------
# Mixin tests
# ---------------------------------------------------------------------------


class TestMixins:
    """Template mixin composition."""

    def test_load_mixin_basic(self, mock_dirs: tuple[Path, Path]) -> None:
        """Load a valid mixin TOML."""
        tmp_config, _ = mock_dirs
        _write_mixin(
            tmp_config / "templates",
            "mcp-mem",
            """\
[mixin]
name = "mcp-mem"
description = "Memory server"
mcp = ["memory"]
""",
        )
        m = load_mixin("mcp-mem")
        assert m.name == "mcp-mem"
        assert m.mcp == ["memory"]
        assert m.description == "Memory server"

    def test_load_mixin_missing(self, mock_dirs: tuple[Path, Path]) -> None:
        """Loading a nonexistent mixin raises FileNotFoundError."""
        _ = mock_dirs
        with pytest.raises(FileNotFoundError):
            load_mixin("nonexistent")

    def test_mixin_name_validation(self) -> None:
        """Invalid mixin names are rejected."""
        with pytest.raises(ValidationError):
            TemplateMixinConfig(name="../bad")

    def test_apply_mixin_mcp_union(self) -> None:
        """Mixin MCP servers are unioned with template."""
        template = SessionTemplateConfig(
            name="t",
            mcp=["memory"],
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        mixin = TemplateMixinConfig(name="m", mcp=["github"])
        result = _apply_mixin(template, mixin)
        assert sorted(result.mcp) == ["github", "memory"]

    def test_apply_mixin_env_merge(self) -> None:
        """Mixin env merges into template; mixin wins on conflict."""
        template = SessionTemplateConfig(
            name="t",
            env={"A": "1", "B": "template"},
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        mixin = TemplateMixinConfig(name="m", env={"B": "mixin", "C": "3"})
        result = _apply_mixin(template, mixin)
        assert result.env == {"A": "1", "B": "mixin", "C": "3"}

    def test_apply_mixin_windows_append(self) -> None:
        """Mixin windows are appended to template windows."""
        template = SessionTemplateConfig(
            name="t",
            windows=[
                TemplateWindowConfig(
                    name="main",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        mixin = TemplateMixinConfig(
            name="m",
            windows=[
                TemplateWindowConfig(
                    name="tests",
                    panes=[TemplatePaneConfig(split="root", command="y")],
                )
            ],
        )
        result = _apply_mixin(template, mixin)
        assert len(result.windows) == 2
        assert result.windows[0].name == "main"
        assert result.windows[1].name == "tests"

    def test_apply_mixin_setup_commands_append(self) -> None:
        """Mixin setup_commands are appended to the template's."""
        template = SessionTemplateConfig(
            name="t",
            setup_commands=["cmd1"],
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        mixin = TemplateMixinConfig(name="m", setup_commands=["cmd2", "cmd3"])
        result = _apply_mixin(template, mixin)
        assert result.setup_commands == ["cmd1", "cmd2", "cmd3"]

    def test_apply_mixin_setup_commands_empty_template(self) -> None:
        """Mixin setup_commands work when template has none."""
        template = SessionTemplateConfig(
            name="t",
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        mixin = TemplateMixinConfig(name="m", setup_commands=["uv sync"])
        result = _apply_mixin(template, mixin)
        assert result.setup_commands == ["uv sync"]

    def test_resolve_with_mixins(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Full resolution: extends + mixins together."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_mixin(
            templates,
            "add-gh",
            """\
[mixin]
name = "add-gh"
mcp = ["github"]

[mixin.env]
GH_TOKEN = "xxx"
""",
        )
        _write_template(
            templates,
            "mixed",
            """\
[template]
name = "mixed"
extends = "base"
mixins = ["add-gh"]
""",
        )
        t = load_template("mixed")
        assert sorted(t.mcp) == ["github", "memory"]
        assert t.env["GH_TOKEN"] == "xxx"  # noqa: S105
        assert t.env["BASE_VAR"] == "base-value"

    def test_unknown_mixin_raises(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Referencing an unknown mixin raises FileNotFoundError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "bad-mixin",
            """\
[template]
name = "bad-mixin"
mixins = ["nonexistent"]

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        with pytest.raises(FileNotFoundError):
            load_template("bad-mixin")

    def test_available_mixins_empty(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Returns empty list when no mixins exist."""
        tmp_config, _ = mock_dirs
        (tmp_config / "templates" / "mixins").mkdir(parents=True, exist_ok=True)
        assert available_mixins() == []

    def test_available_mixins_lists(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """Lists mixin names from mixins directory."""
        tmp_config, _ = mock_dirs
        _write_mixin(
            tmp_config / "templates",
            "alpha",
            """\
[mixin]
name = "alpha"
""",
        )
        _write_mixin(
            tmp_config / "templates",
            "beta",
            """\
[mixin]
name = "beta"
""",
        )
        assert available_mixins() == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestModelValidation:
    """SessionTemplateConfig validation with extends."""

    def test_no_windows_with_extends_valid(self) -> None:
        """Template with extends and no windows is valid."""
        t = SessionTemplateConfig(name="child", extends="parent")
        assert t.windows == []
        assert t.extends == "parent"

    def test_no_windows_no_extends_invalid(self) -> None:
        """Template without windows or extends raises ValidationError."""
        with pytest.raises(ValidationError, match=r"window.*extends"):
            SessionTemplateConfig(name="bad")

    def test_mixin_model_basic(self) -> None:
        """TemplateMixinConfig accepts valid data."""
        m = TemplateMixinConfig(
            name="test-mixin",
            description="Test",
            env={"K": "V"},
            mcp=["memory"],
            windows=[
                TemplateWindowConfig(
                    name="w",
                    panes=[TemplatePaneConfig(split="root", command="x")],
                )
            ],
        )
        assert m.name == "test-mixin"
        assert m.env == {"K": "V"}


# ---------------------------------------------------------------------------
# Raw loading tests
# ---------------------------------------------------------------------------


class TestRawLoading:
    """_load_template_raw and _parse_template_data."""

    def test_load_raw(self, mock_dirs: tuple[Path, Path]) -> None:
        """_load_template_raw returns raw dict."""
        tmp_config, _ = mock_dirs
        _write_template(tmp_config / "templates", "raw-test", BASE_TEMPLATE)
        raw = _load_template_raw("raw-test")
        assert isinstance(raw, dict)
        assert "template" in raw
        assert "windows" in raw

    def test_load_raw_missing(self, mock_dirs: tuple[Path, Path]) -> None:
        """_load_template_raw raises FileNotFoundError for missing."""
        _ = mock_dirs
        with pytest.raises(FileNotFoundError):
            _load_template_raw("nonexistent")

    def test_parse_template_data(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """_parse_template_data produces correct model."""
        tmp_config, _ = mock_dirs
        _write_template(tmp_config / "templates", "parse-test", CHILD_TEMPLATE)
        raw = _load_template_raw("parse-test")
        t = _parse_template_data(raw, "parse-test")
        assert t.extends == "base"
        assert t.mixins == []
        assert t.tool == "claude"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Template CLI commands with inheritance."""

    def test_ls_shows_extends_column(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """template ls output includes EXTENDS column."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        result = runner.invoke(template_app, ["ls"])
        assert result.exit_code == 0
        assert "EXTENDS" in result.output
        assert "base" in result.output

    def test_show_resolved(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show displays resolved (merged) template."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        result = runner.invoke(template_app, ["show", "child"])
        assert result.exit_code == 0
        assert '"claude"' in result.output
        assert '"BASE_VAR"' in result.output
        assert '"extends": null' in result.output

    def test_show_raw(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show --raw displays unresolved template."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        result = runner.invoke(template_app, ["show", "--raw", "child"])
        assert result.exit_code == 0
        assert '"extends": "base"' in result.output
        # Raw should NOT have parent's env
        assert "BASE_VAR" not in result.output

    def test_validate_with_extends(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """template validate follows extends chain successfully."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(templates, "base", BASE_TEMPLATE)
        _write_template(templates, "child", CHILD_TEMPLATE)
        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_validate_catches_cycle(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """template validate reports cycle errors."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "a",
            """\
[template]
name = "a"
extends = "b"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        _write_template(
            templates,
            "b",
            """\
[template]
name = "b"
extends = "a"

[[windows]]
name = "x"

[[windows.panes]]
split = "root"
command = "x"
""",
        )
        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_mixins_cmd_empty(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """template mixins with no mixins shows message."""
        tmp_config, _ = mock_dirs
        (tmp_config / "templates" / "mixins").mkdir(parents=True, exist_ok=True)
        result = runner.invoke(template_app, ["mixins"])
        assert result.exit_code == 0
        assert "No mixins" in result.output

    def test_mixins_cmd_lists(
        self,
        mock_dirs: tuple[Path, Path],
    ) -> None:
        """template mixins lists available mixins."""
        tmp_config, _ = mock_dirs
        _write_mixin(
            tmp_config / "templates",
            "mcp-mem",
            """\
[mixin]
name = "mcp-mem"
description = "Memory"
mcp = ["memory"]
""",
        )
        result = runner.invoke(template_app, ["mixins"])
        assert result.exit_code == 0
        assert "mcp-mem" in result.output
        assert "memory" in result.output
