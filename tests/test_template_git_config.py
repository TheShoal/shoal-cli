"""Tests for [template.git] per-session git identity and commit conventions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from shoal.core.config import _apply_mixin, load_template
from shoal.models.config.templates import (
    SessionTemplateConfig,
    TemplateGitConfig,
    TemplateMixinConfig,
    TemplatePaneConfig,
    TemplateWindowConfig,
)

# -- helpers -----------------------------------------------------------------


def _write_template(templates_dir: Path, name: str, content: str) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / f"{name}.toml").write_text(content)


def _write_mixin(templates_dir: Path, name: str, content: str) -> None:
    mixins = templates_dir / "mixins"
    mixins.mkdir(parents=True, exist_ok=True)
    (mixins / f"{name}.toml").write_text(content)


def _minimal_template(name: str = "base") -> SessionTemplateConfig:
    return SessionTemplateConfig(
        name=name,
        windows=[
            TemplateWindowConfig(
                name="editor",
                panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
            )
        ],
    )


# -- TemplateGitConfig defaults ----------------------------------------------


class TestTemplateGitConfigDefaults:
    def test_all_fields_default_empty(self) -> None:
        cfg = TemplateGitConfig()
        assert cfg.user_name == ""
        assert cfg.user_email == ""
        assert cfg.commit_template == ""
        assert cfg.branch_prefix == ""
        assert cfg.pre_commit_config == ""

    def test_session_template_git_defaults_to_empty(self) -> None:
        t = _minimal_template()
        assert t.git == TemplateGitConfig()

    def test_rejects_unknown_fields(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TemplateGitConfig(bogus="x")  # type: ignore[call-arg]


# -- TOML parsing ------------------------------------------------------------


class TestTemplateGitTomlParsing:
    def test_parses_git_section(self, mock_dirs: tuple[Path, Path]) -> None:
        tmp_config, _ = mock_dirs
        _write_template(
            tmp_config / "templates",
            "with-git",
            """\
[template]
name = "with-git"

[template.git]
user_name  = "Robo"
user_email = "robo@shoal.local"
commit_template = "~/.gitmessage"
branch_prefix = "feat/"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
""",
        )
        t = load_template("with-git")
        assert t.git.user_name == "Robo"
        assert t.git.user_email == "robo@shoal.local"
        assert t.git.commit_template == "~/.gitmessage"
        assert t.git.branch_prefix == "feat/"

    def test_git_section_optional(self, mock_dirs: tuple[Path, Path]) -> None:
        """Templates without [template.git] still load and default to empty."""
        tmp_config, _ = mock_dirs
        _write_template(
            tmp_config / "templates",
            "no-git",
            """\
[template]
name = "no-git"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
""",
        )
        t = load_template("no-git")
        assert t.git == TemplateGitConfig()


# -- Inheritance (extends) ---------------------------------------------------


class TestGitInheritance:
    def test_child_inherits_parent_git_when_not_overriding(
        self, mock_dirs: tuple[Path, Path]
    ) -> None:
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "parent",
            """\
[template]
name = "parent"

[template.git]
user_name  = "Bot"
user_email = "bot@example.com"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
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
""",
        )
        t = load_template("child")
        assert t.git.user_name == "Bot"
        assert t.git.user_email == "bot@example.com"

    def test_child_overrides_parent_git(self, mock_dirs: tuple[Path, Path]) -> None:
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "parent2",
            """\
[template]
name = "parent2"

[template.git]
user_name  = "Bot"
user_email = "bot@example.com"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
""",
        )
        _write_template(
            templates,
            "child2",
            """\
[template]
name = "child2"
extends = "parent2"

