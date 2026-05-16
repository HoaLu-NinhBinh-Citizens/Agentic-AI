"""Circuit breaker implementation for Phase 2D/2D.1.

Provides fault tolerance for MCP server calls with transient failure detection.
Supports sliding time window for accurate failure rate tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str = "Circuit breaker is open"):
        """Initialize the error.

        Args:
            message: Error message.
        """
        self.message = message
        super().__init__(self.message)


class CircuitBreaker:
    """Circuit breaker for MCP server fault tolerance.

    Prevents cascading failures by failing fast when a server is unhealthy.
    Uses a sliding time window for failure tracking to provide accurate
    error rate measurement.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        timeout_seconds: float = 60.0,
        transient_error_codes: list[str] | None = None,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            name: Name of the server/resource.
            failure_threshold: Number of failures before opening circuit.
            window_seconds: Time window for tracking failures (sliding window).
            timeout_seconds: Seconds before attempting to close circuit.
            transient_error_codes: Error codes considered transient.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.timeout_seconds = timeout_seconds
        self.transient_error_codes = transient_error_codes or [
            "MCP_ERROR",
            "TIMEOUT",
            "CONNECTION_REFUSED",
            "CONNECTION_ERROR",
        ]

        self._state = CircuitBreakerState.CLOSED
        self._failure_timestamps: deque[float] = deque()
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()
        self._half_open_used = False

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count (within window)."""
        return self._failure_count_in_window()

    def _failure_count_in_window(self) -> int:
        """Get the number of failures within the sliding window.

        Returns:
            Number of failures in the current time window.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        while self._failure_timestamps and self._failure_timestamps[0] < cutoff:
            self._failure_timestamps.popleft()

        return len(self._failure_timestamps)

    def _is_transient_failure(self, error: Exception) -> bool:
        """Check if an error is transient.

        Args:
            error: The exception to check.

        Returns:
            True if the error is transient.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__

        transient_patterns = [
            "connection",
            "timeout",
            "refused",
            "broken pipe",
            "reset",
            "network",
            "unreachable",
        ]

        for pattern in transient_patterns:
            if pattern in error_str:
                return True

        for code in self.transient_error_codes:
            if code.lower() in error_str:
                return True

        return error_type in (
            "ConnectionError",
            "TimeoutError",
            "BrokenPipeError",
            "ConnectionRefusedError",
            "ConnectionResetError",
            "OSError",
        )

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a function through the circuit breaker.

        Args:
            func: Async function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Result from func.

        Raises:
            CircuitBreakerOpenError: If circuit is open.
        """
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if time.monotonic() - self._last_failure_time > self.timeout_seconds:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_used = False
                    logger.info(
                        "Circuit half-open",
                        extra={"server_name": self.name},
                    )
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is open"
                    )

            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_used:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is half-open, probe pending"
                    )
                self._half_open_used = True

        try:
            result = await func(*args, **kwargs)

            async with self._lock:
                if self._state == CircuitBreakerState.HALF_OPEN:
                    self._state = CircuitBreakerState.CLOSED
                    self._failure_timestamps.clear()
                    self._half_open_used = False
                    logger.info(
                        "Circuit closed",
                        extra={"server_name": self.name},
                    )

            return result

        except Exception as e:
            is_transient = self._is_transient_failure(e)

            async with self._lock:
                if is_transient:
                    now = time.monotonic()
                    self._failure_timestamps.append(now)
                    self._last_failure_time = now

                    current_count = self._failure_count_in_window()

                    if self._state == CircuitBreakerState.HALF_OPEN:
                        self._state = CircuitBreakerState.OPEN
                        self._half_open_used = False
                        logger.error(
                            "Circuit opened after probe failure",
                            extra={
                                "server_name": self.name,
                                "failure_count": current_count,
                            },
                        )
                    elif current_count >= self.failure_threshold:
                        self._state = CircuitBreakerState.OPEN
                        logger.error(
                            "Circuit opened",
                            extra={
                                "server_name": self.name,
                                "failure_count": current_count,
                            },
                        )

            raise

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_used = False
        logger.info(
            "Circuit breaker reset",
            extra={"server_name": self.name},
        )
