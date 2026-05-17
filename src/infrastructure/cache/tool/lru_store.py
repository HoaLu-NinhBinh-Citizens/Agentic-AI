"""LRU Store with byte and entry bounds.

Provides memory-bounded cache storage with O(1) get operations.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from src.infrastructure.cache.tool.types import CacheEntry

logger = logging.getLogger(__name__)


@dataclass
class LRUConfig:
    """Configuration for LRU store."""

    max_entries: int = 1000
    max_memory_bytes: int = 100 * 1024 * 1024
    eviction_batch_size: int = 10


class LRUStore:
    """Lock-free LRU store with memory bounds.

    Features:
    - O(1) get for HIT/FRESH
    - Byte and entry limits
    - LRU eviction
    - Thread-safe operations
    """

    def __init__(self, config: LRUConfig | None = None) -> None:
        self.config = config or LRUConfig()

        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._memory_bytes: int = 0
        self._evictions: int = 0

        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry from store (O(1) for read path).

        Args:
            key: Cache key

        Returns:
            CacheEntry or None if not found
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        entry.touch()
        self._store.move_to_end(key)
        return entry

    async def set(
        self,
        key: str,
        entry: CacheEntry,
        force: bool = False,
    ) -> bool:
        """Set entry in store.

        Args:
            key: Cache key
            entry: Cache entry
            force: Force set even if exceeds limits

        Returns:
            True if set successfully
        """
        async with self._lock:
            old_entry = self._store.get(key)

            if old_entry:
                self._memory_bytes -= self._estimate_size(old_entry)
                del self._store[key]

            size = self._estimate_size(entry)
            self._memory_bytes += size

            if not force and (size > self.config.max_memory_bytes):
                logger.warning(
                    f"Entry size {size} exceeds max memory {self.config.max_memory_bytes}"
                )
                self._memory_bytes -= size
                return False

            self._store[key] = entry

            while self._should_evict():
                self._evict_one()

            return True

    async def delete(self, key: str) -> bool:
        """Delete entry from store.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            if key not in self._store:
                return False

            entry = self._store.pop(key)
            self._memory_bytes -= self._estimate_size(entry)
            return True

    async def contains(self, key: str) -> bool:
        """Check if key exists in store."""
        return key in self._store

    async def size(self) -> int:
        """Get number of entries."""
        return len(self._store)

    async def memory_bytes(self) -> int:
        """Get current memory usage."""
        return self._memory_bytes

    def _estimate_size(self, entry: CacheEntry) -> int:
        """Estimate memory size of entry.

        Args:
            entry: Cache entry

        Returns:
            Estimated size in bytes
        """
        base_size = sys.getsizeof(entry)
        key_size = sys.getsizeof(entry.key)
        value_size = self._estimate_value_size(entry.value)
        metadata_size = sys.getsizeof(entry.metadata)

        return base_size + key_size + value_size + metadata_size

    def _estimate_value_size(self, value: Any) -> int:
        """Estimate size of value."""
        if value is None:
            return 0

        if isinstance(value, str):
            return len(value.encode("utf-8"))

        if isinstance(value, (int, float, bool)):
            return sys.getsizeof(value)

        if isinstance(value, dict):
            size = sys.getsizeof(value)
            for k, v in value.items():
                size += sys.getsizeof(k) + self._estimate_value_size(v)
            return size

        if isinstance(value, (list, tuple)):
            size = sys.getsizeof(value)
            for item in value:
                size += self._estimate_value_size(item)
            return size

        try:
            return len(str(value).encode("utf-8"))
        except Exception:
            return sys.getsizeof(value)

    def _should_evict(self) -> bool:
        """Check if eviction is needed."""
        return (
            len(self._store) >= self.config.max_entries
            or self._memory_bytes > self.config.max_memory_bytes
        )

    def _evict_one(self) -> bool:
        """Evict one LRU entry (must hold lock)."""
        if not self._store:
            return False

        key, entry = self._store.popitem(last=False)
        self._memory_bytes -= self._estimate_size(entry)
        self._evictions += 1

        logger.debug(f"Evicted key: {key}")
        return True

    async def evict_lru(self, count: int = 1) -> int:
        """Evict multiple LRU entries.

        Args:
            count: Number of entries to evict

        Returns:
            Number of entries evicted
        """
        async with self._lock:
            evicted = 0
            for _ in range(min(count, len(self._store))):
                if self._evict_one():
                    evicted += 1
                else:
                    break
            return evicted

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._store.clear()
            self._memory_bytes = 0

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        return {
            "size": len(self._store),
            "max_entries": self.config.max_entries,
            "memory_bytes": self._memory_bytes,
            "max_memory_bytes": self.config.max_memory_bytes,
            "evictions": self._evictions,
            "utilization_entries": len(self._store) / self.config.max_entries if self.config.max_entries > 0 else 0,
            "utilization_memory": self._memory_bytes / self.config.max_memory_bytes if self.config.max_memory_bytes > 0 else 0,
        }

    async def keys(self) -> list[str]:
        """Get all keys."""
        return list(self._store.keys())

    async def entries(self) -> list[CacheEntry]:
        """Get all entries."""
        return list(self._store.values())


