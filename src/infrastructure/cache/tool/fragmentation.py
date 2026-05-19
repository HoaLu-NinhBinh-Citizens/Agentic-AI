"""Memory Fragmentation Manager with Slab Allocator.

Manages memory fragmentation to prevent OOM despite "theoretical memory OK".
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.cache.tool.lru_store import CacheEntry

logger = logging.getLogger(__name__)


@dataclass
class MemoryFragmentationMetrics:
    """Metrics for memory fragmentation tracking."""

    total_allocated_bytes: int = 0
    total_used_bytes: int = 0
    largest_free_block: int = 0
    num_free_blocks: int = 0
    fragmentation_ratio: float = 0.0

    @property
    def wasted_bytes(self) -> int:
        """Bytes wasted due to fragmentation."""
        return self.total_allocated_bytes - self.total_used_bytes

    @property
    def is_fragmented(self) -> bool:
        """Check if fragmentation is severe."""
        return self.fragmentation_ratio > 0.3


@dataclass
class SlabConfig:
    """Configuration for slab allocator."""

    slab_sizes: list[int] = field(
        default_factory=lambda: [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]
    )
    large_object_threshold: int = 1024 * 100
    max_slab_fill: float = 0.8


@dataclass
class FragmentationConfig:
    """Configuration for fragmentation management."""

    fragmentation_threshold: float = 0.4
    check_interval_seconds: float = 300.0
    auto_defrag_enabled: bool = True
    defrag_batch_size: int = 100


class MemoryBlock:
    """Represents a memory block in the slab allocator."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.in_use: bool = False
        self.allocations: list[int] = []

    def allocate(self, size: int) -> bool:
        """Allocate space within this block."""
        if self.in_use:
            return False
        if sum(self.allocations) + size > self.size:
            return False
        self.allocations.append(size)
        self.in_use = True
        return True

    def release(self) -> None:
        """Release the block."""
        self.allocations.clear()
        self.in_use = False

    @property
    def used_bytes(self) -> int:
        """Bytes currently used."""
        return sum(self.allocations)

    @property
    def free_bytes(self) -> int:
        """Bytes available in this block."""
        return self.size - self.used_bytes


class SlabAllocator:
    """Slab allocator to reduce fragmentation.

    Uses power-of-two sized slabs to reduce internal fragmentation.
    """

    def __init__(self, config: SlabConfig | None = None) -> None:
        self.config = config or SlabConfig()
        self._slabs: dict[int, list[MemoryBlock]] = {
            size: [] for size in self.config.slab_sizes
        }
        self._slab_usage: dict[int, int] = {
            size: 0 for size in self.config.slab_sizes
        }
        self._direct_allocations: list[MemoryBlock] = []
        self._lock = asyncio.Lock()

    def _best_fit_size(self, size: int) -> int:
        """Find smallest slab that fits the size."""
        for slab_size in self.config.slab_sizes:
            if slab_size >= size:
                return slab_size
        return self.config.slab_sizes[-1]

    def _create_block(self, slab_size: int) -> MemoryBlock:
        """Create a new memory block."""
        return MemoryBlock(slab_size)

    async def allocate(self, size: int) -> Optional[MemoryBlock]:
        """Allocate a memory block.

        Args:
            size: Required size in bytes

        Returns:
            MemoryBlock if allocation successful, None otherwise
        """
        async with self._lock:
            if size > self.config.large_object_threshold:
                block = self._create_block(size)
                self._direct_allocations.append(block)
                return block

            slab_size = self._best_fit_size(size)

            for block in self._slabs[slab_size]:
                if not block.in_use and block.free_bytes >= size:
                    if block.allocate(size):
                        return block

            if self._slab_usage[slab_size] < self.config.max_slab_fill * 100:
                new_block = self._create_block(slab_size)
                new_block.allocate(size)
                self._slabs[slab_size].append(new_block)
                self._slab_usage[slab_size] += 1
                return new_block

            return None

    async def release(self, block: MemoryBlock) -> None:
        """Release a memory block."""
        async with self._lock:
            if block in self._direct_allocations:
                self._direct_allocations.remove(block)
                return

            for slab_size, slabs in self._slabs.items():
                if block in slabs:
                    block.release()
                    return

    async def get_metrics(self) -> MemoryFragmentationMetrics:
        """Get current memory fragmentation metrics."""
        total_allocated = 0
        total_used = 0
        total_free = 0
        num_free_blocks = 0

        for slab_size, slabs in self._slabs.items():
            for block in slabs:
                total_allocated += block.size
                total_used += block.used_bytes
                total_free += block.free_bytes
                if not block.in_use:
                    num_free_blocks += 1

        for block in self._direct_allocations:
            total_allocated += block.size
            total_used += block.used_bytes

        fragmentation_ratio = (
            total_free / total_allocated if total_allocated > 0 else 0.0
        )

        largest_free = max(
            (block.free_bytes for slab in self._slabs.values() for block in slab if not block.in_use),
            default=0
        )

        return MemoryFragmentationMetrics(
            total_allocated_bytes=total_allocated,
            total_used_bytes=total_used,
            largest_free_block=largest_free,
            num_free_blocks=num_free_blocks,
            fragmentation_ratio=fragmentation_ratio,
        )


