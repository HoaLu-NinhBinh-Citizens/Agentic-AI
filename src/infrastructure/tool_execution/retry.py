"""Retry infrastructure for tool execution - Phase 2.3.

Provides exponential backoff retry with jitter for failed tool executions,
circuit breaker pattern, and configurable retry policies.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

from core.execution.cancellation import CancellationToken

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy(str, Enum):
    """Retry strategy types."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter_factor: float = 0.1
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    retryable_errors: list[str] = field(
        default_factory=lambda: [
            "MCP_ERROR",
            "TIMEOUT",
            "NETWORK_ERROR",
            "CONNECTION_REFUSED",
            "SERVICE_UNAVAILABLE",
            "RuntimeError",
        ]
    )

    def should_retry(self, error_code: str | None, attempt: int) -> bool:
        """Check if error should trigger retry."""
        if attempt >= self.max_attempts:
            return False
        if not error_code:
            return False
        if error_code in self.retryable_errors:
            return True
        if "Error" in error_code:
            return True
        return False

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt with backoff and jitter."""
        if self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        else:
            delay = self.base_delay

        delay = min(delay, self.max_delay)

        if self.jitter_factor > 0:
            jitter = random.uniform(0, self.jitter_factor * delay)
            delay += jitter

        return delay


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 30.0


class CircuitBreaker:
    """Circuit breaker for preventing cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    async def can_execute(self) -> bool:
        """Check if execution is allowed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    return True
                return False

            return True

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        return (time.time() - self._last_failure_time) >= self._config.timeout_seconds

    async def record_success(self) -> None:
        """Record successful execution."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._reset()
                    logger.info("Circuit breaker reset to CLOSED")
            else:
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record failed execution."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker opened after HALF_OPEN failure")
            elif self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker opened after %d failures",
                    self._failure_count,
                )

    def _reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


@dataclass
class RetryMetrics:
    """Metrics for retry operations."""

    total_attempts: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    circuit_breaker_opens: int = 0

    def record_attempt(self) -> None:
        """Record an attempt."""
        self.total_attempts += 1

    def record_success(self) -> None:
        """Record a successful retry."""
        self.successful_retries += 1

    def record_failure(self) -> None:
        """Record a failed retry."""
        self.failed_retries += 1

    def record_circuit_open(self) -> None:
        """Record circuit breaker opening."""
        self.circuit_breaker_opens += 1

    @property
    def retry_rate(self) -> float:
        """Calculate retry rate."""
        if self.total_attempts == 0:
            return 0.0
        return self.successful_retries / self.total_attempts


