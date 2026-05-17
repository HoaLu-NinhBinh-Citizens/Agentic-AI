"""Snapshot manager for immutable snapshot creation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.types import RouterConfig, Snapshot

logger = logging.getLogger(__name__)


class SnapshotManager:
    """
    Manages snapshot lifecycle and creation.
    
    Snapshots are frozen immutable snapshots containing:
    - Configuration
    - ANN index (read-only)
    - Frequency version
    - Snapshot timestamp
    """

    def __init__(self, config_provider: ConfigProvider):
        self._config_provider = config_provider
        self._current_snapshot: Optional[Snapshot] = None
        self._snapshot_lock = asyncio.Lock()

    async def create_snapshot(self) -> Snapshot:
        """
        Create new frozen snapshot.
        
        Called when:
        1. First request
        2. Config changed
        3. Index rebuilt
        4. Force refresh after feedback
        """
        async with self._snapshot_lock:
            from src.infrastructure.router.types import Snapshot

            config = await self._config_provider.get_config()
            frequency_version = await self._config_provider.get_frequency_version()
            freq_snapshot_time = time.time()

            index = await self._load_index()

            snapshot = Snapshot(
                snapshot_id=_generate_snapshot_id(),
                config=config,
                index=index,
                frequency_version=frequency_version,
                freq_snapshot_time=freq_snapshot_time,
                created_at=time.time(),
            )

            self._current_snapshot = snapshot
            logger.debug(f"Created new snapshot: {snapshot.snapshot_id}")
            return snapshot

    async def get_current_snapshot(self) -> Snapshot:
        """Get current snapshot or create new one."""
        if self._current_snapshot is None:
            return await self.create_snapshot()
        return self._current_snapshot

    async def force_new_snapshot(self, reason: str) -> Snapshot:
        """Force create new snapshot (e.g., after feedback)."""
        logger.info(f"Forcing new snapshot: {reason}")
        return await self.create_snapshot()

    async def _load_index(self) -> Any:
        """Load ANN index (read-only copy)."""
        return await self._config_provider.get_ann_index()

    def get_snapshot_info(self) -> dict[str, Any]:
        """Get current snapshot info for debugging."""
        if self._current_snapshot is None:
            return {"status": "no_snapshot"}
        return {
            "snapshot_id": self._current_snapshot.snapshot_id,
            "frequency_version": self._current_snapshot.frequency_version,
            "age_seconds": time.time() - self._current_snapshot.created_at,
        }


class ConfigProvider:
    """
    Provides configuration data for snapshot creation.
    
    Implement this interface to integrate with your config storage.
    """

    async def get_config(self) -> "RouterConfig":
        """Get current router configuration."""
        from src.infrastructure.router.types import RouterConfig

        return RouterConfig()

    async def get_frequency_version(self) -> int:
        """Get current frequency table version."""
        return 1

    async def get_ann_index(self) -> Any:
        """Get ANN index for semantic search."""
        return None


def _generate_snapshot_id() -> str:
    """Generate unique snapshot ID."""
    import uuid

    return f"snap_{uuid.uuid4().hex[:12]}"
