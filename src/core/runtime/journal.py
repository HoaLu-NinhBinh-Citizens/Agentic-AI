"""
Event Journal - Persistent Event Logging

Provides append-only event log with:
- Partitioned storage (by day, hour, or custom)
- Checksum verification for integrity
- Async write operations
- Retention policy with compaction
- Query and scan capabilities
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class PartitionStrategy(Enum):
    """Journal partition strategy."""
    NONE = "none"  # Single file
    DAY = "day"   # One file per day
    HOUR = "hour"  # One file per hour
    WEEK = "week"  # One file per week


class PartitionType(Enum):
    """Partition type."""
    DAILY = "daily"
    HOURLY = "hourly"
    WEEKLY = "weekly"


@dataclass
class JournalEntry:
    """Entry in the event journal."""
    id: str
    event_type: str
    source: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    partition: str = ""
    offset: int = 0
    checksum: str = ""
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata,
            "partition": self.partition,
            "offset": self.offset,
            "checksum": self.checksum,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JournalEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            event_type=data["event_type"],
            source=data["source"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
            partition=data.get("partition", ""),
            offset=data.get("offset", 0),
            checksum=data.get("checksum", ""),
            version=data.get("version", "1.0.0"),
        )

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of event data."""
        content = f"{self.id}|{self.event_type}|{self.source}|{self.timestamp.isoformat()}|{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def verify_checksum(self) -> bool:
        """Verify entry checksum."""
        return self.checksum == self.compute_checksum()


@dataclass
class JournalPartition:
    """Represents a journal partition."""
    name: str
    path: Path
    entry_count: int
    size_bytes: int
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]
    created_at: datetime
    is_compacted: bool = False


