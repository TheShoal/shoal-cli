"""Unit tests for branch naming helpers in shoal.core.git."""

from __future__ import annotations

import pytest

from shoal.core.git import ALLOWED_BRANCH_CATEGORIES, infer_branch_name, validate_branch_name


class TestInferBranchName:
    """Tests for infer_branch_name()."""

    def test_plain_slug_gets_feat_prefix(self) -> None:
        assert infer_branch_name("my-feature") == "feat/my-feature"

    def test_plain_slug_single_word(self) -> None:
        assert infer_branch_name("cleanup") == "feat/cleanup"

    def test_existing_feat_prefix_pass_through(self) -> None:
        assert infer_branch_name("feat/my-feature") == "feat/my-feature"

    def test_existing_fix_prefix_pass_through(self) -> None:
        assert infer_branch_name("fix/tmux-status") == "fix/tmux-status"

    def test_existing_chore_prefix_pass_through(self) -> None:
        assert infer_branch_name("chore/cleanup") == "chore/cleanup"

    def test_existing_refactor_prefix_pass_through(self) -> None:
        assert infer_branch_name("refactor/state-module") == "refactor/state-module"

    def test_no_double_feat_prefix(self) -> None:
        """The core bug: feat/name must not become feat/feat/name."""
        result = infer_branch_name("feat/add-logging")
        assert result == "feat/add-logging"
        assert "feat/feat/" not in result

    def test_no_double_fix_prefix(self) -> None:
        result = infer_branch_name("fix/send-keys-race")
        assert result == "fix/send-keys-race"
        assert "feat/fix/" not in result

    def test_no_double_prefix_for_all_categories(self) -> None:
        for cat in ALLOWED_BRANCH_CATEGORIES:
            worktree = f"{cat}/some-work"
            result = infer_branch_name(worktree)
            assert result == worktree, f"Expected pass-through for {worktree!r}, got {result!r}"


class TestValidateBranchName:
    """Tests for validate_branch_name()."""

    @pytest.mark.parametrize(
        "branch",
        [
            "feat/my-feature",
            "fix/tmux-status",
            "bug/race-condition",
            "chore/cleanup",
            "docs/update-readme",
            "refactor/state-module",
            "test/add-coverage",
            "feat/a1b2c3",
            "feat/x",
        ],
    )
    def test_valid_branches(self, branch: str) -> None:
        validate_branch_name(branch)  # should not raise

    @pytest.mark.parametrize(
        "branch",
        [
            "my-feature",  # missing category prefix
            "feat/",  # empty slug
            "FEAT/my-feature",  # uppercase category
            "feat/My-Feature",  # uppercase slug
            "feat/my_feature",  # underscore in slug
            "feat/my feature",  # space in slug
            "unknown/my-feature",  # invalid category
            "",  # empty string
            "feat/feat/nested",  # nested slash
        ],
    )
    def test_invalid_branches(self, branch: str) -> None:
        with pytest.raises(ValueError, match="category/slug"):
            validate_branch_name(branch)
