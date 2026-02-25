"""Tests for Phase 3 — Session Graph (parent_id, tags, template_name)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.journal import (
    JournalSearchResult,
    append_entry,
    search_journals,
)
from shoal.core.state import (
    add_tag,
    create_session,
    get_session,
    remove_tag,
)
from shoal.models.state import SessionState


@pytest.mark.asyncio
class TestParentId:
    """Fork records parent_id; empty for non-forks."""

    async def test_create_session_no_parent(self, mock_dirs: object) -> None:
        s = await create_session("root-session", "claude", "/tmp/repo")
        assert s.parent_id == ""

    async def test_create_session_with_parent(self, mock_dirs: object) -> None:
        parent = await create_session("parent", "claude", "/tmp/repo")
        child = await create_session("child", "claude", "/tmp/repo", parent_id=parent.id)
        assert child.parent_id == parent.id

    async def test_parent_id_persists_in_db(self, mock_dirs: object) -> None:
        parent = await create_session("parent-persist", "claude", "/tmp/repo")
        child = await create_session("child-persist", "claude", "/tmp/repo", parent_id=parent.id)
        reloaded = await get_session(child.id)
        assert reloaded is not None
        assert reloaded.parent_id == parent.id

    async def test_fork_lifecycle_records_parent(self, mock_dirs: object) -> None:
        from shoal.services.lifecycle import fork_session_lifecycle

        parent = await create_session("fork-parent", "claude", "/tmp/repo")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
        ):
            child = await fork_session_lifecycle(
                session_name="fork-child",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="",
                work_dir="/tmp/repo",
                new_branch="feat/fork-child",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} {tool_command} Enter"],
                parent_id=parent.id,
            )
        assert child.parent_id == parent.id


@pytest.mark.asyncio
class TestTags:
    """Tag add/remove/duplicate handling."""

    async def test_add_tag(self, mock_dirs: object) -> None:
        s = await create_session("tag-test", "claude", "/tmp/repo")
        await add_tag(s.id, "important")
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert "important" in reloaded.tags

    async def test_add_duplicate_tag(self, mock_dirs: object) -> None:
        s = await create_session("tag-dup", "claude", "/tmp/repo")
        await add_tag(s.id, "dupe")
        await add_tag(s.id, "dupe")
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert reloaded.tags.count("dupe") == 1

    async def test_remove_tag(self, mock_dirs: object) -> None:
        s = await create_session("tag-rm", "claude", "/tmp/repo")
        await add_tag(s.id, "removeme")
        await remove_tag(s.id, "removeme")
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert "removeme" not in reloaded.tags

    async def test_remove_nonexistent_tag(self, mock_dirs: object) -> None:
        s = await create_session("tag-noexist", "claude", "/tmp/repo")
        await remove_tag(s.id, "ghost")  # Should not raise
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert reloaded.tags == []

    async def test_multiple_tags(self, mock_dirs: object) -> None:
        s = await create_session("tag-multi", "claude", "/tmp/repo")
        await add_tag(s.id, "alpha")
        await add_tag(s.id, "beta")
        await add_tag(s.id, "gamma")
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert set(reloaded.tags) == {"alpha", "beta", "gamma"}

    async def test_create_with_tags(self, mock_dirs: object) -> None:
        s = await create_session("tag-init", "claude", "/tmp/repo", tags=["a", "b"])
        assert s.tags == ["a", "b"]
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert reloaded.tags == ["a", "b"]

    async def test_add_tag_nonexistent_session(self, mock_dirs: object) -> None:
        await add_tag("nonexistent", "tag")  # Should not raise

    async def test_remove_tag_nonexistent_session(self, mock_dirs: object) -> None:
        await remove_tag("nonexistent", "tag")  # Should not raise


@pytest.mark.asyncio
class TestTemplateName:
    """Create with template stores template_name."""

    async def test_create_with_template_name(self, mock_dirs: object) -> None:
        s = await create_session("tmpl-test", "claude", "/tmp/repo", template_name="base-dev")
        assert s.template_name == "base-dev"

    async def test_template_name_persists(self, mock_dirs: object) -> None:
        s = await create_session("tmpl-persist", "claude", "/tmp/repo", template_name="claude-dev")
        reloaded = await get_session(s.id)
        assert reloaded is not None
        assert reloaded.template_name == "claude-dev"

    async def test_create_without_template_name(self, mock_dirs: object) -> None:
        s = await create_session("no-tmpl", "claude", "/tmp/repo")
        assert s.template_name == ""

    async def test_lifecycle_records_template_name(self, mock_dirs: object) -> None:
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import create_session_lifecycle

        template = SessionTemplateConfig(
            name="test-template",
            tool="claude",
            windows=[
                TemplateWindowConfig(name="main", panes=[TemplatePaneConfig(command="echo hi")])
            ],
        )

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
            patch("shoal.core.tmux.send_keys"),
        ):
            session = await create_session_lifecycle(
                session_name="tmpl-lifecycle",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
                template_cfg=template,
            )
        assert session.template_name == "test-template"


@pytest.mark.asyncio
class TestLsFiltering:
    """--tag filters sessions correctly."""

    async def test_filter_by_tag(self, mock_dirs: object) -> None:
        await create_session("tagged-one", "claude", "/tmp/repo", tags=["web"])
        await create_session("tagged-two", "claude", "/tmp/repo", tags=["api"])
        await create_session("tagged-both", "claude", "/tmp/repo", tags=["web", "api"])

        from shoal.core.state import list_sessions

        all_sessions = await list_sessions()
        filtered = [s for s in all_sessions if "web" in s.tags]
        names = {s.name for s in filtered}
        assert "tagged-one" in names
        assert "tagged-both" in names
        assert "tagged-two" not in names


class TestLsTree:
    """Tree rendering of fork relationships."""

    def test_render_fork_tree(self) -> None:
        """Test that _render_fork_tree doesn't crash with parent-child data."""
        from io import StringIO

        from rich.console import Console

        from shoal.cli.session_view import _render_fork_tree

        parent = SessionState(
            id="parent01",
            name="root-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="root-session",
        )
        child = SessionState(
            id="child001",
            name="child-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="child-session",
            parent_id="parent01",
            tags=["feature"],
        )
        orphan = SessionState(
            id="orphan01",
            name="orphan-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="orphan-session",
        )

        output = StringIO()
        test_console = Console(file=output, width=120)

        with patch("shoal.cli.session_view.console", test_console):
            _render_fork_tree([parent, child, orphan])

        rendered = output.getvalue()
        assert "root-session" in rendered
        assert "child-session" in rendered
        assert "orphan-session" in rendered
        assert "feature" in rendered  # tag displayed

    def test_tree_with_no_forks(self) -> None:
        """All sessions are roots when no parent_id set."""
        from io import StringIO

        from rich.console import Console

        from shoal.cli.session_view import _render_fork_tree

        s1 = SessionState(id="a1", name="alpha", tool="claude", path="/tmp", tmux_session="alpha")
        s2 = SessionState(id="b1", name="beta", tool="claude", path="/tmp", tmux_session="beta")

        output = StringIO()
        test_console = Console(file=output, width=120)

        with patch("shoal.cli.session_view.console", test_console):
            _render_fork_tree([s1, s2])

        rendered = output.getvalue()
        assert "alpha" in rendered
        assert "beta" in rendered
        # No tree connectors since all are roots
        assert "└──" not in rendered


