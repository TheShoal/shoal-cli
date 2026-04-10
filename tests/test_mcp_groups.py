"""Unit tests for shoal.core.mcp_groups."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.config import ConfigLoadError
from shoal.core.mcp_groups import McpGroup, available_mcp_servers, load_mcp_groups

_PATCH_BASE = "shoal.core.mcp_groups"


class TestMcpGroup:
    def test_all_fields(self) -> None:
        g = McpGroup(
            name="dev",
            description="Dev tools",
            servers=["github", "memory"],
            source="config",
        )
        assert g.name == "dev"
        assert g.description == "Dev tools"
        assert g.servers == ["github", "memory"]
        assert g.source == "config"

    def test_defaults(self) -> None:
        g = McpGroup(name="minimal", source="template")
        assert g.description == ""
        assert g.servers == []


class _FakeTemplate:
    """Minimal stand-in for a resolved template with an mcp attribute."""

    def __init__(self, mcp: list[str] | None = None) -> None:
        self.mcp = mcp or []


class TestLoadMcpGroups:
    def test_no_config_file(self, tmp_path: Path) -> None:
        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_groups()
        assert result == {}

    def test_config_only(self, tmp_path: Path) -> None:
        toml = (
            '[groups.dev]\n'
            'description = "Dev essentials"\n'
            'servers = ["github", "memory"]\n'
        )
        (tmp_path / "mcp-groups.toml").write_text(toml)

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_groups()

        assert "dev" in result
        g = result["dev"]
        assert g.source == "config"
        assert g.description == "Dev essentials"
        assert g.servers == ["github", "memory"]

    def test_template_only(self, tmp_path: Path) -> None:
        tpl = _FakeTemplate(mcp=["memory", "github"])

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=["test-tpl"]),
            patch(f"{_PATCH_BASE}.resolve_template", return_value=tpl),
        ):
            result = load_mcp_groups()

        assert "test-tpl" in result
        g = result["test-tpl"]
        assert g.source == "template"
        assert g.servers == ["memory", "github"]
        assert "test-tpl" in g.description

    def test_config_overrides_template(self, tmp_path: Path) -> None:
        toml = (
            '[groups.dev]\n'
            'description = "From config"\n'
            'servers = ["fetch"]\n'
        )
        (tmp_path / "mcp-groups.toml").write_text(toml)

        tpl = _FakeTemplate(mcp=["memory"])

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=["dev"]),
            patch(f"{_PATCH_BASE}.resolve_template", return_value=tpl),
        ):
            result = load_mcp_groups()

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
            result = load_mcp_groups()

        assert "bad-tpl" not in result
        assert result == {}

    def test_malformed_toml(self, tmp_path: Path) -> None:
        (tmp_path / "mcp-groups.toml").write_text("not [valid toml ===")

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            with pytest.raises(ConfigLoadError):
                load_mcp_groups()

    def test_groups_sorted_by_name(self, tmp_path: Path) -> None:
        toml = (
            '[groups.z-group]\n'
            'servers = ["a"]\n'
            '\n'
            '[groups.a-group]\n'
            'servers = ["b"]\n'
        )
        (tmp_path / "mcp-groups.toml").write_text(toml)

        with (
            patch(f"{_PATCH_BASE}.config_dir", return_value=tmp_path),
            patch(f"{_PATCH_BASE}.available_templates", return_value=[]),
        ):
            result = load_mcp_groups()

        keys = list(result.keys())
        assert keys == ["a-group", "z-group"]


class TestAvailableMcpServers:
    def test_returns_sorted(self) -> None:
        registry = {"github": {}, "memory": {}, "fetch": {}}
        with patch(f"{_PATCH_BASE}.load_mcp_registry", return_value=registry):
            result = available_mcp_servers()
        assert result == ["fetch", "github", "memory"]
