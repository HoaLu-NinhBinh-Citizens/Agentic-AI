"""Rate limiting infrastructure for Phase 2C.

Provides rate limit storage abstraction for future persistence support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    """State of rate limiter for a given key."""

    timestamps: list[float] = field(default_factory=list)


class RateLimitStore(ABC):
    """Abstract interface for rate limit storage.

    Phase 2C provides InMemoryRateLimitStore.
    Future phases can implement RedisRateLimitStore for persistence.
    """

    @abstractmethod
    async def get_timestamps(self, key: str) -> list[float]:
        """Get all timestamps for a rate limit key.

        Args:
            key: The rate limit key (e.g., "session:xxx" or "tool:xxx").

        Returns:
            List of timestamps in seconds since epoch.
        """
        ...

    @abstractmethod
    async def add_timestamp(self, key: str, timestamp: float) -> None:
        """Add a timestamp for a rate limit key.

        Args:
            key: The rate limit key.
            timestamp: The timestamp to add.
        """
        ...

    @abstractmethod
    async def clear_expired(self, key: str, cutoff: float) -> None:
        """Clear expired timestamps for a key.

        Args:
            key: The rate limit key.
            cutoff: Timestamps older than this are removed.
        """
        ...

    @abstractmethod
    async def clear_all(self) -> None:
        """Clear all rate limit state."""
        ...


class InMemoryRateLimitStore(RateLimitStore):
    """In-memory rate limit storage.

    Phase 2C implementation. State is lost on restart.
    """

    def __init__(self) -> None:
        """Initialize the store."""
        self._lock = asyncio.Lock()
        self._states: dict[str, RateLimitState] = {}

    async def get_timestamps(self, key: str) -> list[float]:
        """Get all timestamps for a rate limit key.

        Args:
            key: The rate limit key.

        Returns:
            List of timestamps.
        """
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                return []
            return list(state.timestamps)

    async def add_timestamp(self, key: str, timestamp: float) -> None:
        """Add a timestamp for a rate limit key.

        Args:
            key: The rate limit key.
            timestamp: The timestamp to add.
        """
        async with self._lock:
            if key not in self._states:
                self._states[key] = RateLimitState()
            self._states[key].timestamps.append(timestamp)

    async def clear_expired(self, key: str, cutoff: float) -> None:
        """Clear expired timestamps for a key.

        Args:
            key: The rate limit key.
            cutoff: Timestamps older than this are removed.
        """
        async with self._lock:
            state = self._states.get(key)
            if state:
                state.timestamps = [ts for ts in state.timestamps if ts > cutoff]

    async def clear_all(self) -> None:
        """Clear all rate limit state."""
        async with self._lock:
            self._states.clear()


class SlidingWindowRateLimiterV2:
    """Sliding window rate limiter using store abstraction.

    Phase 2C: Uses RateLimitStore for storage, enabling future persistence.
    """

    def __init__(
        self,
        max_calls: int,
        period: float,
        store: RateLimitStore | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            max_calls: Maximum calls allowed in the window.
            period: Window size in seconds.
            store: Optional rate limit store (defaults to in-memory).
        """
        self._max_calls = max_calls
        self._period = period
        self._store = store or InMemoryRateLimitStore()

    async def acquire(self, key: str) -> bool:
        """Attempt to acquire a rate limit slot.

        Args:
            key: Rate limit key (session_id, tool_name, etc.).

        Returns:
            True if allowed, False if rate limited.
        """
        now = time.monotonic()
        cutoff = now - self._period

        await self._store.clear_expired(key, cutoff)
        timestamps = await self._store.get_timestamps(key)

        if len(timestamps) >= self._max_calls:
            logger.warning(
                "Rate limit exceeded: key=%s, max_calls=%d, period=%s",
                key,
                self._max_calls,
                self._period,
            )
            return False

        await self._store.add_timestamp(key, now)
        return True

    async def get_remaining(self, key: str) -> int:
        """Get remaining calls in current window.

        Args:
            key: Rate limit key.

        Returns:
            Number of remaining calls.
        """
        now = time.monotonic()
        cutoff = now - self._period

        await self._store.clear_expired(key, cutoff)
        timestamps = await self._store.get_timestamps(key)

        return max(0, self._max_calls - len(timestamps))
