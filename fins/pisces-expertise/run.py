#!/usr/bin/env python3
"""pisces-expertise fin — run entrypoint.

Reads a completed Shoal session's journal, synthesizes what the agent
discovered via LLM, and appends the expertise note to the template's
expertise file at::

    ~/.config/shoal/templates/<template>/expertise.md

Usage (via shoal fin run):
    run.py <session_name> [--template <template_name>]

Environment (injected by shoal fin runtime):
    SHOAL_FIN_ROOT        Absolute path to this fin's directory.
    SHOAL_OUTPUT_FORMAT   "text" or "json" (unused — always text output).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract and persist session expertise for a Shoal template."
    )
    p.add_argument("session", help="Shoal session name (e.g. auth-feature-planner)")
    p.add_argument(
        "--template",
        default="",
        help="Template name whose expertise.md to update (e.g. pisces-engineer)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

# Journal entries are summarised up to this character budget before being
# sent to the LLM.  Keeps prompt well within Nova Lite's 300k context window
# while avoiding unnecessary token spend.
_MAX_JOURNAL_CHARS = 12_000

_SUMMARISE_MODEL = "amazon.nova-lite-v1:0"
_SUMMARISE_MAX_TOKENS = 700
_SUMMARISE_TEMPERATURE = 0.2

_PROMPT_TEMPLATE = """\
You are reviewing a completed agentic coding session.

Extract a compact expertise note: which files and codepaths the agent \
navigated, patterns and conventions it discovered, decisions it made, \
and any gotchas worth remembering.

Write 4–8 concise bullet points starting with "- ". Be specific: name \
files, functions, and patterns. No introduction, no conclusion — bullets only.

Session: {session}
Template: {template}

Journal (oldest first):
{journal}

Expertise bullets:"""


async def _run(session_name: str, template: str) -> int:
    from shoal.core.config import templates_dir
    from shoal.core.db import get_db
    from shoal.core.journal import read_journal
    from shoal.services.ai_client import call_llm

    # 1. Resolve session name → session ID via Shoal DB
    db = await get_db()
    session = await db.find_session_by_name(session_name)
    if session is None:
        print(f"ERROR: session not found: {session_name!r}", file=sys.stderr)
        return 1

    # 2. Read journal entries (sync helper, run in current thread)
    entries = read_journal(session.id, limit=100)
    if not entries:
        print(
            f"No journal entries for {session_name!r} — nothing to summarise.",
            file=sys.stderr,
        )
        return 0  # not a failure; session may have had no written activity

    # Build a compact journal text within budget
    lines = [
        f"[{e.timestamp.strftime('%H:%M')}] {e.source}: {e.content}"
        for e in entries
    ]
    journal_text = "\n".join(lines)[-_MAX_JOURNAL_CHARS:]

    template_label = template or "unknown"
    prompt = _PROMPT_TEMPLATE.format(
        session=session_name,
        template=template_label,
        journal=journal_text,
    )

    # 3. LLM summarise
    try:
        summary = await call_llm(
            model=_SUMMARISE_MODEL,
            prompt=prompt,
            max_tokens=_SUMMARISE_MAX_TOKENS,
            temperature=_SUMMARISE_TEMPERATURE,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: LLM call failed: {exc}", file=sys.stderr)
        return 1

    # 4. Append to expertise file
    #    Path: ~/.config/shoal/templates/<template>/expertise.md
    #    Matches the path computed by Pisces expertise.ts (getExpertisePath).
    expertise_dir: Path = templates_dir() / template_label
    expertise_dir.mkdir(parents=True, exist_ok=True)
    expertise_path = expertise_dir / "expertise.md"

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n\n## {date_str} — {session_name}\n\n{summary.strip()}\n"

    with expertise_path.open("a") as fh:
        fh.write(entry)

    print(f"Expertise appended to {expertise_path}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()
    sys.exit(asyncio.run(_run(args.session, args.template)))


if __name__ == "__main__":
    main()
