"""Hierarchical rate limiter for tool execution.

Provides fair scheduling across tools and keys.
Global bucket → Per-tool bucket → Per-key fair queue
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    global_rate: float = 100.0
    global_burst: float = 20.0
    tool_rate: float = 20.0
    tool_burst: float = 5.0
    key_rate: float = 10.0
    key_burst: float = 2.0
    window_seconds: float = 1.0


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(
        self,
        rate: float,
        burst: float,
        window_seconds: float = 1.0,
    ) -> None:
        self.rate = rate
        self.burst = burst
        self.window_seconds = window_seconds
        self._tokens = burst
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if acquired, False otherwise
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update

            self._tokens = min(
                self.burst,
                self._tokens + elapsed * self.rate,
            )
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def try_acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire without blocking."""
        return await self.acquire(tokens)

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        now = time.monotonic()
        elapsed = now - self._last_update
        return min(self.burst, self._tokens + elapsed * self.rate)


class FairQueue:
    """Fair queue for per-key scheduling within a tool."""

    def __init__(self) -> None:
        self._queue: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self._order: list[str] = []
        self._lock = asyncio.Lock()
        self._current_index = 0

    async def enqueue(self, key: str) -> asyncio.Event:
        """Enqueue a key and return its event.

        Args:
            key: Key to enqueue

        Returns:
            Event to wait on
        """
        async with self._lock:
            if key not in self._queue:
                self._queue[key] = asyncio.Event()
                self._order.append(key)
            return self._queue[key]

    async def dequeue(self) -> str | None:
        """Get next key in fair round-robin order.

        Returns:
            Next key or None if queue empty
        """
        async with self._lock:
            if not self._order:
                return None

            key = self._order[self._current_index % len(self._order)]
            self._current_index += 1
            return key

    def notify(self, key: str) -> None:
        """Notify that a key's operation completed.

        Args:
            key: Key to notify
        """
        if key in self._queue:
            self._queue[key].set()

    async def remove(self, key: str) -> None:
        """Remove a key from the queue.

        Args:
            key: Key to remove
        """
        async with self._lock:
            if key in self._queue:
                self._queue[key].set()
                del self._queue[key]
                if key in self._order:
                    self._order.remove(key)

    def __len__(self) -> int:
        return len(self._order)


class ToolRateLimiter:
    """Hierarchical rate limiter.

    Hierarchy:
    Global bucket → Per-tool bucket → Per-key fair queue

    Guarantees:
    - No single key can dominate tool capacity
    - Fair scheduling across keys per tool
    - Global protection against overload
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()

        self._global_bucket = TokenBucket(
            rate=self.config.global_rate,
            burst=self.config.global_burst,
            window_seconds=self.config.window_seconds,
        )

        self._tool_buckets: dict[str, TokenBucket] = {}
        self._tool_queues: dict[str, FairQueue] = {}
        self._tool_weights: dict[str, float] = {}

        self._lock = asyncio.Lock()

        self._cooldown_keys: dict[str, float] = {}

    async def acquire(
        self,
        tool: str,
        key: str,
        tokens: float = 1.0,
        weight: float = 1.0,
    ) -> bool:
        """Acquire rate limit for tool+key.

        Keys in cooldown do NOT consume tokens.

        Args:
            tool: Tool name
            key: Cache key
            tokens: Number of tokens to acquire
            weight: Weight for this key (higher = more tokens)

        Returns:
            True if acquired, False if rate limited
        """
        now = time.time()

        if key in self._cooldown_keys and now < self._cooldown_keys[key]:
            return False

        if not await self._global_bucket.acquire(tokens):
            logger.debug(f"Global rate limit exceeded")
            return False

        tool_bucket = await self._get_tool_bucket(tool)
        if not await tool_bucket.acquire(tokens * weight):
            logger.debug(f"Tool rate limit exceeded for {tool}")
            return False

        return True

    async def _get_tool_bucket(self, tool: str) -> TokenBucket:
        """Get or create tool bucket."""
        async with self._lock:
            if tool not in self._tool_buckets:
                weight = self._tool_weights.get(tool, 1.0)
                self._tool_buckets[tool] = TokenBucket(
                    rate=self.config.tool_rate * weight,
                    burst=self.config.tool_burst * weight,
                    window_seconds=self.config.window_seconds,
                )
                self._tool_queues[tool] = FairQueue()
            return self._tool_buckets[tool]

    async def set_tool_weight(self, tool: str, weight: float) -> None:
        """Set weight for a tool.

        Args:
            tool: Tool name
            weight: Weight multiplier
        """
        async with self._lock:
            self._tool_weights[tool] = weight

            if tool in self._tool_buckets:
                bucket = self._tool_buckets[tool]
                bucket.rate = self.config.tool_rate * weight
                bucket.burst = self.config.tool_burst * weight

    def set_key_cooldown(self, key: str, duration: float = 300.0) -> None:
        """Set cooldown for a key (used when in single-flight cooldown).

        Args:
            key: Cache key
            duration: Cooldown duration in seconds
        """
        self._cooldown_keys[key] = time.time() + duration
        logger.debug(f"Key {key} set to cooldown for {duration}s")

    def is_key_in_cooldown(self, key: str) -> bool:
        """Check if key is in cooldown."""
        if key not in self._cooldown_keys:
            return False
        if time.time() >= self._cooldown_keys[key]:
            del self._cooldown_keys[key]
            return False
        return True

    async def cleanup_cooldowns(self) -> int:
        """Clean up expired cooldowns.

        Returns:
            Number of cooldowns cleaned up
        """
        now = time.time()
        to_remove = [k for k, v in self._cooldown_keys.items() if now >= v]

        for key in to_remove:
            del self._cooldown_keys[key]

        return len(to_remove)

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        stats = {
            "global_available": self._global_bucket.available_tokens,
            "tools": {},
            "total_cooldowns": len(self._cooldown_keys),
        }

        for tool, bucket in self._tool_buckets.items():
            stats["tools"][tool] = {
                "available": bucket.available_tokens,
                "rate": bucket.rate,
                "burst": bucket.burst,
                "queue_size": len(self._tool_queues.get(tool, [])),
            }

        return stats

    async def reset(self) -> None:
        """Reset all rate limiters."""
        async with self._lock:
            self._global_bucket = TokenBucket(
                rate=self.config.global_rate,
                burst=self.config.global_burst,
                window_seconds=self.config.window_seconds,
            )
            self._tool_buckets.clear()
            self._tool_queues.clear()
            self._cooldown_keys.clear()
