"""Persistent Store with append-only async event log.

Provides eventual consistency with non-blocking writes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.infrastructure.cache.tool.types import CacheEntry, KeyState

logger = logging.getLogger(__name__)


@dataclass
class PersistenceConfig:
    """Configuration for persistence."""

    base_path: str = "/tmp/tool_cache"
    max_log_size_mb: int = 100
    gc_threshold_days: int = 7
    partition_size: int = 10000
    flush_interval_seconds: float = 5.0


@dataclass
class LogEntry:
    """Log entry for append-only store."""

    timestamp: float
    op: str
    key: str
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps({
            "timestamp": self.timestamp,
            "op": self.op,
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata,
        })

    @classmethod
    def from_json(cls, data: dict) -> LogEntry:
        """Deserialize from JSON."""
        return cls(
            timestamp=data["timestamp"],
            op=data["op"],
            key=data["key"],
            value=data["value"],
            metadata=data.get("metadata", {}),
        )


class PersistentStore:
    """Append-only event log persistence.

    Model:
    - Append-only write log
    - Eventual consistency only
    - Non-blocking writes

    Cleanup:
    - TTL > 7 days → GC
    - Incremental scan only (partitioned)

    Guarantees:
    - Never block cache operations
    - Graceful degradation on disk errors
    """

    def __init__(self, config: PersistenceConfig | None = None) -> None:
        self.config = config or PersistenceConfig()

        self._base_path = Path(self.config.base_path)
        self._log_path = self._base_path / "logs"
        self._index_path = self._base_path / "index"

        self._current_partition = 0
        self._current_log_size = 0
        self._write_queue: asyncio.Queue[LogEntry] = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task] = None
        self._running = False

        self._index: dict[str, dict[str, Any]] = {}

        self._gc_task: Optional[asyncio.Task] = None
        self._gc_running = False

    async def start(self) -> None:
        """Start the persistence layer."""
        if self._running:
            return

        self._running = True
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._log_path.mkdir(parents=True, exist_ok=True)
        self._index_path.mkdir(parents=True, exist_ok=True)

        self._writer_task = asyncio.create_task(self._write_loop())
        self._gc_task = asyncio.create_task(self._gc_loop())

        await self._load_index()

        logger.info("PersistentStore started")

    async def stop(self) -> None:
        """Stop the persistence layer."""
        self._running = False
        self._gc_running = False

        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass

        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass

        await self._flush_pending()
        await self._save_index()

        logger.info("PersistentStore stopped")

    async def append(
        self,
        op: str,
        key: str,
        value: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append an entry to the log (non-blocking).

        Args:
            op: Operation type (SET, DELETE, UPDATE)
            key: Cache key
            value: Value to persist
            metadata: Optional metadata
        """
        entry = LogEntry(
            timestamp=time.time(),
            op=op,
            key=key,
            value=value,
            metadata=metadata or {},
        )

        try:
            self._write_queue.put_nowait(entry)
        except asyncio.QueueFull:
            logger.warning(f"Write queue full, dropping entry for key: {key}")

    async def _write_loop(self) -> None:
        """Background loop that writes to disk."""
        while self._running:
            try:
                entries: list[LogEntry] = []
                deadline = time.time() + self.config.flush_interval_seconds

                while time.time() < deadline:
                    try:
                        entry = await asyncio.wait_for(
                            self._write_queue.get(),
                            timeout=deadline - time.time(),
                        )
                        entries.append(entry)
                    except asyncio.TimeoutError:
                        break

                if entries:
                    await self._write_batch(entries)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Write loop error: {e}")
                await asyncio.sleep(1.0)

    async def _write_batch(self, entries: list[LogEntry]) -> None:
        """Write a batch of entries to disk."""
        try:
            partition_path = self._get_partition_path(self._current_partition)

            async with asyncio.Lock():
                with open(partition_path, "a") as f:
                    for entry in entries:
                        f.write(entry.to_json() + "\n")
                        self._current_log_size += len(entry.to_json()) + 1

                        self._index[entry.key] = {
                            "partition": self._current_partition,
                            "timestamp": entry.timestamp,
                            "op": entry.op,
                        }

            max_size = self.config.max_log_size_mb * 1024 * 1024
            if self._current_log_size >= max_size:
                self._current_partition += 1
                self._current_log_size = 0

        except Exception as e:
            logger.error(f"Failed to write batch: {e}")

    def _get_partition_path(self, partition: int) -> Path:
        """Get path for partition file."""
        return self._log_path / f"partition_{partition:06d}.log"

    async def _flush_pending(self) -> None:
        """Flush pending writes."""
        entries: list[LogEntry] = []

        while not self._write_queue.empty():
            try:
                entry = self._write_queue.get_nowait()
                entries.append(entry)
            except asyncio.QueueEmpty:
                break

        if entries:
            await self._write_batch(entries)

    async def _gc_loop(self) -> None:
        """Background garbage collection loop."""
        self._gc_running = True

        while self._gc_running:
            try:
                await asyncio.sleep(3600.0)
                await self._incremental_gc()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"GC loop error: {e}")

    async def _incremental_gc(self) -> None:
        """Perform incremental GC (partitioned)."""
        now = time.time()
        threshold = now - self.config.gc_threshold_days * 86400

        for partition_path in self._log_path.glob("partition_*.log"):
            try:
                mtime = partition_path.stat().st_mtime
                if mtime > threshold:
                    continue

                await self._compact_partition(partition_path, threshold)

            except Exception as e:
                logger.error(f"GC error for {partition_path}: {e}")

    async def _compact_partition(
        self,
        partition_path: Path,
        threshold: float,
    ) -> None:
        """Compact a partition by removing old entries."""
        try:
            temp_path = partition_path.with_suffix(".tmp")
            kept_keys: set[str] = set()
            new_entries: list[dict] = []

            with open(partition_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry["timestamp"] > threshold:
                            if entry["key"] not in kept_keys:
                                new_entries.append(entry)
                                kept_keys.add(entry["key"])
                    except json.JSONDecodeError:
                        continue

            if new_entries:
                with open(temp_path, "w") as f:
                    for entry in new_entries:
                        f.write(json.dumps(entry) + "\n")
                temp_path.replace(partition_path)
            else:
                partition_path.unlink()

            logger.info(f"Compacted {partition_path}: removed old entries")

        except Exception as e:
            logger.error(f"Partition compaction error: {e}")

    async def load_entry(self, key: str) -> Optional[CacheEntry]:
        """Load an entry from persistent store.

        Args:
            key: Cache key

        Returns:
            CacheEntry or None
        """
        if key not in self._index:
            return None

        index_entry = self._index[key]
        partition = index_entry["partition"]
        partition_path = self._get_partition_path(partition)

        if not partition_path.exists():
            return None

        try:
            with open(partition_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry["key"] == key and entry["op"] == "SET":
                            return self._entry_to_cache_entry(entry)
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Failed to load entry {key}: {e}")

        return None

    def _entry_to_cache_entry(self, entry: dict) -> CacheEntry:
        """Convert log entry to CacheEntry."""
        metadata = entry.get("metadata", {})
        return CacheEntry(
            key=entry["key"],
            value=entry["value"],
            state=KeyState[metadata.get("state", "FRESH")],
            created_at=entry["timestamp"],
            expires_at=metadata.get("expires_at"),
            metadata=metadata,
        )

    async def _load_index(self) -> None:
        """Load index from disk."""
        index_file = self._index_path / "index.json"

        if index_file.exists():
            try:
                with open(index_file, "r") as f:
                    self._index = json.load(f)
                logger.info(f"Loaded index with {len(self._index)} entries")
            except Exception as e:
                logger.error(f"Failed to load index: {e}")

    async def _save_index(self) -> None:
        """Save index to disk."""
        index_file = self._index_path / "index.json"

        try:
            with open(index_file, "w") as f:
                json.dump(self._index, f)
        except Exception as e:
            logger.error(f"Failed to save index: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get persistence statistics."""
        return {
            "running": self._running,
            "partitions": self._current_partition + 1,
            "current_log_size": self._current_log_size,
            "index_size": len(self._index),
            "queue_size": self._write_queue.qsize(),
        }
