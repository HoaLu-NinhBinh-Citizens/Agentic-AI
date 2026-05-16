"""Idempotency support for Phase 2C.

Provides in-memory storage for idempotent retry support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IdempotencyRecord:
    """Record of a successful execution result for idempotency."""

    result: dict[str, Any]
    timestamp: float


class IdempotencyStore(ABC):
    """Abstract interface for idempotency storage.

    Phase 2C provides InMemoryIdempotencyStore.
    Future phases can implement RedisIdempotencyStore, etc.
    """

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """Get cached result by idempotency key.

        Args:
            key: The idempotency key.

        Returns:
            Cached result dict if found, None otherwise.
        """
        ...

    @abstractmethod
    async def set(self, key: str, result: dict[str, Any]) -> None:
        """Store successful result by idempotency key.

        Args:
            key: The idempotency key.
            result: The successful result to cache.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached result.

        Args:
            key: The idempotency key.
        """
        ...

    @abstractmethod
    async def clear_expired(self) -> int:
        """Clear expired entries.

        Returns:
            Number of entries cleared.
        """
        ...


class InMemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency store with TTL support.

    Phase 2C implementation. State is lost on restart.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        """Initialize the store.

        Args:
            ttl_seconds: Time-to-live for cached entries in seconds.
        """
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._records: dict[str, IdempotencyRecord] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get cached result by idempotency key.

        Args:
            key: The idempotency key.

        Returns:
            Cached result dict if found and not expired, None otherwise.
        """
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                return None

            if time.monotonic() - record.timestamp > self._ttl:
                del self._records[key]
                return None

            logger.debug(
                "Idempotency cache hit: key=%s",
                key,
            )
            return record.result

    async def set(self, key: str, result: dict[str, Any]) -> None:
        """Store successful result by idempotency key.

        Args:
            key: The idempotency key.
            result: The successful result to cache.
        """
        async with self._lock:
            self._records[key] = IdempotencyRecord(
                result=result,
                timestamp=time.monotonic(),
            )
            logger.debug(
                "Stored idempotency record: key=%s",
                key,
            )

    async def delete(self, key: str) -> None:
        """Delete cached result.

        Args:
            key: The idempotency key.
        """
        async with self._lock:
            self._records.pop(key, None)
            logger.debug(
                "Deleted idempotency record: key=%s",
                key,
            )

    async def clear_expired(self) -> int:
        """Clear expired entries.

        Returns:
            Number of entries cleared.
        """
        async with self._lock:
            now = time.monotonic()
            expired_keys = [
                key
                for key, record in self._records.items()
                if now - record.timestamp > self._ttl
            ]
            for key in expired_keys:
                del self._records[key]

            if expired_keys:
                logger.debug(
                    "Cleared %d expired idempotency records",
                    len(expired_keys),
                )

            return len(expired_keys)

    async def size(self) -> int:
        """Get the number of cached entries.

        Returns:
            Number of entries in cache.
        """
        async with self._lock:
            return len(self._records)

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._records.clear()
            logger.debug("Cleared all idempotency records")
