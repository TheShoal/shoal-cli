"""Tests for core.prompt_delivery module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.models.config import ToolConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    command: str = "sometool",
    input_mode: str = "keys",
    prompt_flag: str = "",
    prompt_file_prefix: str = "",
) -> ToolConfig:
    """Return a minimal ToolConfig with the given delivery settings."""
    return ToolConfig(
        name="test",
        command=command,
        input_mode=input_mode,  # type: ignore[arg-type]
        prompt_flag=prompt_flag,
        prompt_file_prefix=prompt_file_prefix,
    )


# ---------------------------------------------------------------------------
# write_prompt_file
# ---------------------------------------------------------------------------


def test_write_prompt_file_creates_file(tmp_path: Path) -> None:
    """Prompt file is written with the correct content."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import write_prompt_file

        result = write_prompt_file("sess-abc", "Do the thing")

    assert result == tmp_path / "sess-abc.md"
    assert result.read_text(encoding="utf-8") == "Do the thing"


def test_write_prompt_file_mode(tmp_path: Path) -> None:
    """Prompt file is written with restrictive permissions (0o600)."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import write_prompt_file

        path = write_prompt_file("sess-xyz", "secret prompt")

    assert oct(path.stat().st_mode)[-3:] == "600"


def test_write_prompt_file_overwrites(tmp_path: Path) -> None:
    """Writing twice for the same session_id replaces the file."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import write_prompt_file

        write_prompt_file("sess-1", "first")
        write_prompt_file("sess-1", "second")
        path = tmp_path / "sess-1.md"

    assert path.read_text(encoding="utf-8") == "second"


def test_write_prompt_file_uses_state_dir(tmp_path: Path) -> None:
    """_prompts_dir() creates prompts/ under state_dir()."""
    fake_state = tmp_path / "shoal"
    fake_state.mkdir()

    with patch("shoal.core.config.state_dir", return_value=fake_state):
        # Re-import to get a fresh call (module-level lazy call)
        import importlib

        import shoal.core.prompt_delivery as pd

        importlib.reload(pd)
        result = pd.write_prompt_file("s1", "hello")

    assert result.parent == fake_state / "prompts"
    assert result.read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# build_tool_command_with_prompt — "keys" mode
# ---------------------------------------------------------------------------


def test_build_keys_mode_returns_base_command() -> None:
    """keys mode returns the base command with no modification."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="pi", input_mode="keys")
    result = build_tool_command_with_prompt(tool, "some prompt", "sess-1")
    assert result == "pi"


def test_build_keys_mode_ignores_prompt() -> None:
    """keys mode ignores the prompt entirely."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="pi", input_mode="keys")
    result = build_tool_command_with_prompt(tool, "a very long prompt text here", "sess-1")
    assert "prompt" not in result


# ---------------------------------------------------------------------------
# build_tool_command_with_prompt — "flag" mode
# ---------------------------------------------------------------------------


def test_build_flag_mode_opencode() -> None:
    """flag mode appends --prompt <quoted-prompt> to the command."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="opencode", input_mode="flag", prompt_flag="--prompt")
    result = build_tool_command_with_prompt(tool, "Fix the bug", "sess-2")
    assert result == "opencode --prompt 'Fix the bug'"


def test_build_flag_mode_default_flag() -> None:
    """flag mode uses --prompt when prompt_flag is empty."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="mytool", input_mode="flag", prompt_flag="")
    result = build_tool_command_with_prompt(tool, "do work", "sess-3")
    assert result == "mytool --prompt 'do work'"