class PinManager:
    """Manages pinned cache entries.

    Pinned entries have dual constraint handling:
    - max_pinned_entries
    - max_pinned_memory_bytes

    Eviction order:
    1. Non-pinned LRU (first priority)
    2. Pinned LRU (only if necessary)

    Invariant: Pinned entries are NOT exempt from eviction under memory pressure.
    """

    def __init__(
        self,
        store: LRUStore,
        max_pinned_entries: int = 100,
        max_pinned_memory_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.store = store
        self.max_pinned_entries = max_pinned_entries
        self.max_pinned_memory_bytes = max_pinned_memory_bytes

        self._pinned_keys: set[str] = set()
        self._pinned_memory: int = 0
        self._lock = asyncio.Lock()

    async def pin(self, key: str) -> bool:
        """Pin an entry.

        Args:
            key: Cache key to pin

        Returns:
            True if pinned successfully
        """
        async with self._lock:
            if key in self._pinned_keys:
                return True

            entry = await self.store.get(key)
            if entry is None:
                return False

            size = self.store._estimate_size(entry)

            if (
                len(self._pinned_keys) >= self.max_pinned_entries
                or self._pinned_memory + size > self.max_pinned_memory_bytes
            ):
                await self._evict_pinned_to_make_room(size)

            entry.is_pinned = True
            self._pinned_keys.add(key)
            self._pinned_memory += size

            return True

    async def unpin(self, key: str) -> bool:
        """Unpin an entry.

        Args:
            key: Cache key to unpin

        Returns:
            True if unpinned successfully
        """
        async with self._lock:
            if key not in self._pinned_keys:
                return False

            entry = await self.store.get(key)
            if entry:
                self._pinned_memory -= self.store._estimate_size(entry)
                entry.is_pinned = False

            self._pinned_keys.discard(key)
            return True

    async def is_pinned(self, key: str) -> bool:
        """Check if key is pinned."""
        return key in self._pinned_keys

    def get_pinned_count(self) -> int:
        """Get number of pinned entries."""
        return len(self._pinned_keys)

    def get_pinned_memory(self) -> int:
        """Get pinned memory usage."""
        return self._pinned_memory

    async def _evict_pinned_to_make_room(self, required_size: int) -> None:
        """Evict pinned entries to make room.

        Pinned entries can be evicted under memory pressure.
        """
        while self._pinned_keys:
            if (
                len(self._pinned_keys) < self.max_pinned_entries
                and self._pinned_memory < self.max_pinned_memory_bytes - required_size
            ):
                break

            oldest_pinned = next(iter(self._pinned_keys))
            await self.unpin(oldest_pinned)
            await self.store.delete(oldest_pinned)

    async def force_evict_under_pressure(self) -> int:
        """Force eviction even for pinned entries under memory pressure.

        Called when system is under severe memory pressure.

        Returns:
            Number of entries evicted
        """
        async with self._lock:
            evicted = 0

            while self._pinned_keys and self.store._memory_bytes > self.store.config.max_memory_bytes:
                oldest_pinned = next(iter(self._pinned_keys))
                self._pinned_memory -= self.store._estimate_size(
                    self.store._store.get(oldest_pinned)
                )
                self._pinned_keys.discard(oldest_pinned)
                self.store._store.pop(oldest_pinned, None)
                evicted += 1

            return evicted

    def get_stats(self) -> dict[str, Any]:
        """Get pin manager statistics."""
        return {
            "pinned_count": len(self._pinned_keys),
            "max_pinned_entries": self.max_pinned_entries,
            "pinned_memory": self._pinned_memory,
            "max_pinned_memory_bytes": self.max_pinned_memory_bytes,
        }