[template.git]
user_name  = "OverrideBot"
user_email = "override@example.com"
""",
        )
        t = load_template("child2")
        assert t.git.user_name == "OverrideBot"
        assert t.git.user_email == "override@example.com"


# -- Mixin composition -------------------------------------------------------


class TestGitMixinComposition:
    def test_mixin_git_fields_win_on_non_empty(self) -> None:
        template = _minimal_template()
        assert template.git.user_name == ""

        mixin = TemplateMixinConfig(
            name="id",
            git=TemplateGitConfig(user_name="MixinBot", user_email="mixin@example.com"),
        )
        merged = _apply_mixin(template, mixin)
        assert merged.git.user_name == "MixinBot"
        assert merged.git.user_email == "mixin@example.com"

    def test_mixin_empty_git_field_does_not_clear_template_field(self) -> None:
        """Mixin with only user_email set should not blank user_name from template."""
        template = _minimal_template()
        template = template.model_copy(
            update={"git": TemplateGitConfig(user_name="TemplateBot", user_email="")}
        )
        mixin = TemplateMixinConfig(
            name="partial",
            git=TemplateGitConfig(user_name="", user_email="new@example.com"),
        )
        merged = _apply_mixin(template, mixin)
        assert merged.git.user_name == "TemplateBot"  # preserved from template
        assert merged.git.user_email == "new@example.com"  # taken from mixin

    def test_mixin_git_parsed_from_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        _write_template(
            templates,
            "base-mixin-git",
            """\
[template]
name = "base-mixin-git"
mixins = ["gitid"]

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
""",
        )
        _write_mixin(
            templates,
            "gitid",
            """\
[mixin]
name = "gitid"