class RetryExecutor:
    """Executor wrapper that adds retry logic to tool execution.

    Wraps a tool executor and automatically retries failed operations
    based on configured retry policy and circuit breaker settings.
    """

    def __init__(
        self,
        executor: Any,
        retry_config: RetryConfig | None = None,
        circuit_config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize retry executor.

        Args:
            executor: The underlying tool executor to wrap.
            retry_config: Configuration for retry behavior.
            circuit_config: Configuration for circuit breaker.
        """
        self._executor = executor
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = CircuitBreaker(circuit_config)
        self._metrics = RetryMetrics()

    @property
    def metrics(self) -> RetryMetrics:
        """Get retry metrics."""
        return self._metrics

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get circuit breaker."""
        return self._circuit_breaker

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Execute tool with retry logic.

        Args:
            tool_name: Name of tool to execute.
            arguments: Tool arguments.
            cancellation_token: Optional token for cancellation.

        Returns:
            Tool execution result.

        Raises:
            Exception: Final exception after all retries exhausted.
        """
        last_error: Exception | None = None
        error_code: str | None = None

        for attempt in range(1, self._retry_config.max_attempts + 1):
            if cancellation_token and cancellation_token.is_cancelled:
                raise asyncio.CancelledError("Execution cancelled")

            if not await self._circuit_breaker.can_execute():
                self._metrics.record_circuit_open()
                raise RuntimeError(
                    f"Circuit breaker open, request rejected for {tool_name}"
                )

            self._metrics.record_attempt()

            try:
                result = await self._executor.execute(tool_name, arguments)
                await self._circuit_breaker.record_success()

                if attempt > 1:
                    self._metrics.record_success()
                    logger.info(
                        "Retry succeeded for %s on attempt %d",
                        tool_name,
                        attempt,
                    )

                return result

            except Exception as e:
                last_error = e
                error_code = self._extract_error_code(e)
                await self._circuit_breaker.record_failure()

                logger.warning(
                    "Attempt %d/%d failed for %s: %s (code: %s)",
                    attempt,
                    self._retry_config.max_attempts,
                    tool_name,
                    str(e),
                    error_code,
                )

                if not self._retry_config.should_retry(error_code, attempt):
                    logger.info(
                        "Error %s not retryable for %s",
                        error_code,
                        tool_name,
                    )
                    self._metrics.record_failure()
                    raise

                if attempt < self._retry_config.max_attempts:
                    delay = self._retry_config.get_delay(attempt)
                    logger.debug(
                        "Retrying %s in %.2f seconds (attempt %d)",
                        tool_name,
                        delay,
                        attempt + 1,
                    )

                    if cancellation_token:
                        try:
                            await asyncio.wait_for(
                                cancellation_token.wait(),
                                timeout=delay,
                            )
                            raise asyncio.CancelledError("Cancelled during retry delay")
                        except asyncio.TimeoutError:
                            pass
                    else:
                        await asyncio.sleep(delay)

        self._metrics.record_failure()
        raise last_error or RuntimeError(f"All retries exhausted for {tool_name}")

    def _extract_error_code(self, error: Exception) -> str | None:
        """Extract error code from exception.

        Args:
            error: The exception to extract from.

        Returns:
            Error code string or None.
        """
        if hasattr(error, "code"):
            return str(error.code)
        if hasattr(error, "error_code"):
            return str(error.error_code)

        error_str = type(error).__name__
        if "Timeout" in error_str:
            return "TIMEOUT"
        if "Network" in error_str or "Connection" in error_str:
            return "NETWORK_ERROR"
        return error_str


async def retry_with_backoff(
    func: Callable[..., Awaitable[T]],
    config: RetryConfig | None = None,
    *args: Any,
    cancellation_token: CancellationToken | None = None,
    **kwargs: Any,
) -> T:
    """Decorator-style retry for async functions.

    Args:
        func: Async function to retry.
        config: Retry configuration.
        *args: Positional arguments for func.
        cancellation_token: Optional cancellation token (keyword only).
        **kwargs: Keyword arguments for func.

    Returns:
        Result of func.

    Raises:
        Exception: Final exception after retries exhausted.
    """
    retry_config = config or RetryConfig()
    last_error: Exception | None = None

    for attempt in range(1, retry_config.max_attempts + 1):
        if cancellation_token and cancellation_token.is_cancelled:
            raise asyncio.CancelledError("Operation cancelled")

        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e

            error_code = None
            if hasattr(e, "code") and e.code is not None:
                error_code = str(e.code)
            elif hasattr(e, "error_code") and e.error_code is not None:
                error_code = str(e.error_code)
            else:
                error_code = type(e).__name__

            if not retry_config.should_retry(error_code, attempt):
                raise

            if attempt < retry_config.max_attempts:
                delay = retry_config.get_delay(attempt)
                if cancellation_token:
                    try:
                        await asyncio.wait_for(
                            cancellation_token.wait(),
                            timeout=delay,
                        )
                        raise asyncio.CancelledError("Cancelled during retry delay")
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(delay)

    raise last_error or RuntimeError("All retries exhausted")


def create_retry_config(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
) -> RetryConfig:
    """Factory function to create retry config.

    Args:
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay between retries.
        max_delay: Maximum delay cap.
        strategy: Backoff strategy.

    Returns:
        Configured RetryConfig instance.
    """
    return RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=strategy,
    )
