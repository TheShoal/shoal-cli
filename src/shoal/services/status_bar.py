"""Status bar data generator — entry point for shoal-status."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from shoal.core.state import list_sessions

if TYPE_CHECKING:
    pass

logger = logging.getLogger("shoal.status_bar")

_STATUS_KEYS = ("running", "idle", "waiting", "error", "inactive")


async def generate_status() -> dict[str, int]:
    """Generate status counts for all sessions from the local database.

    Returns:
        Dict with counts: running, idle, waiting, error, inactive.
    """
    sessions = await list_sessions()
    logger.debug("Generating status bar for %d session(s)", len(sessions))
    counts: dict[str, int] = {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}

    for session in sessions:
        status_val = session.status.value
        if status_val in counts:
            counts[status_val] += 1
        elif status_val in ("stopped", "unknown"):
            counts["inactive"] += 1
        else:
            counts["inactive"] += 1

    return counts


async def generate_status_extended() -> dict[str, object]:
    """Generate status counts plus per-session Dreamer summaries.

    Includes a ``dreamer_summaries`` dict mapping session name → latest summary
    for all sessions where Dreamer has produced at least one summary.

    Returns:
        Dict with counts (running/idle/waiting/error/inactive) and
        ``dreamer_summaries: {name: summary_text}``.
    """
    from shoal.core.journal import read_journal
    from shoal.services.dreamer import get_dreamer

    sessions = await list_sessions()
    running = idle = waiting = error = inactive = 0

    dreamer = get_dreamer()
    dreamer_summaries: dict[str, str] = {}

    for session in sessions:
        status_val = session.status.value
        if status_val == "running":
            running += 1
        elif status_val == "idle":
            idle += 1
        elif status_val == "waiting":
            waiting += 1
        elif status_val == "error":
            error += 1
        else:
            inactive += 1

        # 1. In-process singleton (fastest).
        if dreamer is not None:
            summary = dreamer.get_summary(session.id)
            if summary:
                dreamer_summaries[session.name] = summary
                continue

        # 2. Fall back to latest dreamer journal entry.
        try:
            entries = await asyncio.to_thread(read_journal, session.id, limit=50)
            for entry in reversed(entries):
                if entry.source == "dreamer":
                    dreamer_summaries[session.name] = entry.content
                    break
        except Exception:
            logger.debug(
                "Failed to read journal for dreamer summary: %s", session.id, exc_info=True
            )

    counts: dict[str, object] = {
        "running": running,
        "idle": idle,
        "waiting": waiting,
        "error": error,
        "inactive": inactive,
        "dreamer_summaries": dreamer_summaries,
    }
    return counts


def generate_remote_status(host: str, api_port: int, timeout: int = 5) -> dict[str, int]:
    """Fetch status counts from a remote Shoal API server.

    Calls ``GET http://<host>:<api_port>/status`` and maps the response into
    the same ``{running, idle, waiting, error, inactive}`` shape used by
    :func:`generate_status`.

    Args:
        host: Hostname or IP of the remote Shoal API server.
        api_port: Port the Shoal API server is listening on.
        timeout: Request timeout in seconds (default 5).

    Returns:
        Dict with counts: running, idle, waiting, error, inactive.
        On connection failure, returns all-zero counts and logs a warning.
    """
    url = f"http://{host}:{api_port}/status"
    empty: dict[str, int] = {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            raw: dict[str, object] = json.loads(resp.read())
    except urllib.error.URLError as exc:
        logger.warning("Remote status unavailable (%s): %s", url, exc)
        return empty
    except Exception:
        logger.warning("Unexpected error fetching remote status from %s", url, exc_info=True)
        return empty

    # Map the API's StatusResponse fields onto our display shape.
    # stopped/unknown → inactive; total/version are ignored.
    counts: dict[str, int] = {"running": 0, "idle": 0, "waiting": 0, "error": 0, "inactive": 0}
    for key in ("running", "idle", "waiting", "error"):
        val = raw.get(key, 0)
        counts[key] = int(val) if isinstance(val, (int, float)) else 0
    for key in ("stopped", "unknown"):
        val = raw.get(key, 0)
        counts["inactive"] += int(val) if isinstance(val, (int, float)) else 0

    return counts


def main() -> None:
    """Entry point for shoal-status console script.

    Usage::

        shoal-status                       # local DB
        shoal-status --extended            # include Dreamer summaries
        shoal-status --remote <name>       # remote host named in [remote.<name>]
    """
    remote_name: str | None = None
    extended = False
    args = sys.argv[1:]
    if "--extended" in args:
        extended = True
        args = [a for a in args if a != "--extended"]
    if "--remote" in args:
        idx = args.index("--remote")
        if idx + 1 >= len(args):
            print(json.dumps({"error": "--remote requires a host name"}))
            sys.exit(1)
        remote_name = args[idx + 1]

    if remote_name is not None:
        from shoal.core.config import load_config

        cfg = load_config()
        host_cfg = cfg.remote.get(remote_name)
        if host_cfg is None:
            known = list(cfg.remote.keys())
            print(json.dumps({"error": f"Unknown remote '{remote_name}'. Known: {known}"}))
            sys.exit(1)
        counts: object = generate_remote_status(host_cfg.host, host_cfg.api_port)
    else:
        from shoal.core.db import with_db

        if extended:
            counts = asyncio.run(with_db(generate_status_extended()))
        else:
            counts = asyncio.run(with_db(generate_status()))

    print(json.dumps(counts))


if __name__ == "__main__":
    main()
