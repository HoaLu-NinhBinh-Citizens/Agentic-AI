"""
Runtime Circuit Breaker - Fault isolation for dependencies

Provides fault isolation by stopping cascade failures when a dependency fails.

State Machine:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped, requests rejected immediately
- HALF_OPEN: Testing if dependency has recovered
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when circuit is open."""

    def __init__(self, circuit_name: str, retry_after: float | None = None):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        msg = f"Circuit '{circuit_name}' is OPEN"
        if retry_after:
            msg += f". Retry after {retry_after:.1f}s"
        super().__init__(msg)


class CircuitBreaker:
    """
    Circuit breaker for fault isolation.
    
    Usage:
        circuit = CircuitBreaker("ollama")
        result = await circuit.call(my_async_func)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = time.time()
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        await self._check_state()

        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            retry_after = max(0, self.timeout_seconds - elapsed)
            raise CircuitOpenError(self.name, retry_after)

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _check_state(self) -> None:
        """Check if circuit should transition states."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.timeout_seconds:
                    logger.info(f"Circuit '{self.name}': OPEN -> HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    logger.info(f"Circuit '{self.name}': HALF_OPEN -> CLOSED")
                    self.state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self.state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._success_count = 0

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit '{self.name}': HALF_OPEN -> OPEN")
                self.state = CircuitState.OPEN
            elif self._failure_count >= self.failure_threshold:
                logger.warning(f"Circuit '{self.name}': CLOSED -> OPEN (failures: {self._failure_count})")
                self.state = CircuitState.OPEN

    async def reset(self) -> None:
        """Manually reset circuit to closed state."""
        async with self._lock:
            logger.info(f"Circuit '{self.name}': Reset to CLOSED")
            self.state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = time.time()

    def get_stats(self) -> dict:
        """Get circuit statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": datetime.fromtimestamp(self._last_failure_time).isoformat(),
        }


class CircuitRegistry:
    """Registry for circuit breakers."""

    _circuits: dict[str, CircuitBreaker] = {}

    @classmethod
    def get(cls, name: str, **kwargs) -> CircuitBreaker:
        """Get or create circuit breaker."""
        if name not in cls._circuits:
            cls._circuits[name] = CircuitBreaker(name, **kwargs)
        return cls._circuits[name]

    @classmethod
    def all_stats(cls) -> dict[str, dict]:
        """Get stats for all circuits."""
        return {name: cb.get_stats() for name, cb in cls._circuits.items()}

    @classmethod
    async def reset_all(cls) -> None:
        """Reset all circuits."""
        for cb in cls._circuits.values():
            await cb.reset()

    @classmethod
    def clear(cls) -> None:
        """Clear registry."""
        cls._circuits.clear()


circuit_registry = CircuitRegistry


def get_circuit(name: str, **kwargs) -> CircuitBreaker:
    """Get circuit breaker from registry."""
    return CircuitRegistry.get(name, **kwargs)


DEFAULT_CIRCUITS = {
    "ollama": {"failure_threshold": 3, "timeout_seconds": 30.0},
    "embeddings": {"failure_threshold": 5, "timeout_seconds": 60.0},
    "vector_db": {"failure_threshold": 3, "timeout_seconds": 30.0},
    "file_system": {"failure_threshold": 5, "timeout_seconds": 10.0},
    "external_api": {"failure_threshold": 5, "timeout_seconds": 60.0},
}


def init_default_circuits() -> dict[str, CircuitBreaker]:
    """Initialize default circuit breakers."""
    return {name: CircuitBreaker(name, **cfg) for name, cfg in DEFAULT_CIRCUITS.items()}
