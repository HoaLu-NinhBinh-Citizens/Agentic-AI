"""Journal module - backward-compatible re-exports.

This module re-exports EventJournal and related classes from the canonical
source at src.core.runtime.journal.

Do not add new functionality here. All event journal logic lives in
src.core.runtime.journal.
"""

from src.core.runtime.journal import (
    EventJournal,
    JournalEntry,
    JournalPartition,
    PartitionStrategy,
)

__all__ = [
    "EventJournal",
    "JournalEntry",
    "JournalPartition",
    "PartitionStrategy",
]
