"""Dead Letter Queue - Phase 15 stub."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DLQReason(Enum):
    """Dead letter queue entry reason."""
    PROCESSING_ERROR = "processing_error"
    TIMEOUT = "timeout"
    INVALID_MESSAGE = "invalid_message"
    CIRCUIT_OPEN = "circuit_open"


class DLQStatus(Enum):
    """Dead letter queue entry status."""
    PENDING = "pending"
    RETRYING = "retrying"
    DEAD = "dead"
    DISCARDED = "discarded"


@dataclass
class DLQEntry:
    """Dead letter queue entry."""
    id: str
    reason: DLQReason
    status: DLQStatus
    message: dict[str, Any]
    created_at: datetime
    retry_count: int = 0
    last_error: str | None = None


class DeadLetterQueue:
    """Stub DeadLetterQueue for Phase 15."""

    def __init__(self):
        self._entries: list[DLQEntry] = []

    async def enqueue(
        self,
        reason: DLQReason,
        message: dict[str, Any],
    ) -> DLQEntry:
        entry = DLQEntry(
            id=f"dlq-{len(self._entries)}",
            reason=reason,
            status=DLQStatus.PENDING,
            message=message,
            created_at=datetime.now(),
        )
        self._entries.append(entry)
        return entry

    async def dequeue(self) -> DLQEntry | None:
        for entry in self._entries:
            if entry.status == DLQStatus.PENDING:
                return entry
        return None

    async def get_pending(self) -> list[DLQEntry]:
        return [e for e in self._entries if e.status == DLQStatus.PENDING]