class TestJournalSearch:
    """Search across journals."""

    @pytest.fixture(autouse=True)
    def _journal_dir(self, tmp_path: Path) -> Generator[Path, None, None]:
        """Isolate journal writes to a fresh temp directory."""
        journal_dir = tmp_path / "journals"
        journal_dir.mkdir()
        with patch("shoal.core.journal._journals_dir", return_value=journal_dir):
            yield journal_dir

    def test_search_finds_matching_entry(self) -> None:
        append_entry("search-auth-1", "Fixed the authentication bug", source="test")
        append_entry("search-auth-2", "Updated the README docs", source="test")

        results = search_journals("authentication")
        assert len(results) == 1
        assert results[0].session_id == "search-auth-1"
        assert "authentication" in results[0].entry.content

    def test_search_case_insensitive(self) -> None:
        append_entry("search-ci", "Added new Feature for Login", source="test")

        results = search_journals("feature")
        assert len(results) == 1
        assert results[0].session_id == "search-ci"

    def test_search_no_results(self) -> None:
        results = search_journals("xyzzy-nonexistent-12345")
        assert len(results) == 0

    def test_search_respects_limit(self) -> None:
        for i in range(5):
            append_entry(f"search-lim-{i}", f"Match keyword entry {i}", source="test")

        results = search_journals("keyword", limit=3)
        assert len(results) == 3

    def test_search_result_type(self) -> None:
        append_entry("search-type", "Type check content", source="test")

        results = search_journals("Type check")
        assert len(results) == 1
        assert isinstance(results[0], JournalSearchResult)
        assert results[0].session_id == "search-type"
