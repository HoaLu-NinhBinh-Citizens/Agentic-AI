"""Legacy alias for src.runtime module.

Provides backward-compatible imports from src.core.runtime.
Components now live in src.core.runtime; this module provides aliases.
"""

from src.core.runtime import RuntimeManager

# RuntimeController + LifecycleEvent + RuntimeState from controller.py
from src.core.runtime.controller import (
    RuntimeController,
    RuntimeState,
    LifecycleEvent,
)

# EventJournal + JournalEntry + JournalPartition + PartitionStrategy from journal.py
from src.core.runtime.journal import (
    EventJournal,
    JournalEntry,
    JournalPartition,
    PartitionStrategy,
)

# DeadLetterQueue + DLQEntry + DLQReason + DLQStatus from dlq.py
from src.core.runtime.dlq import (
    DeadLetterQueue,
    DLQEntry,
    DLQReason,
    DLQStatus,
)

# EventReplayer + ReplayFilter + ReplayResult from replayer.py
from src.core.runtime.replayer import (
    EventReplayer,
    ReplayFilter,
    ReplayResult,
)

__all__ = [
    "RuntimeManager",
    "RuntimeController",
    "RuntimeState",
    "LifecycleEvent",
    "EventJournal",
    "JournalEntry",
    "JournalPartition",
    "PartitionStrategy",
    "DeadLetterQueue",
    "DLQEntry",
    "DLQReason",
    "DLQStatus",
    "EventReplayer",
    "ReplayFilter",
    "ReplayResult",
]
