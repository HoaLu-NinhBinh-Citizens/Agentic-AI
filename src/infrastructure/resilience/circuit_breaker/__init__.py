"""Circuit breaker stub."""

import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker pattern implementation."""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._timeout = timeout
        self._last_failure_time: float | None = None
    
    def record_success(self) -> None:
        """Record a successful call."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and time.time() - self._last_failure_time > self._timeout:
                self._state = CircuitState.HALF_OPEN
                return True
            return False
        return True
