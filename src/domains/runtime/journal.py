"""Event Journal - Phase 15 stub."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PartitionStrategy(Enum):
    """Partition strategy for event journal."""
    TIME_BASED = "time_based"
    SIZE_BASED = "size_based"
    COUNT_BASED = "count_based"


@dataclass
class JournalEntry:
    """Event journal entry."""
    timestamp: datetime
    event_type: str
    data: dict[str, Any]
    sequence: int = 0


@dataclass
class JournalPartition:
    """Event journal partition."""
    id: str
    path: str
    start_time: datetime
    end_time: datetime | None = None
    entry_count: int = 0


class EventJournal:
    """Stub EventJournal for Phase 15."""

    def __init__(self, path: str | None = None):
        self._path = path
        self._entries: list[JournalEntry] = []
        self._partitions: list[JournalPartition] = []

    async def append(self, event_type: str, data: dict[str, Any]) -> JournalEntry:
        entry = JournalEntry(
            timestamp=datetime.now(),
            event_type=event_type,
            data=data,
            sequence=len(self._entries),
        )
        self._entries.append(entry)
        return entry

    async def replay(
        self,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
    ) -> list[JournalEntry]:
        return [e for e in self._entries if e.sequence >= from_sequence]

    async def get_partition(self, partition_id: str) -> JournalPartition | None:
        for p in self._partitions:
            if p.id == partition_id:
                return p
        return None
