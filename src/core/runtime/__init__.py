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
from src.core.runtime.runtime_manager import RuntimeManager, StreamInfo

__all__ = [
    "RuntimeManager",
    "StreamInfo",
]


class _LazyLoader:
    """Lazy loading wrapper for Phase 15 modules."""

    _phase15_imports = {
        # Note: RuntimeController, EventJournal, EventReplayer live in src.core.runtime
        # (not src.domains.runtime) — those stubs were deleted as Phase 15 duplicates.
        # Keeping stub imports here would cause ImportError; the active implementations
        # in src/core/runtime/ are the authoritative sources.
        "DeadLetterQueue": ("src.domains.runtime.dlq", "DeadLetterQueue"),
        "DLQEntry": ("src.domains.runtime.dlq", "DLQEntry"),
        "DLQReason": ("src.domains.runtime.dlq", "DLQReason"),
        "DLQStatus": ("src.domains.runtime.dlq", "DLQStatus"),
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
# Note: RuntimeController, EventJournal, EventReplayer and related types
# live in src/core/runtime/*.py directly — not lazy-loaded from src.domains.runtime.
