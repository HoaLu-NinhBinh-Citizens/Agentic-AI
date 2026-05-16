"""Runtime module for Phase 1B and Phase 15.

Phase 1B provides:
- RuntimeManager: Stream cancellation and timeout support

Phase 15 components are available via lazy import.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Phase 1B Runtime Manager
from core.runtime.runtime_manager import RuntimeManager, StreamInfo

__all__ = [
    "RuntimeManager",
    "StreamInfo",
]


class _LazyLoader:
    """Lazy loading wrapper for Phase 15 modules."""

    _phase15_imports = {
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
        "CircuitBreaker": ("src.domains.runtime.circuit_breaker", "CircuitBreaker"),
    }

    def __getattr__(self, name: str):
        if name in self._phase15_imports:
            import importlib
            module_path, class_name = self._phase15_imports[name]
            try:
                mod = importlib.import_module(module_path)
                return getattr(mod, class_name)
            except ImportError:
                raise AttributeError(
                    f"Phase 15 module not available: {module_path}. "
                    f"Install required dependencies for Phase 15 features."
                )
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_lazy_loader = _LazyLoader()


def __getattr__(name: str):
    """Lazy load Phase 15 components."""
    return _lazy_loader.__getattr__(name)


# Also expose under core.runtime namespace for backward compatibility
sys.modules['core.runtime'].RuntimeController = property(
    lambda self: _lazy_loader.__getattr__("RuntimeController")
)
sys.modules['core.runtime'].RuntimeState = property(
    lambda self: _lazy_loader.__getattr__("RuntimeState")
)
sys.modules['core.runtime'].LifecycleEvent = property(
    lambda self: _lazy_loader.__getattr__("LifecycleEvent")
)
sys.modules['core.runtime'].EventJournal = property(
    lambda self: _lazy_loader.__getattr__("EventJournal")
)
sys.modules['core.runtime'].DeadLetterQueue = property(
    lambda self: _lazy_loader.__getattr__("DeadLetterQueue")
)
sys.modules['core.runtime'].EventReplayer = property(
    lambda self: _lazy_loader.__getattr__("EventReplayer")
)
sys.modules['core.runtime'].TaskScheduler = property(
    lambda self: _lazy_loader.__getattr__("TaskScheduler")
)
sys.modules['core.runtime'].CircuitBreaker = property(
    lambda self: _lazy_loader.__getattr__("CircuitBreaker")
)
