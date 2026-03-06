"""Generate docs-site pages from canonical root-level project documents."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import mkdocs_gen_files

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_BLOB_BASE = "https://github.com/TheShoal/shoal-cli/blob/main"

ROOT_DOCS: dict[str, str] = {
    "ARCHITECTURE.md": "project/architecture-guide.md",
    "CHANGELOG.md": "project/changelog.md",
    "COMMIT_GUIDELINES.md": "project/commit-guidelines.md",
    "CONTRIBUTING.md": "project/contributing.md",
    "RELEASE_PROCESS.md": "project/release-process.md",
    "ROADMAP.md": "project/roadmap.md",
    "SECURITY.md": "project/security.md",
}

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _relative_link(source: str, target: str) -> str:
    """Build a stable relative link between two docs paths."""
    return posixpath.relpath(target, posixpath.dirname(source))


def _rewrite_target(target: str, output_path: str) -> str:
    """Rewrite root-doc links so they work inside the docs site."""
    if "://" in target or target.startswith(("mailto:", "#")):
        return target

    path, anchor = target.split("#", 1) if "#" in target else (target, "")
    suffix = f"#{anchor}" if anchor else ""

    if path in ROOT_DOCS:
        return f"{_relative_link(output_path, ROOT_DOCS[path])}{suffix}"

    if path.startswith("docs/"):
        docs_target = path.removeprefix("docs/")
        return f"{_relative_link(output_path, docs_target)}{suffix}"

    candidate = REPO_ROOT / path
    if candidate.exists():
        return f"{REPO_BLOB_BASE}/{path}{suffix}"

    return f"{REPO_BLOB_BASE}/{path}{suffix}"


def _rewrite_links(text: str, output_path: str) -> str:
    """Rewrite markdown links for generated docs-site pages."""

    def replace(match: re.Match[str]) -> str:
        label, target = match.groups()
        return f"[{label}]({_rewrite_target(target, output_path)})"

    return LINK_RE.sub(replace, text)


for root_name, output_path in ROOT_DOCS.items():
    source = REPO_ROOT / root_name
    content = source.read_text(encoding="utf-8")
    content = _rewrite_links(content, output_path)
    header = (
        f"> Canonical source: [{root_name}]({REPO_BLOB_BASE}/{root_name})\n"
        "> This page is generated for the docs site from the repository root document.\n\n"
    )
    with mkdocs_gen_files.open(output_path, "w") as fd:
        fd.write(header)
        fd.write(content)
