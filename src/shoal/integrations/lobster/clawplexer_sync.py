"""QMD sync between Shoal journal and Lobster Party Claw conversations.

No gRPC dependency — operates entirely on local QMD files.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("shoal.clawplexer_sync")


class ClawplexerSync:
    """QMD sync loop between Shoal journal and Lobster Party Claw conversations."""

    def __init__(
        self,
        session_id: str,
        conversations_dir: Path,
        poll_interval: float = 30.0,
    ) -> None:
        self.session_id = session_id
        self.conversations_dir = conversations_dir
        self.poll_interval = poll_interval

    def sync_once(self, direction: str = "import") -> dict[str, int]:
        """Sync conversations once.

        Args:
            direction: "import", "export", or "both".

        Returns:
            Dict with "imported" and "exported" counts.
        """
        from shoal.core.journal import journal_path
        from shoal.core.qmd import sync_journal_with_qmd

        j_path = journal_path(self.session_id)
        result = sync_journal_with_qmd(
            journal_path=j_path,
            conversations_dir=self.conversations_dir,
            session_id=self.session_id,
            session_name=self.session_id,
            direction=direction,
        )
        logger.info(
            "Clawplexer sync: %d imported, %d exported",
            result["imported"],
            result["exported"],
        )
        return result

    async def run_sync_loop(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Poll loop that syncs on every interval.

        Checks stop_event AFTER the first sync so at least one sync always runs.

        Args:
            stop_event: When set, exits after the current sync completes.
        """
        while True:
            await asyncio.to_thread(self.sync_once)
            if stop_event and stop_event.is_set():
                break
            await asyncio.sleep(self.poll_interval)


def sync_for_handoff(
    session_id: str,
    conversations_dir: Path,
) -> int:
    """Import latest Claw turns before generating a handoff.

    Args:
        session_id: The session to sync.
        conversations_dir: Path to the Claw conversations directory.

    Returns:
        Number of turns imported.
    """
    syncer = ClawplexerSync(session_id=session_id, conversations_dir=conversations_dir)
    result = syncer.sync_once(direction="import")
    return result["imported"]
