"""
Dead Letter Queue - Failed Event Quarantine

Provides quarantine for failed events:
- Failed event storage with error details
- Retry tracking with max attempts
- Priority-based requeue
- Expiration policy
- Error categorization
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class DLQReason(Enum):
    """Reason for event going to DLQ."""
    HANDLER_ERROR = "handler_error"
    TIMEOUT = "timeout"
    VALIDATION_FAILED = "validation_failed"
    SECURITY_REJECTED = "security_rejected"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    UNKNOWN_ERROR = "unknown_error"


class DLQStatus(Enum):
    """Status of DLQ entry."""
    PENDING = "pending"
    RETRYING = "retrying"
    EXPIRED = "expired"
    DISCARDED = "discarded"
    REQUEUED = "requeued"


@dataclass
class DLQEntry:
    """
    Entry in the Dead Letter Queue.

    Attributes:
        id: Unique entry ID
        event_id: Original event ID
        event_type: Type of event
        source: Original source
        data: Event payload
        error: Error message
        error_type: Error class/type
        reason: Why it went to DLQ
        status: Current status
        attempts: Number of retry attempts
        max_attempts: Maximum allowed attempts
        first_failure: First failure timestamp
        last_failure: Most recent failure timestamp
        handler: Handler that failed
        stack_trace: Error stack trace
        priority: Retry priority (higher = retry first)
        expires_at: When this entry expires
    """
    id: str
    event_id: str
    event_type: str
    source: str
    data: Dict[str, Any]
    error: str
    error_type: str
    reason: DLQReason
    status: DLQStatus
    attempts: int
    max_attempts: int
    first_failure: datetime
    last_failure: datetime
    handler: str
    stack_trace: str
    priority: int = 0
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "reason": self.reason.value,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "first_failure": self.first_failure.isoformat(),
            "last_failure": self.last_failure.isoformat(),
            "handler": self.handler,
            "stack_trace": self.stack_trace,
            "priority": self.priority,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DLQEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            event_id=data["event_id"],
            event_type=data["event_type"],
            source=data["source"],
            data=data["data"],
            error=data["error"],
            error_type=data["error_type"],
            reason=DLQReason(data["reason"]),
            status=DLQStatus(data["status"]),
            attempts=data["attempts"],
            max_attempts=data["max_attempts"],
            first_failure=datetime.fromisoformat(data["first_failure"]),
            last_failure=datetime.fromisoformat(data["last_failure"]),
            handler=data["handler"],
            stack_trace=data["stack_trace"],
            priority=data.get("priority", 0),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            metadata=data.get("metadata", {}),
            version=data.get("version", "1.0.0"),
        )

    @property
    def can_retry(self) -> bool:
        """Check if entry can be retried."""
        return (
            self.attempts < self.max_attempts
            and self.status in [DLQStatus.PENDING, DLQStatus.RETRYING]
            and (self.expires_at is None or self.expires_at > datetime.now())
        )

    @property
    def should_retry(self) -> bool:
        """Check if should retry now based on backoff."""
        if not self.can_retry:
            return False
        # Exponential backoff: 2^attempts seconds
        backoff_seconds = min(2 ** self.attempts, 300)  # Max 5 minutes
        retry_after = self.last_failure + timedelta(seconds=backoff_seconds)
        return datetime.now() >= retry_after


class DeadLetterQueue:
    """
    Dead Letter Queue for failed events.

    Features:
    - Async operations
    - Retry with exponential backoff
    - Priority-based processing
    - Expiration policy
    - Error categorization
    - Export/import
    """

    def __init__(
        self,
        dlq_dir: Optional[Path] = None,
        max_attempts: int = 3,
        default_ttl_hours: int = 24,
        cleanup_interval: int = 300,
    ):
        self.dlq_dir = dlq_dir or Path("AI_support/data/dlq")
        self.max_attempts = max_attempts
        self.default_ttl = timedelta(hours=default_ttl_hours)
        self.cleanup_interval = cleanup_interval

        # State
        self._entries: Dict[str, DLQEntry] = {}
        self._lock = asyncio.Lock()
        self._retry_callbacks: List[Callable[[DLQEntry], bool]] = []

        # Ensure directory exists
        self.dlq_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Entry Management
    # -------------------------------------------------------------------------

    async def enqueue(
        self,
        event_id: str,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        error: str,
        error_type: str,
        reason: DLQReason,
        handler: str,
        stack_trace: str = "",
        priority: int = 0,
        max_attempts: Optional[int] = None,
        ttl_hours: Optional[int] = None,
    ) -> DLQEntry:
        """
        Add a failed event to the DLQ.

        Args:
            event_id: Original event ID
            event_type: Type of event
            source: Original source
            data: Event payload
            error: Error message
            error_type: Error class/type
            reason: Why it went to DLQ
            handler: Handler that failed
            stack_trace: Error stack trace
            priority: Retry priority
            max_attempts: Max retry attempts
            ttl_hours: Time to live in hours

        Returns:
            Created DLQEntry
        """
        async with self._lock:
            entry_id = str(uuid4())[:8]
            now = datetime.now()

            entry = DLQEntry(
                id=entry_id,
                event_id=event_id,
                event_type=event_type,
                source=source,
                data=data,
                error=error,
                error_type=error_type,
                reason=reason,
                status=DLQStatus.PENDING,
                attempts=0,
                max_attempts=max_attempts or self.max_attempts,
                first_failure=now,
                last_failure=now,
                handler=handler,
                stack_trace=stack_trace,
                priority=priority,
                expires_at=now + timedelta(hours=ttl_hours) if ttl_hours else now + self.default_ttl,
            )

            self._entries[entry_id] = entry
            await self._persist_entry(entry)

            logger.info(
                "DLQ: Added entry %s for event %s (reason: %s)",
                entry_id,
                event_id,
                reason.value,
            )

            return entry

    async def retry(self, entry_id: str) -> bool:
        """
        Retry a DLQ entry.

        Args:
            entry_id: DLQ entry ID

        Returns:
            True if retry was triggered
        """
        async with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                logger.warning("DLQ: Entry %s not found", entry_id)
                return False

            if not entry.can_retry:
                logger.info("DLQ: Entry %s cannot retry (attempts: %d/%d)", entry_id, entry.attempts, entry.max_attempts)
                return False

            # Update entry
            entry.attempts += 1
            entry.last_failure = datetime.now()
            entry.status = DLQStatus.RETRYING

            await self._persist_entry(entry)

            logger.info(
                "DLQ: Retry scheduled for entry %s (attempt %d/%d)",
                entry_id,
                entry.attempts,
                entry.max_attempts,
            )

            return True

    async def requeue(self, entry_id: str) -> bool:
        """
        Requeue an entry back to main processing.

        Args:
            entry_id: DLQ entry ID

        Returns:
            True if requeued successfully
        """
        async with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False

            # Mark as requeued
            entry.status = DLQStatus.REQUEUED
            await self._persist_entry(entry)

            # Remove from memory
            del self._entries[entry_id]

            logger.info("DLQ: Requeued entry %s", entry_id)
            return True

    async def discard(self, entry_id: str) -> bool:
        """
        Permanently discard a DLQ entry.

        Args:
            entry_id: DLQ entry ID

        Returns:
            True if discarded successfully
        """
        async with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False

            # Mark as discarded
            entry.status = DLQStatus.DISCARDED
            await self._persist_entry(entry)

            # Remove from memory
            del self._entries[entry_id]

            logger.info("DLQ: Discarded entry %s", entry_id)
            return True

    async def expire(self, entry_id: str) -> bool:
        """
        Mark an entry as expired.

        Args:
            entry_id: DLQ entry ID

        Returns:
            True if expired successfully
        """
        async with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False

            entry.status = DLQStatus.EXPIRED
            await self._persist_entry(entry)

            del self._entries[entry_id]

            logger.info("DLQ: Expired entry %s", entry_id)
            return True

    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------

    async def get(self, entry_id: str) -> Optional[DLQEntry]:
        """Get a DLQ entry by ID."""
        async with self._lock:
            return self._entries.get(entry_id)

    async def get_by_event_id(self, event_id: str) -> List[DLQEntry]:
        """Get all DLQ entries for an event."""
        async with self._lock:
            return [e for e in self._entries.values() if e.event_id == event_id]

    async def get_pending(self, limit: int = 100) -> List[DLQEntry]:
        """Get pending entries sorted by priority and age."""
        async with self._lock:
            pending = [
                e for e in self._entries.values()
                if e.status == DLQStatus.PENDING
            ]
            # Sort by priority (desc) then by first_failure (asc)
            pending.sort(key=lambda e: (-e.priority, e.first_failure))
            return pending[:limit]

    async def get_retryable(self, limit: int = 100) -> List[DLQEntry]:
        """Get entries ready for retry."""
        async with self._lock:
            retryable = [
                e for e in self._entries.values()
                if e.should_retry
            ]
            retryable.sort(key=lambda e: (-e.priority, e.first_failure))
            return retryable[:limit]

    async def get_expired(self) -> List[DLQEntry]:
        """Get expired entries."""
        async with self._lock:
            now = datetime.now()
            return [
                e for e in self._entries.values()
                if e.expires_at and e.expires_at < now
            ]

    async def get_by_reason(self, reason: DLQReason) -> List[DLQEntry]:
        """Get entries by failure reason."""
        async with self._lock:
            return [e for e in self._entries.values() if e.reason == reason]

    async def get_by_status(self, status: DLQStatus) -> List[DLQEntry]:
        """Get entries by status."""
        async with self._lock:
            return [e for e in self._entries.values() if e.status == status]

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics."""
        entries = list(self._entries.values())

        by_status: Dict[str, int] = {}
        by_reason: Dict[str, int] = {}
        total_attempts = 0

        for entry in entries:
            by_status[entry.status.value] = by_status.get(entry.status.value, 0) + 1
            by_reason[entry.reason.value] = by_reason.get(entry.reason.value, 0) + 1
            total_attempts += entry.attempts

        return {
            "total_entries": len(entries),
            "by_status": by_status,
            "by_reason": by_reason,
            "total_attempts": total_attempts,
            "avg_attempts": total_attempts / len(entries) if entries else 0,
            "pending": len([e for e in entries if e.status == DLQStatus.PENDING]),
            "retrying": len([e for e in entries if e.status == DLQStatus.RETRYING]),
            "expired": len([e for e in entries if e.status == DLQStatus.EXPIRED]),
        }

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    async def _persist_entry(self, entry: DLQEntry) -> None:
        """Persist entry to disk."""
        entry_file = self.dlq_dir / f"{entry.id}.json"
        with open(entry_file, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2, default=str)

    async def load_from_disk(self) -> int:
        """Load entries from disk."""
        count = 0
        for entry_file in self.dlq_dir.glob("*.json"):
            try:
                with open(entry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entry = DLQEntry.from_dict(data)
                    # Only load non-requeued/discarded entries
                    if entry.status not in [DLQStatus.REQUEUED, DLQStatus.DISCARDED]:
                        self._entries[entry.id] = entry
                        count += 1
            except Exception as exc:
                logger.error("Failed to load DLQ entry %s: %s", entry_file, exc)
        return count

    # -------------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------------

    async def cleanup(self) -> int:
        """
        Cleanup expired entries.

        Returns:
            Number of entries cleaned up
        """
        async with self._lock:
            now = datetime.now()
            to_cleanup = [
                entry_id
                for entry_id, entry in self._entries.items()
                if entry.expires_at and entry.expires_at < now
            ]

            for entry_id in to_cleanup:
                await self.expire(entry_id)

            return len(to_cleanup)

    async def export(self, filepath: Path) -> bool:
        """
        Export DLQ entries to file.

        Args:
            filepath: Output file path

        Returns:
            True if successful
        """
        async with self._lock:
            entries = list(self._entries.values())
            data = [e.to_dict() for e in entries]

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
                logger.info("DLQ: Exported %d entries to %s", len(entries), filepath)
                return True
            except Exception as exc:
                logger.error("DLQ: Export failed: %s", exc)
                return False

    async def import_entries(self, filepath: Path) -> int:
        """
        Import DLQ entries from file.

        Args:
            filepath: Input file path

        Returns:
            Number of entries imported
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            count = 0
            async with self._lock:
                for entry_data in data:
                    entry = DLQEntry.from_dict(entry_data)
                    self._entries[entry.id] = entry
                    await self._persist_entry(entry)
                    count += 1

            logger.info("DLQ: Imported %d entries from %s", count, filepath)
            return count

        except Exception as exc:
            logger.error("DLQ: Import failed: %s", exc)
            return 0
