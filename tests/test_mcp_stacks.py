"""Unit tests for shoal.core.mcp_stacks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.config import ConfigLoadError
from shoal.core.mcp_stacks import McpStack, available_mcp_servers, load_mcp_stacks

_PATCH_BASE = "shoal.core.mcp_stacks"


class TestMcpStack:
    def test_all_fields(self) -> None:
        s = McpStack(
            name="dev",
            description="Dev tools",
            servers=["github", "memory"],
            source="config",
        )
        assert s.name == "dev"
        assert s.description == "Dev tools"
        assert s.servers == ["github", "memory"]
        assert s.source == "config"

    def test_defaults(self) -> None:
        s = McpStack(name="minimal", source="template")
        assert s.description == ""
        assert s.servers == []


class _FakeTemplate:
    """Minimal stand-in for a resolved template with an mcp attribute."""

    def __init__(self, mcp: list[str] | None = None) -> None:
        self.mcp = mcp or []


class TestLoadMcpStacks:
    def test_no_config_file(self, tmp_path: Path) -> None:
        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_stacks()
        assert result == {}

    def test_config_only(self, tmp_path: Path) -> None:
        toml = '[stacks.dev]\ndescription = "Dev essentials"\nservers = ["github", "memory"]\n'
        (tmp_path / "mcp-stacks.toml").write_text(toml)

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_stacks()

        assert "dev" in result
        s = result["dev"]
        assert s.source == "config"
        assert s.description == "Dev essentials"
        assert s.servers == ["github", "memory"]

    def test_template_only(self, tmp_path: Path) -> None:
        tpl = _FakeTemplate(mcp=["memory", "github"])

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=["test-tpl"]),
            patch(f"{_PATCH_BASE}.resolve_template", return_value=tpl),
        ):
            result = load_mcp_stacks()

        assert "test-tpl" in result
        s = result["test-tpl"]
        assert s.source == "template"
        assert s.servers == ["memory", "github"]
        assert "test-tpl" in s.description

    def test_config_overrides_template(self, tmp_path: Path) -> None:
        toml = '[stacks.dev]\ndescription = "From config"\nservers = ["fetch"]\n'
        (tmp_path / "mcp-stacks.toml").write_text(toml)

        tpl = _FakeTemplate(mcp=["memory"])

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=["dev"]),
            patch(f"{_PATCH_BASE}.resolve_template", return_value=tpl),
        ):
            result = load_mcp_stacks()

        assert result["dev"].source == "config"
        assert result["dev"].servers == ["fetch"]

    def test_broken_template_skipped(self, tmp_path: Path) -> None:
        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=["bad-tpl"]),
            patch(
                f"{_PATCH_BASE}.resolve_template",
                side_effect=RuntimeError("corrupted"),
            ),
        ):
            result = load_mcp_stacks()

        assert "bad-tpl" not in result
        assert result == {}

    def test_malformed_toml(self, tmp_path: Path) -> None:
        (tmp_path / "mcp-stacks.toml").write_text("not [valid toml ===")

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            with pytest.raises(ConfigLoadError):
                load_mcp_stacks()

    def test_stacks_sorted_by_name(self, tmp_path: Path) -> None:
        toml = '[stacks.z-stack]\nservers = ["a"]\n\n[stacks.a-stack]\nservers = ["b"]\n'
        (tmp_path / "mcp-stacks.toml").write_text(toml)

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_stacks()

        keys = list(result.keys())
        assert keys == ["a-stack", "z-stack"]


class TestAvailableMcpServers:
    def test_returns_sorted(self) -> None:
        registry = {"github": {}, "memory": {}, "fetch": {}}
        with patch(f"{_PATCH_BASE}.load_mcp_registry", return_value=registry):
            result = available_mcp_servers()
        assert result == ["fetch", "github", "memory"]
