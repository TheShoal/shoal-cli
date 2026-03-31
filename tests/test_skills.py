"""Tests for cross-agent skill discovery and sync."""

from __future__ import annotations

from pathlib import Path

from shoal.core.config import discover_skills
from shoal.models.config import SkillConfig


class TestSkillConfig:
    def test_basic_fields(self) -> None:
        s = SkillConfig(name="test", description="A test skill", allowed_tools=["Read", "Bash"])
        assert s.name == "test"
        assert s.description == "A test skill"
        assert s.allowed_tools == ["Read", "Bash"]

    def test_extra_fields_ignored(self) -> None:
        s = SkillConfig(
            name="test",
            **{"disable-model-invocation": True},  # type: ignore[arg-type]
        )
        assert s.name == "test"


class TestDiscoverSkills:
    def test_discovers_from_project(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".shoal" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test skill\nallowed-tools: Read, Glob\n---\n\nBody\n"
        )
        skills = discover_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].description == "Test skill"
        assert skills[0].allowed_tools == ["Read", "Glob"]

    def test_discovers_from_dir_name_fallback(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".shoal" / "skills" / "auto-named"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\ndescription: No name field\n---\n\nBody\n")
        skills = discover_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0].name == "auto-named"

    def test_skips_missing_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".shoal" / "skills" / "bad"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("No frontmatter here\n")
        skills = discover_skills(str(tmp_path))
        assert len(skills) == 0

    def test_local_wins_over_global(self, tmp_path: Path, monkeypatch: object) -> None:
        # Local skill
        local_dir = tmp_path / "project" / ".shoal" / "skills" / "shared"
        local_dir.mkdir(parents=True)
        (local_dir / "SKILL.md").write_text(
            "---\nname: shared\ndescription: local version\n---\n\nLocal\n"
        )
        # Global skill with same name
        global_dir = tmp_path / "global" / "skills" / "shared"
        global_dir.mkdir(parents=True)
        (global_dir / "SKILL.md").write_text(
            "---\nname: shared\ndescription: global version\n---\n\nGlobal\n"
        )
        import shoal.core.config

        original = shoal.core.config.config_dir

        def mock_config_dir() -> Path:
            return tmp_path / "global"

        monkeypatch.setattr(shoal.core.config, "config_dir", mock_config_dir)  # type: ignore[arg-type]
        skills = discover_skills(str(tmp_path / "project"))
        assert len(skills) == 1
        assert skills[0].description == "local version"
        monkeypatch.setattr(shoal.core.config, "config_dir", original)  # type: ignore[arg-type]

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        skills = discover_skills(str(tmp_path))
        assert skills == []

    def test_none_git_root(self) -> None:
        skills = discover_skills(None)
        # Should not crash — just searches global
        assert isinstance(skills, list)


class TestSyncSkillsToWorktree:
    def test_symlinks_claude_skills(self, tmp_path: Path) -> None:
        from shoal.services.lifecycle import _sync_skills_to_worktree

        git_root = tmp_path / "repo"
        git_root.mkdir()
        skill_dir = git_root / ".shoal" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nBody\n")

        wt = tmp_path / "wt"
        wt.mkdir()

        _sync_skills_to_worktree(str(git_root), str(wt), "claude")

        link = wt / ".claude" / "skills" / "my-skill"
        assert link.is_symlink()
        assert (link / "SKILL.md").exists()

    def test_skips_non_claude_tools(self, tmp_path: Path) -> None:
        from shoal.services.lifecycle import _sync_skills_to_worktree

        git_root = tmp_path / "repo"
        skill_dir = git_root / ".shoal" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nBody\n")

        wt = tmp_path / "wt"
        wt.mkdir()

        _sync_skills_to_worktree(str(git_root), str(wt), "opencode")

        assert not (wt / ".claude" / "skills").exists()

    def test_no_skills_dir_is_noop(self, tmp_path: Path) -> None:
        from shoal.services.lifecycle import _sync_skills_to_worktree

        _sync_skills_to_worktree(str(tmp_path), str(tmp_path / "wt"), "claude")
        # Should not crash
