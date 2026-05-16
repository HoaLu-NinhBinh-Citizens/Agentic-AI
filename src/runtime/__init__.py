"""Runtime module stub.

This module provides backward compatibility for tests importing from src.runtime.
Redirects to core.runtime for Phase 1B+ components.
Phase 15 components are lazy-loaded on demand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Phase 1B components - directly imported
from core.runtime.runtime_manager import RuntimeManager, StreamInfo

__all__ = [
    "RuntimeManager",
    "StreamInfo",
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
    "ReplayResult",
    "ReplayFilter",
    "TaskScheduler",
    "Priority",
    "ScheduledTask",
    "QueueFullError",
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
]


class _LazyLoader:
    """Lazy loading for Phase 15 components."""

    _phase15 = {
        "RuntimeController": ("src.domains.runtime.controller", "RuntimeController"),
        "RuntimeState": ("src.domains.runtime.controller", "RuntimeState"),
        "LifecycleEvent": ("src.domains.runtime.controller", "LifecycleEvent"),
        "EventJournal": ("src.domains.runtime.journal", "EventJournal"),
        "JournalEntry": ("src.domains.runtime.journal", "JournalEntry"),
        "JournalPartition": ("src.domains.runtime.journal", "JournalPartition"),
        "PartitionStrategy": ("src.domains.runtime.journal", "PartitionStrategy"),
        "DeadLetterQueue": ("src.domains.runtime.dlq", "DeadLetterQueue"),
        "DLQEntry": ("src.domains.runtime.dlq", "DLQEntry"),
        "DLQReason": ("src.domains.runtime.dlq", "DLQReason"),
        "DLQStatus": ("src.domains.runtime.dlq", "DLQStatus"),
        "EventReplayer": ("src.domains.runtime.replayer", "EventReplayer"),
        "ReplayResult": ("src.domains.runtime.replayer", "ReplayResult"),
        "ReplayFilter": ("src.domains.runtime.replayer", "ReplayFilter"),
        "TaskScheduler": ("src.core.scheduler", "TaskScheduler"),
        "Priority": ("src.core.scheduler", "Priority"),
        "ScheduledTask": ("src.core.scheduler", "ScheduledTask"),
        "QueueFullError": ("src.core.scheduler", "QueueFullError"),
        "CircuitBreaker": ("src.domains.runtime.circuit_breaker", "CircuitBreaker"),
        "CircuitState": ("src.domains.runtime.circuit_breaker", "CircuitState"),
        "CircuitOpenError": ("src.domains.runtime.circuit_breaker", "CircuitOpenError"),
    }

    def __getattr__(self, name):
        if name in self._phase15:
            import importlib
            mod_path, class_name = self._phase15[name]
            try:
                mod = importlib.import_module(mod_path)
                return getattr(mod, class_name)
            except ImportError as e:
                raise AttributeError(
                    f"Cannot load Phase 15 component '{name}': {e}"
                )
        raise AttributeError(f"module 'src.runtime' has no attribute '{name}'")


_loader = _LazyLoader()


def __getattr__(name):
    return _loader.__getattr__(name)
