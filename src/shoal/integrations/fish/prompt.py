# SPDX-FileCopyrightText: 2024 The SHOAL Authors
# SPDX-License-Identifier: Apache-2.0

"""Fish shell prompt escaping utilities.

Fish shell interprets certain characters as special syntax:

- ? - command substitution indicator
- && - command chain
- () - command substitution
- $ - variable expansion
- \\ - escape character
- ' and " - quoting

When sending prompts via tmux send-keys to a fish shell, these must be
escaped to be treated as literal text.
"""

from __future__ import annotations


def escape_for_fish(text: str) -> str:
    """Escape a prompt string for safe use in fish shell.

    This escapes special characters so the text is treated as a literal
    string when sent via tmux send-keys to a fish shell pane.

    Args:
        text: The raw prompt text to escape.

    Returns:
        The escaped string safe for fish shell interpretation.
    """
    if not text:
        return text

    # Characters that fish shell interprets as special in command position
    # or that could cause parsing issues
    special_chars = ["?", "&", "$", "(", ")", "\\", '"', "'", ";", "|", "<", ">"]

    escaped = text
    for char in special_chars:
        # Escape each special character with backslash
        escaped = escaped.replace(char, "\\" + char)

    return escaped


def escape_for_fish_heredoc(text: str) -> str:
    """Escape a prompt string for fish shell heredoc syntax.

    Use this when passing prompts via a heredoc to avoid any shell
    interpretation issues.

    Args:
        text: The raw prompt text to escape.

    Returns:
        The text escaped for fish shell heredoc.
    """
    # For heredocs, we only need to escape the delimiter if it appears
    # in the text. Since prompts are typically single-use, we use a
    # unique delimiter based on null bytes or UUID-like pattern.
    if not text:
        return text

    # Replace any null bytes which can't be in heredocs
    escaped = text.replace("\x00", "")

    # Escape backslashes first (but not the delimiter we'll use)
    escaped = escaped.replace("\\", "\\\\")

    # Escape the delimiter pattern we'll use (EOFPROMPT)
    escaped = escaped.replace("EOFPROMPT", "EOFPROMPT")

    return escaped


# Characters that fish interprets as having special meaning
FISH_SPECIAL_CHARS = frozenset("?&$()\\\"';|<>")


def contains_fish_special_chars(text: str) -> bool:
    """Check if text contains fish shell special characters.

    Args:
        text: The text to check.

    Returns:
        True if the text contains fish special characters.
    """
    return any(char in FISH_SPECIAL_CHARS for char in text)