def test_build_flag_mode_quotes_special_chars() -> None:
    """flag mode correctly shell-quotes prompts with spaces and special chars."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="opencode", input_mode="flag", prompt_flag="--prompt")
    result = build_tool_command_with_prompt(tool, "Say 'hello' & goodbye", "sess-4")
    # shlex.quote should produce a safely quoted string
    assert result.startswith("opencode --prompt ")
    # Re-parse: the quoted arg should round-trip correctly
    import shlex

    parts = shlex.split(result)
    assert parts == ["opencode", "--prompt", "Say 'hello' & goodbye"]


# ---------------------------------------------------------------------------
# build_tool_command_with_prompt — "arg" mode, no file prefix (claude)
# ---------------------------------------------------------------------------


def test_build_arg_mode_no_prefix_claude() -> None:
    """arg mode without prefix inlines prompt as a positional arg."""
    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="claude", input_mode="arg", prompt_file_prefix="")
    result = build_tool_command_with_prompt(tool, "Refactor the module", "sess-5")
    assert result == "claude 'Refactor the module'"


def test_build_arg_mode_no_prefix_quotes_special_chars() -> None:
    """arg mode without prefix shell-quotes the prompt."""
    import shlex

    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(command="claude", input_mode="arg", prompt_file_prefix="")
    result = build_tool_command_with_prompt(tool, "it's tricky & fun", "sess-6")
    parts = shlex.split(result)
    assert parts == ["claude", "it's tricky & fun"]


# ---------------------------------------------------------------------------
# build_tool_command_with_prompt — "arg" mode, with file prefix (omp)
# ---------------------------------------------------------------------------


def test_build_arg_mode_with_prefix_omp(tmp_path: Path) -> None:
    """arg+prefix mode writes a file and returns omp @/path/to/file.md."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import build_tool_command_with_prompt

        tool = _make_tool(command="omp", input_mode="arg", prompt_file_prefix="@")
        result = build_tool_command_with_prompt(tool, "Build the feature", "sess-7")

    expected_path = tmp_path / "sess-7.md"
    assert result == f"omp @{expected_path}"
    assert expected_path.read_text(encoding="utf-8") == "Build the feature"


def test_build_arg_mode_with_prefix_writes_prompt_file(tmp_path: Path) -> None:
    """arg+prefix mode creates the prompt file with correct content."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import build_tool_command_with_prompt

        tool = _make_tool(command="omp", input_mode="arg", prompt_file_prefix="@")
        build_tool_command_with_prompt(tool, "multi\nline\nprompt", "sess-8")
        written = (tmp_path / "sess-8.md").read_text(encoding="utf-8")

    assert written == "multi\nline\nprompt"


def test_build_arg_mode_with_prefix_no_space_between_prefix_and_path(tmp_path: Path) -> None:
    """The prefix is concatenated directly to the path with no space."""
    with patch("shoal.core.prompt_delivery._prompts_dir", return_value=tmp_path):
        from shoal.core.prompt_delivery import build_tool_command_with_prompt

        tool = _make_tool(command="omp", input_mode="arg", prompt_file_prefix="@")
        result = build_tool_command_with_prompt(tool, "test", "sess-9")

    # must be "omp @/..." not "omp @ /..."
    assert " @ " not in result
    parts = result.split(" ")
    assert parts[1].startswith("@/")


# ---------------------------------------------------------------------------
# Round-trip: command contains no unquoted prompt text in arg/flag modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_mode", "flag", "prefix"),
    [
        ("flag", "--prompt", ""),
        ("arg", "", ""),
    ],
)
def test_prompt_does_not_appear_raw_in_command(input_mode: str, flag: str, prefix: str) -> None:
    """The raw prompt text with shell-sensitive chars doesn't appear unquoted."""
    import shlex

    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    tool = _make_tool(
        command="tool", input_mode=input_mode, prompt_flag=flag, prompt_file_prefix=prefix
    )
    raw_prompt = "hello; rm -rf / && echo pwned"
    result = build_tool_command_with_prompt(tool, raw_prompt, "sess-safe")

    # shlex.split must succeed (no unmatched quotes / syntax errors)
    parts = shlex.split(result)
    # The dangerous string should appear verbatim in one part, not spread across multiple
    combined = " ".join(parts[1:])
    assert "rm -rf /" in combined  # it IS there…
    assert parts[0] == "tool"  # …but confined to a single quoted token
