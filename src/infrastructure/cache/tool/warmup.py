"""WarmUp Manager with atomic initialization.

Loads cache entries before traffic enablement. Atomic guarantee.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from src.infrastructure.cache.tool.state_machine import StateManager
from src.infrastructure.cache.tool.types import CacheEntry, KeyState

logger = logging.getLogger(__name__)


@dataclass
class WarmupEntry:
    """Entry to be loaded during warmup."""

    key: str
    value: Any
    ttl_seconds: float = 300.0
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class WarmupConfig:
    """Configuration for warmup."""

    timeout_seconds: float = 60.0
    max_concurrent_loads: int = 10
    allow_partial: bool = True


class WarmUpManager:
    """WarmUp manager with atomic initialization.

    Rules:
    - Runs ONLY before traffic enablement
    - Must be fully completed before serving requests
    - Uses set_if_absent(key) OR acquire per-key lock

    Prohibited:
    - Overwrite newer data
    - Run concurrently with live traffic
    """

    def __init__(
        self,
        store: Any,
        state_manager: StateManager,
        config: WarmupConfig | None = None,
    ) -> None:
        self.store = store
        self.state_manager = state_manager
        self.config = config or WarmupConfig()

        self._warmup_entries: list[WarmupEntry] = []
        self._loaded_keys: set[str] = set()
        self._failed_keys: dict[str, str] = {}

        self._completed = False
        self._started_at: float | None = None

        self._lock = asyncio.Lock()

    def add_entry(self, entry: WarmupEntry) -> None:
        """Add an entry to warmup list.

        Args:
            entry: Entry to warm up
        """
        if self._completed:
            raise RuntimeError("Cannot add entries after warmup is completed")
        self._warmup_entries.append(entry)

    def add_entries(self, entries: list[WarmupEntry]) -> None:
        """Add multiple entries to warmup list.

        Args:
            entries: Entries to warm up
        """
        if self._completed:
            raise RuntimeError("Cannot add entries after warmup is completed")
        self._warmup_entries.extend(entries)

    async def execute(
        self,
        loader: Callable[[str], Coroutine[Any, Any, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute warmup.

        Args:
            loader: Optional async function to load value for a key

        Returns:
            Warmup result with statistics
        """
        async with self._lock:
            if self._completed:
                logger.warning("Warmup already completed")
                return self._get_result()

            if self._started_at is not None:
                raise RuntimeError("Warmup already in progress")

            self._started_at = time.time()

        logger.info(f"Starting warmup with {len(self._warmup_entries)} entries")

        self._warmup_entries.sort(key=lambda e: -e.priority)

        results = await self._load_entries(loader)

        async with self._lock:
            self._completed = True
            self._started_at = None

        logger.info(
            f"Warmup completed: {len(self._loaded_keys)} loaded, "
            f"{len(self._failed_keys)} failed"
        )

        return results

    async def _load_entries(
        self,
        loader: Callable[[str], Coroutine[Any, Any, Any]] | None,
    ) -> dict[str, Any]:
        """Load entries with bounded concurrency."""
        semaphore = asyncio.Semaphore(self.config.max_concurrent_loads)

        async def load_with_semaphore(entry: WarmupEntry) -> tuple[str, bool, str | None]:
            async with semaphore:
                try:
                    return await self._load_single_entry(entry, loader)
                except asyncio.TimeoutError:
                    logger.warning(f"Warmup timeout for key: {entry.key}")
                    return (entry.key, False, "Timeout")
                except Exception as e:
                    logger.error(f"Warmup error for key {entry.key}: {e}")
                    return (entry.key, False, str(e))

        tasks = [load_with_semaphore(entry) for entry in self._warmup_entries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple):
                key, success, error = result
                if success:
                    self._loaded_keys.add(key)
                else:
                    self._failed_keys[key] = error or "Unknown error"

        return self._get_result()

    async def _load_single_entry(
        self,
        entry: WarmupEntry,
        loader: Callable[[str], Coroutine[Any, Any, Any]] | None,
    ) -> tuple[str, bool, str | None]:
        """Load a single entry."""
        value = entry.value

        if loader is not None and value is None:
            value = await asyncio.wait_for(
                loader(entry.key),
                timeout=self.config.timeout_seconds,
            )

        if value is None:
            return (entry.key, False, "No value returned")

        cache_entry = CacheEntry(
            key=entry.key,
            value=value,
            state=KeyState.FRESH,
            created_at=time.time(),
            expires_at=time.time() + entry.ttl_seconds,
            metadata=entry.metadata,
        )

        existing = await self.store.get(entry.key)
        if existing is not None and existing.created_at > cache_entry.created_at:
            logger.debug(f"Skipping {entry.key}: newer data exists")
            return (entry.key, True, None)

        success = await self.store.set(entry.key, cache_entry, force=False)
        if success:
            await self.state_manager.transition(entry.key, "warmup", KeyState.FRESH)

        return (entry.key, success, None if success else "Store set failed")

    async def set_if_absent(
        self,
        key: str,
        value: Any,
        ttl_seconds: float = 300.0,
    ) -> bool:
        """Set entry only if absent (atomic).

        Args:
            key: Cache key
            value: Value to set
            ttl_seconds: TTL in seconds

        Returns:
            True if set, False if key exists
        """
        existing = await self.store.get(key)
        if existing is not None:
            return False

        cache_entry = CacheEntry(
            key=key,
            value=value,
            state=KeyState.FRESH,
            created_at=time.time(),
            expires_at=time.time() + ttl_seconds,
        )

        return await self.store.set(key, cache_entry, force=False)

    def is_completed(self) -> bool:
        """Check if warmup is completed."""
        return self._completed

    def is_in_progress(self) -> bool:
        """Check if warmup is in progress."""
        return self._started_at is not None

    def _get_result(self) -> dict[str, Any]:
        """Get warmup result."""
        return {
            "completed": self._completed,
            "total_entries": len(self._warmup_entries),
            "loaded_keys": list(self._loaded_keys),
            "failed_keys": dict(self._failed_keys),
            "loaded_count": len(self._loaded_keys),
            "failed_count": len(self._failed_keys),
            "success_rate": (
                len(self._loaded_keys) / len(self._warmup_entries)
                if self._warmup_entries
                else 0.0
            ),
        }

    def get_stats(self) -> dict[str, Any]:
        """Get warmup statistics."""
        return {
            "completed": self._completed,
            "in_progress": self.is_in_progress(),
            "total_entries": len(self._warmup_entries),
            "loaded_count": len(self._loaded_keys),
            "failed_count": len(self._failed_keys),
            "pending_count": len(self._warmup_entries) - len(self._loaded_keys) - len(self._failed_keys),
        }

    def reset(self) -> None:
        """Reset warmup state."""
        self._warmup_entries.clear()
        self._loaded_keys.clear()
        self._failed_keys.clear()
        self._completed = False
        self._started_at = None
