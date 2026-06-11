"""Circuit breaker implementation for Phase 2D/2D.1.

Provides fault tolerance for MCP server calls with transient failure detection.
Supports sliding time window for accurate failure rate tracking.

FIX W-008: Fixed half-open race condition with single-winner pattern.
FIX W-009: Added exponential backoff retry for transient failures.
"""

from __future__ import annotations

import asyncio
import structlog
import time
from collections import deque
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

logger = structlog.get_logger(__name__)

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
        max_retries: int = 3,
        base_backoff: float = 0.1,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            name: Name of the server/resource.
            failure_threshold: Number of failures before opening circuit.
            window_seconds: Time window for tracking failures (sliding window).
            timeout_seconds: Seconds before attempting to close circuit.
            transient_error_codes: Error codes considered transient.
            max_retries: Maximum number of retries for transient failures.
            base_backoff: Base backoff time in seconds.
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
        self.max_retries = max_retries  # W-009
        self.base_backoff = base_backoff  # W-009

        self._state = CircuitBreakerState.CLOSED
        self._failure_timestamps: deque[float] = deque()
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()
        self._half_open_used = False
        self._half_open_lock_held = False  # W-008: Single-winner flag

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

        FIX W-008: Fixed half-open race with atomic transition.
        FIX W-009: Added exponential backoff retry for transient failures.

        Args:
            func: Async function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Result from func.

        Raises:
            CircuitBreakerOpenError: If circuit is open.
        """
        last_exception = None
        failure_recorded = False
        
        for attempt in range(self.max_retries + 1):
            try:
                return await self._execute(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                # Circuit is open or half-open, don't retry
                raise
            except Exception as e:
                last_exception = e
                
                # Check current state (may have changed during execution)
                async with self._lock:
                    current_state = self._state
                
                # In HALF_OPEN state, no retries - probe must execute exactly once
                if current_state == CircuitBreakerState.HALF_OPEN:
                    if not failure_recorded:
                        await self._record_failure(e)
                        failure_recorded = True
                    raise
                
                # Only retry if transient and haven't exhausted retries
                if self._is_transient_failure(e) and attempt < self.max_retries:
                    # W-009 backoff: previously documented but never slept,
                    # so retries hammered the failing server back-to-back.
                    await asyncio.sleep(self.base_backoff * (2**attempt))
                    continue
                else:
                    # Non-transient or max retries reached
                    # Record failure only ONCE per call (regardless of retries)
                    if not failure_recorded:
                        await self._record_failure(e)
                        failure_recorded = True
                    raise
        
        # Should not reach here, but just in case
        raise last_exception or Exception("Circuit breaker call failed")

    async def _execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function with circuit breaker protection.
        
        FIX W-008: Single-winner pattern for half-open state.
        """
        # W-008: Atomic check-and-transition for half-open
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if time.monotonic() - self._last_failure_time > self.timeout_seconds:
                    # W-008: Only first request wins to become half-open
                    if not self._half_open_lock_held:
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._half_open_used = False  # Reset for new probe attempt
                        self._half_open_lock_held = True
                        logger.info(
                            "circuit_half_open",
                            server=self.name,
                        )
                    # else: another request already transitioning
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
                    self._half_open_lock_held = False
                    logger.info(
                        "circuit_closed",
                        server=self.name,
                    )

            return result

        except Exception as e:
            # Don't record failure here - let call() handle it
            raise

    async def _record_failure(self, e: Exception) -> None:
        """Record a failure and potentially open the circuit."""
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
                    self._half_open_lock_held = False  # Reset so next request can transition to HALF_OPEN
                    logger.warning(
                        "circuit_opened_probe_failed",
                        server=self.name,
                        failure_count=current_count,
                    )
                elif current_count >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    logger.warning(
                        "circuit_opened",
                        server=self.name,
                        failure_count=current_count,
                    )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_used = False
        self._half_open_lock_held = False
        logger.info(
            "circuit_breaker_reset",
            server=self.name,
        )
