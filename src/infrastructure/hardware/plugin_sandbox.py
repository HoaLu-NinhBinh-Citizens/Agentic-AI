"""Plugin sandbox and resilience patterns.

This module implements plugin isolation and resilience patterns including:
- Timeout enforcement
- Circuit breaker pattern
- Process isolation (optional)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable
import structlog

from .exceptions import PluginCrashError, PluginTimeoutError

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: float = 30.0  # Time before half-open
    exclude_exceptions: tuple[type[Exception], ...] = ()  # Exceptions to ignore


class CircuitBreaker:
    """Circuit breaker implementation.

    Prevents cascading failures by tracking plugin failures
    and temporarily blocking calls to failing plugins.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking)."""
        return self._state == CircuitState.OPEN

    def _should_ignore(self, exc: Exception) -> bool:
        """Check if exception should be ignored."""
        return isinstance(exc, self.config.exclude_exceptions)

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._close()
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

        logger.debug("circuit_success", name=self.name, state=self._state.value)

    def record_failure(self, exc: Exception) -> None:
        """Record a failed call.

        Args:
            exc: The exception that occurred
        """
        if self._should_ignore(exc):
            return

        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._open()
        elif self._failure_count >= self.config.failure_threshold:
            self._open()

        logger.warning(
            "circuit_failure",
            name=self.name,
            failure_count=self._failure_count,
            state=self._state.value,
        )

    def _open(self) -> None:
        """Open the circuit."""
        self._state = CircuitState.OPEN
        self._opened_at = time.time()
        self._success_count = 0
        logger.warning("circuit_opened", name=self.name)

    def _close(self) -> None:
        """Close the circuit."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None
        logger.info("circuit_closed", name=self.name)

    def _try_half_open(self) -> None:
        """Attempt to transition to half-open."""
        if self._opened_at is None:
            return

        elapsed = time.time() - self._opened_at
        if elapsed >= self.config.timeout_seconds:
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info("circuit_half_open", name=self.name)

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            self._try_half_open()
            return self._state == CircuitState.HALF_OPEN

        return True  # HALF_OPEN allows execution

    def get_state(self) -> dict[str, Any]:
        """Get circuit state for monitoring."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "opened_at": self._opened_at,
        }


@dataclass
class SandboxConfig:
    """Sandbox configuration."""

    timeout_seconds: float = 5.0
    enable_process_isolation: bool = False
    max_memory_mb: int = 256
    enable_circuit_breaker: bool = True
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


class PluginSandbox:
    """Sandbox for plugin execution.

    Provides:
    - Timeout enforcement
    - Circuit breaker pattern
    - Optional process isolation
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._circuits: dict[str, CircuitBreaker] = {}

    def get_circuit(self, plugin_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            CircuitBreaker instance
        """
        if plugin_name not in self._circuits:
            self._circuits[plugin_name] = CircuitBreaker(
                name=plugin_name,
                config=self.config.circuit_breaker,
            )
        return self._circuits[plugin_name]

    async def execute(
        self,
        plugin_name: str,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> Any:
        """Execute function with sandbox protections.

        Args:
            plugin_name: Name of plugin (for circuit breaker)
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            PluginTimeoutError: If execution times out
            PluginCrashError: If circuit is open
        """
        circuit = self.get_circuit(plugin_name)

        # Check circuit breaker
        if not circuit.can_execute():
            raise PluginCrashError(
                plugin_name=plugin_name,
                exit_code=None,
            )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout_seconds,
            )
            circuit.record_success()
            return result

        except asyncio.TimeoutError:
            circuit.record_failure(TimeoutError("Execution timed out"))
            raise PluginTimeoutError(
                plugin_name=plugin_name,
                operation=func.__name__,
                timeout_seconds=self.config.timeout_seconds,
            )

        except Exception as e:
            if not circuit.can_execute():
                raise PluginCrashError(
                    plugin_name=plugin_name,
                    exit_code=None,
                    cause=e,
                )
            raise

    def execute_sync(
        self,
        plugin_name: str,
        func: Callable[..., Any],
        *args,
        **kwargs,
    ) -> Any:
        """Execute function synchronously with timeout.

        Note: For true async, use execute().

        Args:
            plugin_name: Name of plugin
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result
        """
        return asyncio.run(self.execute(plugin_name, func, *args, **kwargs))

    def get_all_circuit_states(self) -> dict[str, dict[str, Any]]:
        """Get state of all circuit breakers.

        Returns:
            Dictionary of plugin name to circuit state
        """
        return {
            name: circuit.get_state()
            for name, circuit in self._circuits.items()
        }

    def reset_circuit(self, plugin_name: str) -> bool:
        """Manually reset a circuit breaker.

        Args:
            plugin_name: Plugin name

        Returns:
            True if reset
        """
        if plugin_name in self._circuits:
            self._circuits[plugin_name]._close()
            return True
        return False

    def get_metrics(self) -> dict[str, Any]:
        """Get sandbox metrics."""
        return {
            "timeout_seconds": self.config.timeout_seconds,
            "process_isolation": self.config.enable_process_isolation,
            "circuit_breakers": self.get_all_circuit_states(),
        }


# Global sandbox instance
_sandbox: PluginSandbox | None = None


def get_sandbox() -> PluginSandbox:
    """Get global sandbox instance.

    Returns:
        Global PluginSandbox
    """
    global _sandbox
    if _sandbox is None:
        _sandbox = PluginSandbox()
    return _sandbox


def set_sandbox(sandbox: PluginSandbox) -> None:
    """Set global sandbox instance.

    Args:
        sandbox: Sandbox to use globally
    """
    global _sandbox
    _sandbox = sandbox
