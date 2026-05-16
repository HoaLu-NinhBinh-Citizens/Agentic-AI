"""Event Replayer - Phase 15 stub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class ReplayFilter(Enum):
    """Replay filter types."""
    ALL = "all"
    FROM_TIMESTAMP = "from_timestamp"
    BY_TYPE = "by_type"
    SEQUENCE_RANGE = "sequence_range"


@dataclass
class ReplayResult:
    """Replay operation result."""
    success: bool
    entries_replayed: int
    errors: list[str]
    start_time: datetime
    end_time: datetime


class EventReplayer:
    """Stub EventReplayer for Phase 15."""

    def __init__(self):
        self._replays: list[ReplayResult] = []

    async def replay(
        self,
        journal: Any,
        handler: Callable,
        filter_type: ReplayFilter = ReplayFilter.ALL,
        **kwargs,
    ) -> ReplayResult:
        start = datetime.now()
        result = ReplayResult(
            success=True,
            entries_replayed=0,
            errors=[],
            start_time=start,
            end_time=datetime.now(),
        )
        self._replays.append(result)
        return result

    async def validate(self, journal: Any) -> bool:
        return True
