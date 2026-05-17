"""Exactly-once processor for frequency updates.

Ensures frequency updates are applied exactly once using idempotency keys.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.types import Feedback

logger = logging.getLogger(__name__)


class ExactlyOnceProcessor:
    """
    Ensures frequency updates are applied exactly once.
    
    Uses idempotency keys + applied_keys table to guarantee:
    - Each feedback is processed only once
    - Crash recovery doesn't cause duplicates
    - Safe for concurrent processing
    """

    def __init__(self, storage: FrequencyStorage):
        self._storage = storage
        self._lock = asyncio.Lock()

    async def process_feedback(self, feedback: Feedback) -> bool:
        """
        Process feedback with exactly-once guarantee.
        
        Args:
            feedback: Feedback to process
            
        Returns:
            True if processed (new feedback)
            False if already processed (idempotent)
        """
        async with self._lock:
            idempotency_key = self._generate_idempotency_key(feedback)

            if await self._is_already_processed(idempotency_key):
                logger.debug(f"Feedback already processed: {idempotency_key[:16]}...")
                return False

            await self._write_to_wal(feedback, idempotency_key)

            inserted = await self._insert_applied_key_atomic(idempotency_key)
            if not inserted:
                return False

            try:
                await self._update_frequency(feedback)
                await self._increment_frequency_version()
                return True
            except Exception as e:
                await self._rollback_applied_key(idempotency_key)
                raise

    def _generate_idempotency_key(self, feedback: Feedback) -> str:
        """
        Generate deterministic idempotency key from feedback.
        
        Same feedback components = same key (within same day).
        """
        day_bucket = int(feedback.timestamp / 86400) * 86400
        payload = f"{feedback.query}|{feedback.intent_path}|{feedback.example_text}|{day_bucket}"
        return hashlib.sha256(payload.encode()).hexdigest()

    async def _is_already_processed(self, key: str) -> bool:
        """Check if key already processed."""
        return await self._storage.key_exists(key)

    async def _insert_applied_key_atomic(self, key: str) -> bool:
        """
        Atomic insert with conflict detection.
        
        Returns:
            True if inserted (new key)
            False if already exists
        """
        return await self._storage.insert_applied_key(key)

    async def _write_to_wal(self, feedback: Feedback, idempotency_key: str) -> None:
        """Write event to WAL for audit/replay."""
        await self._storage.write_wal_event(
            event_id=_generate_event_id(),
            intent_path=feedback.intent_path,
            example_text=feedback.example_text,
            idempotency_key=idempotency_key,
            timestamp=feedback.timestamp,
        )

    async def _update_frequency(self, feedback: Feedback) -> None:
        """Update example frequency."""
        example_hash = hashlib.sha256(feedback.example_text.encode()).hexdigest()
        await self._storage.update_frequency(
            intent_path=feedback.intent_path,
            example_hash=example_hash,
        )

    async def _increment_frequency_version(self) -> None:
        """Increment global frequency version."""
        await self._storage.increment_frequency_version()

    async def _rollback_applied_key(self, key: str) -> None:
        """Rollback applied key on failure."""
        await self._storage.delete_applied_key(key)


class FrequencyStorage:
    """
    Storage interface for frequency data.
    
    Implement this to integrate with your database.
    """

    async def key_exists(self, key: str) -> bool:
        """Check if idempotency key exists."""
        raise NotImplementedError

    async def insert_applied_key(self, key: str) -> bool:
        """
        Insert applied key atomically.
        
        Returns:
            True if inserted
            False if already exists
        """
        raise NotImplementedError

    async def delete_applied_key(self, key: str) -> None:
        """Delete applied key (for rollback)."""
        raise NotImplementedError

    async def write_wal_event(
        self,
        event_id: str,
        intent_path: str,
        example_text: str,
        idempotency_key: str,
        timestamp: float,
    ) -> None:
        """Write event to WAL."""
        raise NotImplementedError

    async def update_frequency(
        self,
        intent_path: str,
        example_hash: str,
    ) -> None:
        """Update frequency count."""
        raise NotImplementedError

    async def increment_frequency_version(self) -> None:
        """Increment global frequency version."""
        raise NotImplementedError


class InMemoryFrequencyStorage(FrequencyStorage):
    """In-memory implementation for testing."""

    def __init__(self):
        self._applied_keys: set[str] = set()
        self._frequencies: dict[tuple[str, str], int] = {}
        self._frequency_version: int = 1
        self._wal: list[dict] = []
        self._lock = asyncio.Lock()

    async def key_exists(self, key: str) -> bool:
        async with self._lock:
            return key in self._applied_keys

    async def insert_applied_key(self, key: str) -> bool:
        async with self._lock:
            if key in self._applied_keys:
                return False
            self._applied_keys.add(key)
            return True

    async def delete_applied_key(self, key: str) -> None:
        async with self._lock:
            self._applied_keys.discard(key)

    async def write_wal_event(
        self,
        event_id: str,
        intent_path: str,
        example_text: str,
        idempotency_key: str,
        timestamp: float,
    ) -> None:
        async with self._lock:
            self._wal.append({
                "event_id": event_id,
                "intent_path": intent_path,
                "example_text": example_text,
                "idempotency_key": idempotency_key,
                "timestamp": timestamp,
                "processed": True,
            })

    async def update_frequency(
        self,
        intent_path: str,
        example_hash: str,
    ) -> None:
        async with self._lock:
            key = (intent_path, example_hash)
            self._frequencies[key] = self._frequencies.get(key, 0) + 1

    async def increment_frequency_version(self) -> None:
        async with self._lock:
            self._frequency_version += 1

    async def get_frequency(self, intent_path: str) -> dict[str, int]:
        async with self._lock:
            return {
                h: f
                for (ip, h), f in self._frequencies.items()
                if ip == intent_path
            }


def _generate_event_id() -> str:
    """Generate unique event ID."""
    import uuid
    return f"evt_{uuid.uuid4().hex[:16]}"
