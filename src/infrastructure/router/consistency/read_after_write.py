"""Read-after-write consistency guard."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.snapshot import SnapshotManager
    from src.infrastructure.router.types import ConsistencyConfig, Snapshot

logger = logging.getLogger(__name__)


class ReadAfterWriteGuard:
    """
    Ensures read-after-write consistency with configurable behavior.
    
    When feedback is written, there may be a delay before the next
    request sees the change. This guard manages that consistency.
    """

    def __init__(
        self,
        config: ConsistencyConfig,
        snapshot_manager: SnapshotManager,
    ):
        self._config = config
        self._snapshot_manager = snapshot_manager
        self._last_feedback_time: Optional[float] = None
        self._feedback_lock = asyncio.Lock()

    async def on_feedback_written(self) -> None:
        """Called after feedback successfully written."""
        async with self._feedback_lock:
            self._last_feedback_time = time.time()
            logger.debug("Feedback written, tracking for consistency")

    async def should_force_new_snapshot(self) -> tuple[bool, Optional[str]]:
        """
        Check if new snapshot should be created.
        
        Returns:
            (should_force, reason)
        """
        if not self._last_feedback_time:
            return False, None

        elapsed_ms = (time.time() - self._last_feedback_time) * 1000

        if elapsed_ms < self._config.read_after_write_guard_ms:
            if self._config.force_new_snapshot_on_feedback:
                reason = f"Feedback at {elapsed_ms:.0f}ms ago, forcing new snapshot"
                return True, reason
            else:
                if self._config.warn_on_stale_snapshot:
                    logger.warning(
                        f"Using potentially stale snapshot: "
                        f"feedback written {elapsed_ms:.0f}ms ago"
                    )
                return False, None

        return False, None

    async def after_feedback(
        self,
        snapshot_manager: SnapshotManager,
    ) -> Optional[Snapshot]:
        """
        After feedback is written, potentially create new snapshot.
        
        Args:
            snapshot_manager: Manager to create new snapshot if needed
            
        Returns:
            New snapshot if forced, None otherwise
        """
        should_force, reason = await self.should_force_new_snapshot()

        if should_force:
            return await snapshot_manager.force_new_snapshot(reason)

        return None

    def get_guard_status(self) -> dict:
        """Get current guard status for monitoring."""
        if not self._last_feedback_time:
            return {"status": "idle", "elapsed_ms": None}

        elapsed_ms = (time.time() - self._last_feedback_time) * 1000
        return {
            "status": "guarding" if elapsed_ms < self._config.read_after_write_guard_ms else "expired",
            "elapsed_ms": elapsed_ms,
            "guard_threshold_ms": self._config.read_after_write_guard_ms,
        }