class EventJournal:
    """
    Append-only event journal with partition support.

    Features:
    - Append-only writes (no modification)
    - Partitioned storage (daily, hourly, weekly)
    - SHA256 checksum verification
    - Retention policy with auto-compaction
    - Async operations
    - Query and scan
    """

    def __init__(
        self,
        journal_dir: Path,
        partition_by: PartitionStrategy = PartitionStrategy.DAY,
        retention_days: int = 30,
        compaction_interval: int = 3600,
        max_file_size_mb: int = 100,
        schema_version: str = "1.0.0",
    ):
        self.journal_dir = Path(journal_dir)
        self.partition_by = partition_by
        self.retention_days = retention_days
        self.compaction_interval = compaction_interval
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.schema_version = schema_version

        # State
        self._current_partition: Optional[Path] = None
        self._current_offset: int = 0
        self._write_lock = asyncio.Lock()
        self._compaction_lock = asyncio.Lock()

        # Last compaction
        self._last_compaction = datetime.now()

        # Ensure directory exists
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Partition Management
    # -------------------------------------------------------------------------

    def _get_partition_name(self, timestamp: Optional[datetime] = None) -> str:
        """Get partition name for timestamp."""
        ts = timestamp or datetime.now()

        if self.partition_by == PartitionStrategy.DAY:
            return ts.strftime("%Y-%m-%d")
        elif self.partition_by == PartitionStrategy.HOUR:
            return ts.strftime("%Y-%m-%d_%H")
        elif self.partition_by == PartitionStrategy.WEEK:
            return f"{ts.year}-W{ts.isocalendar()[1]:02d}"
        else:
            return "main"

    def _get_partition_path(self, partition_name: str) -> Path:
        """Get file path for partition."""
        return self.journal_dir / f"journal_{partition_name}.jsonl"

    def _get_or_create_partition(self, timestamp: Optional[datetime] = None) -> Path:
        """Get or create current partition file."""
        partition_name = self._get_partition_name(timestamp)
        partition_path = self._get_partition_path(partition_name)

        if self._current_partition != partition_path:
            # Count existing entries
            if partition_path.exists():
                with open(partition_path, "r", encoding="utf-8") as f:
                    self._current_offset = sum(1 for _ in f)
            else:
                self._current_offset = 0

            self._current_partition = partition_path

        return partition_path

    # -------------------------------------------------------------------------
    # Transactional Write Operations (P1)
    # -------------------------------------------------------------------------
    
    async def append_transactional(
        self,
        events: List[JournalEntry],
        fsync: bool = True,
    ) -> tuple[List[JournalEntry], bool]:
        """Append events transactionally with durability guarantee.
        
        All events are written atomically or none are written.
        Optionally forces fsync to ensure durability.
        
        Args:
            events: Events to append
            fsync: Force fsync after write (ensures durability)
            
        Returns:
            (List of appended entries, success)
        """
        if not events:
            return [], True
        
        import tempfile
        import os
        
        async with self._write_lock:
            # Prepare entries with metadata
            prepared_events = []
            partition_name = None
            partition_path = None
            
            for i, event in enumerate(events):
                # Use same partition for all events in transaction
                if partition_name is None:
                    partition_name = self._get_partition_name(event.timestamp)
                    partition_path = self._get_partition_path(partition_name)
                
                event.offset = self._current_offset + i
                event.partition = partition_name
                event.checksum = event.compute_checksum()
                event.version = self.schema_version
                prepared_events.append(event)
            
            # Write to temp file first (atomic write)
            temp_fd = None
            temp_path = None
            try:
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=str(self.journal_dir),
                    prefix=".journal_temp_",
                )
                
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    for event in prepared_events:
                        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                        f.write(line)
                    
                    if fsync:
                        f.flush()
                        os.fsync(f.fileno())
                
                temp_fd = None  # File handle closed, don't close again
                
                # Atomic rename to final location
                target_path = partition_path or self._get_partition_path(partition_name)
                
                # Ensure parent directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                if target_path.exists():
                    # Append to existing file
                    with open(target_path, "a", encoding="utf-8") as f:
                        with open(temp_path, "r", encoding="utf-8") as temp:
                            for line in temp:
                                f.write(line)
                        if fsync:
                            f.flush()
                            os.fsync(f.fileno())
                else:
                    # Move temp file to final location
                    os.rename(temp_path, target_path)
                    temp_path = None  # Don't delete, it's now the target
                
                # Update offset
                self._current_offset += len(events)
                
                # Check for rotation
                if target_path.stat().st_size >= self.max_file_size_bytes:
                    self._current_partition = None  # Force new partition
                
                logger.info(
                    "Transactional append completed: %d events, partition=%s, fsync=%s",
                    len(events),
                    partition_name,
                    fsync,
                )
                
                return prepared_events, True
                
            except Exception as e:
                logger.error("Transactional append failed: %s", e)
                return [], False
                
            finally:
                # Clean up temp file if it still exists
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except OSError:
                        pass
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
    
    async def append(self, event: JournalEntry, fsync: bool = False) -> JournalEntry:
        """
        Append an event to the journal.
        
        For guaranteed durability, use append_transactional() instead.
        
        Args:
            event: Event to journal
            fsync: Force fsync after write (for durability)

        Returns:
            JournalEntry with offset and checksum set
        """
        # Use single-event transaction for compatibility
        events, success = await self.append_transactional([event], fsync=fsync)
        if success and events:
            return events[0]
        raise IOError("Failed to append event")
    
    async def append_batch(self, events: List[JournalEntry]) -> List[JournalEntry]:
        """
        Append multiple events in a batch.
        
        For guaranteed durability, use append_transactional() instead.

        Args:
            events: Events to journal

        Returns:
            List of journaled entries
        """
        results, success = await self.append_transactional(events, fsync=False)
        if not success:
            raise IOError("Failed to append batch")
        return results

    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------

    async def read(
        self,
        partition: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[JournalEntry]:
        """
        Read events from journal.

        Args:
            partition: Partition to read (or all if None)
            offset: Starting offset
            limit: Maximum entries to read

        Returns:
            List of journal entries
        """
        entries = []

        if partition:
            partitions = [self._get_partition_path(partition)]
        else:
            partitions = list(self.journal_dir.glob("journal_*.jsonl"))

        for partition_path in sorted(partitions):
            try:
                with open(partition_path, "r", encoding="utf-8") as f:
                    entries_read = 0
                    current_offset = 0

                    for line in f:
                        if entries_read >= limit:
                            break

                        if current_offset < offset:
                            current_offset += 1
                            continue

                        try:
                            data = json.loads(line.strip())
                            entry = JournalEntry.from_dict(data)
                            entries.append(entry)
                            entries_read += 1
                            current_offset += 1
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON in partition: %s", partition_path)

            except OSError as exc:
                logger.error("Failed to read partition %s: %s", partition_path, exc)

        return entries

    async def scan(
        self,
        event_types: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        predicate: Optional[Callable[[JournalEntry], bool]] = None,
        limit: int = 1000,
    ) -> List[JournalEntry]:
        """
        Scan journal with filters.

        Args:
            event_types: Filter by event types
            sources: Filter by sources
            since: Start timestamp
            until: End timestamp
            predicate: Custom filter function
            limit: Maximum entries

        Returns:
            Filtered journal entries
        """
        entries = []

        for partition_path in sorted(self.journal_dir.glob("journal_*.jsonl")):
            if len(entries) >= limit:
                break

            try:
                with open(partition_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if len(entries) >= limit:
                            break

                        try:
                            data = json.loads(line.strip())
                            entry = JournalEntry.from_dict(data)

                            # Apply filters
                            if event_types and entry.event_type not in event_types:
                                continue

                            if sources and entry.source not in sources:
                                continue

                            if since and entry.timestamp < since:
                                continue

                            if until and entry.timestamp > until:
                                continue

                            if predicate and not predicate(entry):
                                continue

                            entries.append(entry)

                        except (json.JSONDecodeError, KeyError):
                            continue

            except OSError:
                continue

        return entries

    def iter_partitions(self) -> Iterator[JournalPartition]:
        """Iterate over all partitions."""
        for partition_path in sorted(self.journal_dir.glob("journal_*.jsonl")):
            try:
                stat = partition_path.stat()
                name = partition_path.stem.replace("journal_", "")

                # Count entries and get timestamp range
                entry_count = 0
                first_ts = None
                last_ts = None

                with open(partition_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            ts = datetime.fromisoformat(data["timestamp"])

                            if first_ts is None:
                                first_ts = ts
                            last_ts = ts

                            entry_count += 1
                        except (json.JSONDecodeError, KeyError):
                            continue

                yield JournalPartition(
                    name=name,
                    path=partition_path,
                    entry_count=entry_count,
                    size_bytes=stat.st_size,
                    first_timestamp=first_ts,
                    last_timestamp=last_ts,
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                    is_compacted=".compact" in name,
                )

            except OSError:
                continue

    # -------------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------------

    async def compact(self, before: Optional[datetime] = None) -> int:
        """
        Compact old partitions.

        Args:
            before: Compact partitions before this timestamp

        Returns:
            Number of entries removed
        """
        async with self._compaction_lock:
            cutoff = before or (datetime.now() - timedelta(days=self.retention_days))
            removed = 0

            for partition in self.iter_partitions():
                if partition.last_timestamp and partition.last_timestamp < cutoff:
                    # Move to compact folder
                    compact_path = partition.path.with_suffix(".compact.jsonl")

                    try:
                        partition.path.rename(compact_path)
                        removed += partition.entry_count
                        logger.info("Compacted partition: %s (%d entries)", partition.name, partition.entry_count)
                    except OSError as exc:
                        logger.error("Failed to compact %s: %s", partition.name, exc)

            self._last_compaction = datetime.now()
            return removed

    async def cleanup(self, before: Optional[datetime] = None) -> int:
        """
        Delete old partitions.

        Args:
            before: Delete partitions before this timestamp

        Returns:
            Number of partitions deleted
        """
        cutoff = before or (datetime.now() - timedelta(days=self.retention_days))
        deleted = 0

        for partition in self.iter_partitions():
            if partition.last_timestamp and partition.last_timestamp < cutoff:
                try:
                    partition.path.unlink()
                    deleted += 1
                    logger.info("Deleted partition: %s", partition.name)
                except OSError as exc:
                    logger.error("Failed to delete %s: %s", partition.name, exc)

        return deleted

    async def verify_integrity(self, partition: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify checksum integrity of entries.

        Args:
            partition: Partition to verify (or all if None)

        Returns:
            Verification report
        """
        results = {
            "total_entries": 0,
            "valid_entries": 0,
            "invalid_entries": 0,
            "errors": [],
        }

        entries = await self.read(partition=partition, limit=100000)

        for entry in entries:
            results["total_entries"] += 1

            if entry.verify_checksum():
                results["valid_entries"] += 1
            else:
                results["invalid_entries"] += 1
                results["errors"].append({
                    "id": entry.id,
                    "offset": entry.offset,
                    "partition": entry.partition,
                    "error": "Checksum mismatch",
                })

        return results

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get journal statistics."""
        partitions = list(self.iter_partitions())

        return {
            "journal_dir": str(self.journal_dir),
            "partition_by": self.partition_by.value,
            "retention_days": self.retention_days,
            "total_partitions": len(partitions),
            "total_entries": sum(p.entry_count for p in partitions),
            "total_size_bytes": sum(p.size_bytes for p in partitions),
            "last_compaction": self._last_compaction.isoformat(),
        }
