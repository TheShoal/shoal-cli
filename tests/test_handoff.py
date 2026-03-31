"""Tests for handoff artifact generation and CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from shoal.core.journal import HandoffArtifact, JournalEntry, generate_handoff

# ---------------------------------------------------------------------------
# HandoffArtifact.to_dict
# ---------------------------------------------------------------------------


class TestHandoffArtifactToDict:
    def test_round_trip(self) -> None:
        entry = JournalEntry(
            timestamp=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
            source="cli",
            content="test content",
        )
        artifact = HandoffArtifact(
            session_name="test/feat",
            tool="pi",
            branch="feat/test",
            status="idle",
            urgency_label="idle",
            time_in_status="5m",
            last_active="2026-03-30 12:00 UTC",
            recent_entries=[entry],
            transition_summary=["12:00  running → idle"],
            suggested_next="Resume work.",
            worktree="/tmp/wt",
            git_diff_summary="2 files changed, 10 insertions(+)",
            commit_count=3,
        )
        d = artifact.to_dict()
        assert d["session_name"] == "test/feat"
        assert d["worktree"] == "/tmp/wt"
        assert d["git_diff_summary"] == "2 files changed, 10 insertions(+)"
        assert d["commit_count"] == 3
        assert len(d["recent_entries"]) == 1
        assert d["recent_entries"][0]["source"] == "cli"
        assert d["recent_entries"][0]["timestamp"].startswith("2026-03-30")

    def test_empty_fields(self) -> None:
        artifact = HandoffArtifact(
            session_name="s",
            tool="pi",
            branch="",
            status="unknown",
            urgency_label="unknown",
            time_in_status="-",
            last_active="-",
            recent_entries=[],
            transition_summary=[],
            suggested_next="Check.",
        )
        d = artifact.to_dict()
        assert d["worktree"] == ""
        assert d["git_diff_summary"] == ""
        assert d["commit_count"] == 0
        assert d["recent_entries"] == []


# ---------------------------------------------------------------------------
# HandoffArtifact.to_markdown with git context
# ---------------------------------------------------------------------------


class TestHandoffMarkdownGitContext:
    def test_includes_git_section(self) -> None:
        artifact = HandoffArtifact(
            session_name="s",
            tool="pi",
            branch="feat/x",
            status="idle",
            urgency_label="idle",
            time_in_status="2m",
            last_active="-",
            recent_entries=[],
            transition_summary=[],
            suggested_next="Resume.",
            worktree="/tmp/wt",
            git_diff_summary="3 files changed",
            commit_count=5,
        )
        md = artifact.to_markdown()
        assert "## Git context" in md
        assert "**Commits**: 5" in md
        assert "**Changes**: 3 files changed" in md

    def test_no_git_section_when_empty(self) -> None:
        artifact = HandoffArtifact(
            session_name="s",
            tool="pi",
            branch="",
            status="idle",
            urgency_label="idle",
            time_in_status="-",
            last_active="-",
            recent_entries=[],
            transition_summary=[],
            suggested_next="Resume.",
        )
        md = artifact.to_markdown()
        assert "## Git context" not in md

    def test_worktree_in_status(self) -> None:
        artifact = HandoffArtifact(
            session_name="s",
            tool="pi",
            branch="",
            status="idle",
            urgency_label="idle",
            time_in_status="-",
            last_active="-",
            recent_entries=[],
            transition_summary=[],
            suggested_next="Resume.",
            worktree="/tmp/wt",
        )
        md = artifact.to_markdown()
        assert "**Worktree**: `/tmp/wt`" in md


# ---------------------------------------------------------------------------
# generate_handoff with git context
# ---------------------------------------------------------------------------


class TestGenerateHandoffGitContext:
    def test_populates_git_fields_from_worktree(self) -> None:
        session = MagicMock()
        session.name = "test"
        session.tool = "pi"
        session.branch = "feat/x"
        session.worktree = "/tmp/wt"
        session.status = "idle"
        session.status_since = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        session.last_activity = datetime(2026, 3, 30, 12, 5, tzinfo=UTC)
        session.tags = []

        with (
            patch("shoal.core.git.diff_stat", return_value="2 files changed"),
            patch("shoal.core.git.commit_count_since_main", return_value=4),
        ):
            artifact = generate_handoff(session, [], [])

        assert artifact.worktree == "/tmp/wt"
        assert artifact.git_diff_summary == "2 files changed"
        assert artifact.commit_count == 4

    def test_graceful_fallback_on_git_error(self) -> None:
        session = MagicMock()
        session.name = "test"
        session.tool = "pi"
        session.branch = ""
        session.worktree = "/tmp/wt"
        session.status = "idle"
        session.status_since = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        session.last_activity = datetime(2026, 3, 30, 12, 5, tzinfo=UTC)
        session.tags = []

        with patch("shoal.core.git.diff_stat", side_effect=OSError("no git")):
            artifact = generate_handoff(session, [], [])

        assert artifact.git_diff_summary == ""
        assert artifact.commit_count == 0

    def test_no_git_when_no_worktree(self) -> None:
        session = MagicMock()
        session.name = "test"
        session.tool = "pi"
        session.branch = ""
        session.worktree = ""
        session.status = "idle"
        session.status_since = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        session.last_activity = datetime(2026, 3, 30, 12, 5, tzinfo=UTC)
        session.tags = []

        artifact = generate_handoff(session, [], [])
        assert artifact.worktree == ""
        assert artifact.git_diff_summary == ""
        assert artifact.commit_count == 0


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


class TestGitDiffStat:
    def test_returns_last_line(self) -> None:
        from shoal.core.git import diff_stat

        with patch("shoal.core.git._run") as mock:
            mock.return_value = MagicMock(
                returncode=0,
                stdout=" 2 files changed, 10 insertions(+), 3 deletions(-)\n",
            )
            result = diff_stat("/tmp/repo")
        assert result == "2 files changed, 10 insertions(+), 3 deletions(-)"

    def test_returns_empty_on_error(self) -> None:
        from shoal.core.git import diff_stat

        with patch("shoal.core.git._run") as mock:
            mock.return_value = MagicMock(returncode=128, stdout="")
            result = diff_stat("/tmp/repo")
        assert result == ""


class TestCommitCountSinceMain:
    def test_returns_count(self) -> None:
        from shoal.core.git import commit_count_since_main

        with (
            patch("shoal.core.git.main_branch", return_value="main"),
            patch("shoal.core.git._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0, stdout="7\n")
            result = commit_count_since_main("/tmp/repo")
        assert result == 7

    def test_returns_zero_on_error(self) -> None:
        from shoal.core.git import commit_count_since_main

        with (
            patch("shoal.core.git.main_branch", return_value="main"),
            patch("shoal.core.git._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=128, stdout="")
            result = commit_count_since_main("/tmp/repo")
        assert result == 0
