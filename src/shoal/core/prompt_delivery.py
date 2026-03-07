"""Tool-native prompt delivery for initial session prompts.

Replaces the fragile ``send_keys`` post-launch approach with each tool's
native input mechanism so the prompt is guaranteed to reach the agent
before the TUI finishes rendering.

Three delivery modes (``ToolConfig.input_mode``):

* ``"keys"``  — legacy: ``send_keys`` after launch (default, unchanged).
* ``"arg"``   — bake the prompt as a positional CLI argument.
              If ``prompt_file_prefix`` is set (e.g. ``"@"`` for omp),
              the prompt is written to a file and the file path is passed
              with the prefix prepended.
* ``"flag"``  — bake the prompt via a named flag (e.g. ``--prompt``).

Prompt files are written to ``state_dir()/prompts/<session_id>.md`` and
kept on disk as an audit trail — they are never deleted.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from shoal.models.config import ToolConfig


def _prompts_dir() -> Path:
    """Return (and create) the directory used for persisted prompt files."""
    from shoal.core.config import state_dir

    d = state_dir() / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_prompt_file(session_id: str, prompt: str) -> Path:
    """Write *prompt* to ``<state_dir>/prompts/<session_id>.md`` and return the path.

    The file is created with mode 0o600 (owner-readable only).
    If a file for *session_id* already exists it is overwritten so that
    re-runs of the same session get a fresh prompt.

    Args:
        session_id: Unique session identifier used as the file stem.
        prompt: Prompt text to persist.

    Returns:
        Absolute path to the written prompt file.
    """
    path = _prompts_dir() / f"{session_id}.md"
    path.write_text(prompt, encoding="utf-8")
    path.chmod(0o600)
    return path


def build_tool_command_with_prompt(
    tool_cfg: ToolConfig,
    prompt: str,
    session_id: str,
) -> str:
    """Return the tool launch command with *prompt* baked in natively.

    The returned string is a complete shell command ready to pass as
    ``tool_command`` to ``create_session_lifecycle``.

    For ``input_mode = "keys"`` the base command is returned unchanged —
    the caller is responsible for the post-launch ``send_keys`` flow.

    Args:
        tool_cfg: Resolved tool configuration for the session.
        prompt: Initial prompt text to deliver.
        session_id: Session ID used to name the prompt file (``"arg"`` +
            file mode only).

    Returns:
        Shell command string with the prompt embedded.
    """
    base = tool_cfg.command

    if tool_cfg.input_mode == "flag":
        flag = tool_cfg.prompt_flag or "--prompt"
        return f"{base} {flag} {shlex.quote(prompt)}"

    if tool_cfg.input_mode == "arg":
        if tool_cfg.prompt_file_prefix:
            prompt_path = write_prompt_file(session_id, prompt)
            return f"{base} {tool_cfg.prompt_file_prefix}{prompt_path}"
        return f"{base} {shlex.quote(prompt)}"

    # "keys" or unknown — return base command unmodified
    return base