[mixin.git]
user_name  = "MixinUser"
user_email = "mixinuser@example.com"
""",
        )
        t = load_template("base-mixin-git")
        assert t.git.user_name == "MixinUser"
        assert t.git.user_email == "mixinuser@example.com"


# -- Lifecycle application ---------------------------------------------------


class TestApplyTemplateGitConfigAsync:
    @pytest.mark.asyncio
    async def test_sends_git_config_commands(self) -> None:
        from shoal.services.lifecycle import _apply_template_git_config_async

        template = _minimal_template()
        template = template.model_copy(
            update={
                "git": TemplateGitConfig(
                    user_name="Robo",
                    user_email="robo@shoal.local",
                    commit_template="~/.gitmessage",
                )
            }
        )

        with patch("shoal.services.lifecycle.tmux") as mock_tmux:
            mock_tmux.async_first_pane = AsyncMock(return_value="shoal:sess.0")
            mock_tmux.async_send_keys = AsyncMock()
            await _apply_template_git_config_async(template, "shoal:sess", "/tmp/work")

        calls = [str(c) for c in mock_tmux.async_send_keys.call_args_list]
        assert any("user.name" in c and "Robo" in c for c in calls)
        assert any("user.email" in c and "robo@shoal.local" in c for c in calls)
        assert any("commit.template" in c and ".gitmessage" in c for c in calls)
        assert any("GIT_AUTHOR_NAME" in c and "Robo" in c for c in calls)
        assert any("GIT_AUTHOR_EMAIL" in c and "robo@shoal.local" in c for c in calls)

    @pytest.mark.asyncio
    async def test_no_keys_sent_when_git_section_empty(self) -> None:
        from shoal.services.lifecycle import _apply_template_git_config_async

        template = _minimal_template()  # git defaults to all-empty

        with patch("shoal.services.lifecycle.tmux") as mock_tmux:
            mock_tmux.async_first_pane = AsyncMock(return_value="shoal:sess.0")
            mock_tmux.async_send_keys = AsyncMock()
            await _apply_template_git_config_async(template, "shoal:sess", "/tmp/work")

        mock_tmux.async_send_keys.assert_not_called()

    @pytest.mark.asyncio
    async def test_branch_prefix_does_not_emit_git_config(self) -> None:
        """branch_prefix is a convention hint only — no git config call emitted."""
        from shoal.services.lifecycle import _apply_template_git_config_async

        template = _minimal_template()
        template = template.model_copy(update={"git": TemplateGitConfig(branch_prefix="fix/")})

        with patch("shoal.services.lifecycle.tmux") as mock_tmux:
            mock_tmux.async_first_pane = AsyncMock(return_value="shoal:sess.0")
            mock_tmux.async_send_keys = AsyncMock()
            await _apply_template_git_config_async(template, "shoal:sess", "/tmp/work")

        # branch_prefix alone should not trigger any git config calls
        mock_tmux.async_send_keys.assert_not_called()


# -- _symlink_pre_commit_config ---------------------------------------------


class TestSymlinkPreCommitConfig:
    @pytest.mark.asyncio
    async def test_creates_symlink_when_source_exists(self, tmp_path: Path) -> None:
        """Symlink is created at <work_dir>/.pre-commit-config.yaml pointing at src."""
        from shoal.services.lifecycle import _symlink_pre_commit_config

        src = tmp_path / "shared-pre-commit.yaml"
        src.write_text("repos: []\n")
        work_dir = tmp_path / "worktree"
        work_dir.mkdir()

        await _symlink_pre_commit_config(str(src), str(work_dir))

        dest = work_dir / ".pre-commit-config.yaml"
        assert dest.is_symlink()
        assert dest.resolve() == src.resolve()

    @pytest.mark.asyncio
    async def test_noop_when_source_missing(self, tmp_path: Path) -> None:
        """No error and no symlink if the source path does not exist."""
        from shoal.services.lifecycle import _symlink_pre_commit_config

        work_dir = tmp_path / "worktree"
        work_dir.mkdir()

        await _symlink_pre_commit_config(str(tmp_path / "nonexistent.yaml"), str(work_dir))

        assert not (work_dir / ".pre-commit-config.yaml").exists()

    @pytest.mark.asyncio
    async def test_replaces_existing_symlink(self, tmp_path: Path) -> None:
        """An existing symlink at the destination is replaced (idempotent)."""
        from shoal.services.lifecycle import _symlink_pre_commit_config

        src1 = tmp_path / "config-v1.yaml"
        src1.write_text("repos: []\n")
        src2 = tmp_path / "config-v2.yaml"
        src2.write_text("repos: [x]\n")
        work_dir = tmp_path / "worktree"
        work_dir.mkdir()
        dest = work_dir / ".pre-commit-config.yaml"

        # First call
        await _symlink_pre_commit_config(str(src1), str(work_dir))
        assert dest.resolve() == src1.resolve()

        # Second call — replaces
        await _symlink_pre_commit_config(str(src2), str(work_dir))
        assert dest.resolve() == src2.resolve()

    @pytest.mark.asyncio
    async def test_expands_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """~ in the source path is expanded before stat."""
        from shoal.services.lifecycle import _symlink_pre_commit_config

        # Redirect ~ to tmp_path so test is hermetic
        monkeypatch.setenv("HOME", str(tmp_path))
        src = tmp_path / "pc.yaml"
        src.write_text("repos: []\n")
        work_dir = tmp_path / "worktree"
        work_dir.mkdir()

        await _symlink_pre_commit_config("~/pc.yaml", str(work_dir))

        dest = work_dir / ".pre-commit-config.yaml"
        assert dest.is_symlink()


# -- pre_commit_config field + lifecycle integration -------------------------


class TestPreCommitConfigField:
    def test_defaults_empty(self) -> None:
        assert TemplateGitConfig().pre_commit_config == ""

    def test_toml_parsing(self, mock_dirs: tuple[Path, Path]) -> None:
        tmp_config, _ = mock_dirs
        _write_template(
            tmp_config / "templates",
            "with-pc",
            """\
[template]
name = "with-pc"

[template.git]
user_name = "Bot"
pre_commit_config = "/shared/hooks.yaml"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "{tool_command}"
""",
        )
        t = load_template("with-pc")
        assert t.git.pre_commit_config == "/shared/hooks.yaml"

    @pytest.mark.asyncio
    async def test_pre_commit_config_only_does_not_call_send_keys(self, tmp_path: Path) -> None:
        """pre_commit_config alone must not emit any tmux send_keys calls."""
        from shoal.services.lifecycle import _apply_template_git_config_async

        src = tmp_path / "pc.yaml"
        src.write_text("repos: []\n")
        work_dir = tmp_path / "worktree"
        work_dir.mkdir()

        template = _minimal_template()
        template = template.model_copy(
            update={"git": TemplateGitConfig(pre_commit_config=str(src))}
        )

        with patch("shoal.services.lifecycle.tmux") as mock_tmux:
            mock_tmux.async_first_pane = AsyncMock(return_value="shoal:sess.0")
            mock_tmux.async_send_keys = AsyncMock()
            await _apply_template_git_config_async(template, "shoal:sess", str(work_dir))

        mock_tmux.async_send_keys.assert_not_called()
        assert (work_dir / ".pre-commit-config.yaml").is_symlink()