@dataclass
class LargeObjectPolicy:
    """Policy for evicting large objects."""

    LARGE_OBJECT_THRESHOLD: int = 1024

    def calculate_eviction_score(
        self,
        entry: CacheEntry,
        lru_score: float,
        size_bytes: int,
    ) -> float:
        """Calculate eviction score with size penalty.

        Args:
            entry: Cache entry
            lru_score: Base LRU score (higher = better)
            size_bytes: Size of entry in bytes

        Returns:
            Eviction score (higher = more likely to evict)
        """
        score = lru_score

        if size_bytes > self.LARGE_OBJECT_THRESHOLD:
            size_ratio = size_bytes / self.LARGE_OBJECT_THRESHOLD
            penalty = min(0.3, 0.1 * (size_ratio - 1))
            score += penalty

        if hasattr(entry, "access_count") and entry.access_count > 10:
            score *= 0.8

        return score

    def should_evict_large_object(
        self,
        entry: CacheEntry,
        memory_pressure: float,
    ) -> bool:
        """Check if large object should be evicted.

        Args:
            entry: Cache entry
            memory_pressure: Current memory pressure (0.0 - 1.0)

        Returns:
            True if should evict
        """
        if memory_pressure < 0.9:
            return False
        return True


class DefragmentationManager:
    """Manages memory defragmentation.

    Trigger conditions:
    - fragmentation_ratio > threshold
    - Periodic check
    """

    def __init__(
        self,
        cache: Any,
        config: FragmentationConfig | None = None,
    ) -> None:
        self.config = config or FragmentationConfig()
        self._cache = cache
        self._slab_allocator = SlabAllocator()
        self._large_object_policy = LargeObjectPolicy()

        self._defrag_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_defrag_time: Optional[float] = None

    async def start(self) -> None:
        """Start the defragmentation manager."""
        if self._running:
            return

        self._running = True
        self._defrag_task = asyncio.create_task(self._defrag_loop())
        logger.info("Defragmentation manager started")

    async def stop(self) -> None:
        """Stop the defragmentation manager."""
        self._running = False
        if self._defrag_task:
            self._defrag_task.cancel()
            try:
                await self._defrag_task
            except asyncio.CancelledError:
                pass
        logger.info("Defragmentation manager stopped")

    async def _defrag_loop(self) -> None:
        """Periodic defragmentation loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.check_interval_seconds)
                await self._check_and_defragment()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Defragmentation loop error: {e}")

    async def should_defragment(self) -> bool:
        """Check if defragmentation should be triggered."""
        metrics = await self._slab_allocator.get_metrics()
        return (
            metrics.fragmentation_ratio > self.config.fragmentation_threshold
            and metrics.is_fragmented
        )

    async def defragment(self) -> bool:
        """Perform defragmentation.

        Returns:
            True if defragmentation was performed
        """
        if not self.config.auto_defrag_enabled:
            return False

        if not await self.should_defragment():
            return False

        logger.info("Starting memory defragmentation...")

        entries = list(self._cache.entries.items())
        self._cache.entries.clear()

        sorted_entries = sorted(
            entries,
            key=lambda x: len(str(x[1].value)) if hasattr(x[1], "value") else 0,
            reverse=True,
        )

        for key, entry in sorted_entries:
            self._cache.entries[key] = entry

        self._last_defrag_time = time.time()
        logger.info(f"Defragmentation complete, processed {len(entries)} entries")

        return True

    async def _check_and_defragment(self) -> None:
        """Check and trigger defragmentation if needed."""
        if await self.should_defragment():
            await self.defragment()

    async def get_metrics(self) -> MemoryFragmentationMetrics:
        """Get current fragmentation metrics."""
        return await self._slab_allocator.get_metrics()

    def get_large_object_score(
        self,
        entry: CacheEntry,
        lru_score: float,
    ) -> float:
        """Get eviction score for a large object."""
        size = len(str(entry.value)) if hasattr(entry, "value") else 0
        return self._large_object_policy.calculate_eviction_score(
            entry, lru_score, size
        )
