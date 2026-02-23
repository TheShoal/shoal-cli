"""Status bar data generator — entry point for shoal-status."""

from __future__ import annotations

import asyncio
import json

from shoal.core.state import list_sessions


async def generate_status() -> dict[str, int]:
    """Generate status counts for all sessions.

    Returns:
        Dict with counts: running, idle, waiting, error, inactive.
    """
    sessions = await list_sessions()
    counts = {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    for session in sessions:
        status_val = session.status.value
        if status_val in counts:
            counts[status_val] += 1
        elif status_val in ("stopped", "unknown"):
            counts["inactive"] += 1
        else:
            counts["inactive"] += 1

    return counts


def main() -> None:
    """Entry point for shoal-status console script."""
    from shoal.core.db import with_db

    print(json.dumps(asyncio.run(with_db(generate_status()))))


if __name__ == "__main__":
    main()
