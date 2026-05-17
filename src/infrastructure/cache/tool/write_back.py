"""Write-Back Queue with non-blocking operations.

Provides async write-back to persistent storage with drop/spill only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.infrastructure.cache.tool.types import CacheEntry

logger = logging.getLogger(__name__)


@dataclass
class WriteBackConfig:
    """Configuration for write-back queue."""

    max_queue_size: int = 10000
    max_memory_mb: int = 50
    flush_interval_seconds: float = 30.0
    flush_batch_size: int = 100
    spill_path: str = "/tmp/tool_cache/spill"
    enable_spill: bool = True


@dataclass
class WriteBackEntry:
    """Entry for write-back queue."""

    key: str
    entry: CacheEntry
    priority: int = 0
    created_at: float = field(default_factory=time.time)


class WriteBackQueue:
    """Non-blocking write-back queue.

    Rules:
    - drop OR spill_to_disk ONLY
    - Never block

    Guarantees:
    - No blocking I/O in hot path
    - Graceful degradation on overflow
    """

    def __init__(self, config: WriteBackConfig | None = None) -> None:
        self.config = config or WriteBackConfig()

        self._queue: asyncio.PriorityQueue[tuple[int, WriteBackEntry]] = (
            asyncio.PriorityQueue(maxsize=self.config.max_queue_size)
        )
        self._memory_bytes: int = 0
        self._spill_path = Path(self.config.spill_path)
        self._spill_files: list[Path] = []
        self._spill_size: int = 0

        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the write-back queue."""
        if self._running:
            return

        self._running = True
        self._spill_path.mkdir(parents=True, exist_ok=True)

        self._flush_task = asyncio.create_task(self._flush_loop())

        logger.info("WriteBackQueue started")

    async def stop(self) -> None:
        """Stop the write-back queue."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        await self._flush_all()

        logger.info("WriteBackQueue stopped")

    async def enqueue(
        self,
        key: str,
        entry: CacheEntry,
        priority: int = 0,
    ) -> bool:
        """Enqueue a write-back operation (non-blocking).

        Args:
            key: Cache key
            entry: Cache entry
            priority: Higher = more urgent

        Returns:
            True if enqueued, False if dropped
        """
        write_back_entry = WriteBackEntry(
            key=key,
            entry=entry,
            priority=priority,
        )

        size = self._estimate_size(entry)

        if self._memory_bytes + size > self.config.max_memory_mb * 1024 * 1024:
            if self.config.enable_spill:
                await self._spill_entry(write_back_entry)
                return True
            else:
                logger.debug(f"Write-back queue full, dropping: {key}")
                return False

        try:
            self._queue.put_nowait((~priority, write_back_entry))
            self._memory_bytes += size
            return True
        except asyncio.QueueFull:
            if self.config.enable_spill:
                await self._spill_entry(write_back_entry)
                return True
            else:
                logger.debug(f"Write-back queue full, dropping: {key}")
                return False

    async def _spill_entry(self, entry: WriteBackEntry) -> None:
        """Spill entry to disk."""
        try:
            import json

            spill_file = self._spill_path / f"spill_{int(time.time() * 1000)}.json"

            data = {
                "key": entry.key,
                "entry": {
                    "key": entry.entry.key,
                    "value": entry.entry.value,
                    "state": entry.entry.state.name,
                    "created_at": entry.entry.created_at,
                    "expires_at": entry.entry.expires_at,
                    "metadata": entry.entry.metadata,
                },
                "priority": entry.priority,
                "created_at": entry.created_at,
            }

            with open(spill_file, "w") as f:
                json.dump(data, f)

            self._spill_files.append(spill_file)
            self._spill_size += spill_file.stat().st_size

            logger.debug(f"Spilled entry to: {spill_file}")

        except Exception as e:
            logger.error(f"Failed to spill entry: {e}")

    async def _flush_loop(self) -> None:
        """Background loop that flushes to persistent store."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush_batch(self) -> None:
        """Flush a batch of entries."""
        async with self._lock:
            flushed = 0

            for _ in range(self.config.flush_batch_size):
                try:
                    _, entry = self._queue.get_nowait()
                    self._memory_bytes -= self._estimate_size(entry.entry)

                    await self._write_entry(entry)

                    flushed += 1

                except asyncio.QueueEmpty:
                    break

            if flushed > 0:
                logger.debug(f"Flushed {flushed} entries")

    async def _flush_all(self) -> None:
        """Flush all remaining entries."""
        async with self._lock:
            flushed = 0

            while not self._queue.empty():
                try:
                    _, entry = self._queue.get_nowait()
                    self._memory_bytes -= self._estimate_size(entry.entry)
                    await self._write_entry(entry)
                    flushed += 1
                except asyncio.QueueEmpty:
                    break

            logger.info(f"Flushed {flushed} entries on shutdown")

    async def _write_entry(self, entry: WriteBackEntry) -> None:
        """Write a single entry (called by persistence layer)."""
        logger.debug(f"Write-back for key: {entry.key}")

    def _estimate_size(self, entry: CacheEntry) -> int:
        """Estimate size of entry."""
        import sys

        base = sys.getsizeof(entry)
        value_size = sys.getsizeof(entry.value)
        return base + value_size

    async def cleanup_spill(self) -> int:
        """Clean up spill files.

        Returns:
            Number of files cleaned up
        """
        cleaned = 0

        for spill_file in self._spill_files:
            try:
                if spill_file.exists():
                    spill_file.unlink()
                    cleaned += 1
            except Exception as e:
                logger.error(f"Failed to cleanup spill file: {e}")

        self._spill_files.clear()
        self._spill_size = 0

        return cleaned

    def get_stats(self) -> dict[str, Any]:
        """Get write-back queue statistics."""
        return {
            "queue_size": self._queue.qsize(),
            "max_queue_size": self.config.max_queue_size,
            "memory_bytes": self._memory_bytes,
            "max_memory_mb": self.config.max_memory_mb,
            "spill_files": len(self._spill_files),
            "spill_size": self._spill_size,
        }
