#!/usr/bin/env python3
"""Pre-commit hook: reject raw backticks inside HTML elements in Markdown files.

Backtick characters inside HTML tags render as literal text in the browser,
not as styled inline code.  Use <code>…</code> instead.

Exit 1 with per-file diagnostics when violations are found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Only match opening tags that look like real HTML — a known set of block/inline
# elements.  This avoids treating `<name>` or `<session>` placeholders inside
# markdown table cells or code spans as HTML tags.
_KNOWN_HTML_TAGS = frozenset(
    [
        "div",
        "p",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "main",
        "nav",
        "span",
        "strong",
        "em",
        "b",
        "i",
        "a",
        "ul",
        "ol",
        "li",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "blockquote",
        "pre",
        "code",
        "details",
        "summary",
        "figure",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    ]
)

_OPEN_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)[^>]*>")
_CLOSE_TAG = re.compile(r"</([a-zA-Z][a-zA-Z0-9]*)>")
_BACKTICK_SPAN = re.compile(r"`[^`\n]*`")


def _strip_backtick_spans(line: str) -> str:
    """Remove inline code spans so their contents don't influence HTML parsing."""
    return _BACKTICK_SPAN.sub("``", line)


def _count_html_tags(line: str) -> tuple[int, int]:
    """Return (opens, closes) counting only known HTML element names."""
    clean = _strip_backtick_spans(line)
    opens = sum(1 for m in _OPEN_TAG.finditer(clean) if m.group(1).lower() in _KNOWN_HTML_TAGS)
    closes = sum(1 for m in _CLOSE_TAG.finditer(clean) if m.group(1).lower() in _KNOWN_HTML_TAGS)
    return opens, closes


def _has_html_tag(line: str) -> bool:
    clean = _strip_backtick_spans(line)
    return bool(
        any(m.group(1).lower() in _KNOWN_HTML_TAGS for m in _OPEN_TAG.finditer(clean))
        or any(m.group(1).lower() in _KNOWN_HTML_TAGS for m in _CLOSE_TAG.finditer(clean))
    )


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, line_content) violations."""
    violations: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    in_fenced = False
    html_depth = 0  # nesting depth of block-level HTML tags

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track fenced code blocks — never lint inside them.
        if stripped.startswith(("```", "~~~")):
            in_fenced = not in_fenced
        if in_fenced:
            continue

        # Markdown table rows (| col | col |) are not HTML; skip for depth tracking.
        if stripped.startswith("|"):
            continue

        # Update HTML nesting depth using only real HTML tag names.
        opens, closes = _count_html_tags(line)
        html_depth += opens - closes
        html_depth = max(html_depth, 0)

        # Violation: a backtick that appears on a line with a real HTML tag,
        # or on a line nested inside an HTML block (html_depth > 0 before this line).
        has_tag = _has_html_tag(line)
        has_backtick = "`" in line
        if has_backtick and (has_tag or html_depth > 0):
            violations.append((lineno, line))

    return violations


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] if argv else list(Path("docs").rglob("*.md"))
    found = False
    for path in files:
        if path.suffix != ".md":
            continue
        violations = check_file(path)
        if violations:
            found = True
            for lineno, content in violations:
                print(f"{path}:{lineno}: raw backtick inside HTML — use <code>…</code>")
                print(f"  {content.rstrip()}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
