"""
Replayer module - backward-compatible re-exports.

This module re-exports EventReplayer and related classes from the canonical
source at src.core.runtime.replayer.

Do not add new functionality here. All event replay logic lives in
src.core.runtime.replayer.
"""

from src.core.runtime.replayer import (
    EventReplayer,
    ReplayFilter,
    ReplayResult,
    ReplayDiff,
    ReplayTracer,
    compute_replay_diff,
)

__all__ = [
    "EventReplayer",
    "ReplayFilter",
    "ReplayResult",
    "ReplayDiff",
    "ReplayTracer",
    "compute_replay_diff",
]
