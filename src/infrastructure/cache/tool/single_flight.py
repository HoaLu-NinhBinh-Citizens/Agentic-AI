"""Single-flight coordinator for deduplicating concurrent requests.

Ensures only 1 active execution per key at any time.
Bounded lifecycle with timeout and cooldown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Generic, TypeVar

from src.infrastructure.cache.tool.types import KeyState, RefreshToken

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class SingleFlightConfig:
    """Configuration for single-flight behavior."""

    timeout_seconds: float = 30.0
    max_pending_keys: int = 1000
    cooldown_seconds: float = 300.0
    max_retries_normal: int = 3
    max_retries_backoff: int = 10
    backoff_base_ms: float = 100.0


class SingleFlightError(Exception):
    """Single-flight operation error."""

    pass


class CooldownError(SingleFlightError):
    """Key is in cooldown period."""

    pass


class PendingLimitError(SingleFlightError):
    """Max pending keys exceeded."""

    pass


@dataclass
class Flight(Generic[T]):
    """Represents a single in-flight operation."""

    key: str
    future: asyncio.Future[T]
    token: RefreshToken
    created_at: float = field(default_factory=time.time)
    waiters: int = 0


class SingleFlightCoordinator:
    """Coordinates single-flight execution per key.

    Guarantees:
    - Only 1 active execution per key at any time
    - Bounded lifecycle with timeout
    - Cooldown after repeated failures

    Failure model:
    | Failure Count | Behavior              |
    |---------------|----------------------|
    | 1-3          | Normal retry         |
    | 4-10         | Exponential backoff  |
    | >10          | Cooldown (5 min)     |
    """

    def __init__(self, config: SingleFlightConfig | None = None) -> None:
        self.config = config or SingleFlightConfig()
        self._flights: dict[str, Flight] = {}
        self._cooldowns: dict[str, float] = {}
        self._failure_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._pending_count = 0

    async def acquire(self, key: str, tool: str) -> asyncio.Future | None:
        """Acquire permission to execute for a key.

        Args:
            key: Cache key
            tool: Tool name (for tracking)

        Returns:
            Existing Future if another request is in-flight, None if acquired

        Raises:
            CooldownError: If key is in cooldown
            PendingLimitError: If max pending keys exceeded
        """
        async with self._lock:
            now = time.time()

            if key in self._cooldowns and now < self._cooldowns[key]:
                raise CooldownError(f"Key {key} is in cooldown until {self._cooldowns[key]}")

            if self._pending_count >= self.config.max_pending_keys:
                raise PendingLimitError(
                    f"Max pending keys ({self.config.max_pending_keys}) exceeded"
                )

            if key in self._flights:
                flight = self._flights[key]
                flight.waiters += 1
                return flight.future

            future: asyncio.Future = asyncio.get_event_loop().create_future()
            token = RefreshToken(key=key, tool=tool, started_at=now)

            self._flights[key] = Flight(
                key=key,
                future=future,
                token=token,
            )
            self._pending_count += 1

            return None

    async def release(
        self,
        key: str,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        """Release a flight, completing all waiters.

        Args:
            key: Cache key
            result: Result value if successful
            error: Exception if failed
        """
        async with self._lock:
            if key not in self._flights:
                logger.warning(f"Release called for non-existent flight: {key}")
                return

            flight = self._flights.pop(key)
            self._pending_count = max(0, self._pending_count - 1)

            if error is not None:
                await self._handle_failure(key, flight, error)
            else:
                self._failure_counts[key] = 0

            if not flight.future.done():
                if error is not None:
                    flight.future.set_exception(error)
                else:
                    flight.future.set_result(result)

    def _handle_failure(
        self,
        key: str,
        flight: Flight,
        error: Exception,
    ) -> None:
        """Handle flight failure based on failure count."""
        count = self._failure_counts.get(key, 0) + 1
        self._failure_counts[key] = count

        logger.warning(f"Flight failed for key {key}: {error} (attempt {count})")

        if count > self.config.max_retries_backoff:
            self._cooldowns[key] = time.time() + self.config.cooldown_seconds
            logger.warning(f"Key {key} entering cooldown for {self.config.cooldown_seconds}s")
        elif count > self.config.max_retries_normal:
            delay = self.config.backoff_base_ms * (2 ** (count - self.config.max_retries_normal)) / 1000.0
            logger.debug(f"Key {key} backoff delay: {delay}s")

    async def execute(
        self,
        key: str,
        tool: str,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function with single-flight deduplication.

        Args:
            key: Cache key
            tool: Tool name
            fn: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CooldownError: If key is in cooldown
            PendingLimitError: If max pending keys exceeded
            asyncio.TimeoutError: If execution times out
        """
        existing_future = await self.acquire(key, tool)

        if existing_future is not None:
            return await asyncio.wait_for(existing_future, timeout=self.config.timeout_seconds)

        try:
            result = await asyncio.wait_for(
                fn(*args, **kwargs),
                timeout=self.config.timeout_seconds,
            )
            await self.release(key, result=result)
            return result
        except asyncio.TimeoutError:
            await self.release(key, error=asyncio.TimeoutError(f"Execution timed out for key {key}"))
            raise
        except Exception as e:
            await self.release(key, error=e)
            raise

    async def cancel(self, key: str) -> bool:
        """Cancel an in-flight operation.

        Args:
            key: Cache key

        Returns:
            True if cancelled, False if not found
        """
        async with self._lock:
            if key not in self._flights:
                return False

            flight = self._flights[key]
            if not flight.future.done():
                flight.future.cancel()

            self._flights.pop(key)
            self._pending_count = max(0, self._pending_count - 1)
            return True

    async def cancel_all(self) -> int:
        """Cancel all in-flight operations.

        Returns:
            Number of operations cancelled
        """
        async with self._lock:
            count = 0
            for key, flight in self._flights.items():
                if not flight.future.done():
                    flight.future.cancel()
                    count += 1

            self._flights.clear()
            self._pending_count = 0
            return count

    def is_in_flight(self, key: str) -> bool:
        """Check if key is currently in-flight."""
        return key in self._flights

    def is_in_cooldown(self, key: str) -> bool:
        """Check if key is in cooldown."""
        if key not in self._cooldowns:
            return False
        return time.time() < self._cooldowns[key]

    def cooldown_remaining(self, key: str) -> float:
        """Get remaining cooldown time in seconds."""
        if key not in self._cooldowns:
            return 0.0
        remaining = self._cooldowns[key] - time.time()
        return max(0.0, remaining)

    def get_stats(self) -> dict[str, Any]:
        """Get coordinator statistics."""
        return {
            "pending_count": self._pending_count,
            "max_pending_keys": self.config.max_pending_keys,
            "cooldown_keys": len(self._cooldowns),
            "failure_counts": dict(self._failure_counts),
            "in_flight": list(self._flights.keys()),
        }

    async def cleanup(self) -> int:
        """Clean up old cooldown entries.

        Returns:
            Number of entries cleaned up
        """
        async with self._lock:
            now = time.time()
            to_remove = [k for k, v in self._cooldowns.items() if now >= v]

            for key in to_remove:
                del self._cooldowns[key]
                self._failure_counts.pop(key, None)

            return len(to_remove)
