"""
Two-Way Circuit Breaker for Multi-Agent Coordination.

Implements bidirectional circuit breaker protecting both directions:
- Coordinator -> Agent: Protects coordinator from failing agents
- Agent -> Coordinator: Protects agents from failing coordinator

Uses sliding window for accurate failure rate tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from src.core.multi_agent.coordination.types import (
    CircuitBreakerDirection,
    CircuitBreakerState,
    CircuitBreakerInfo,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    
    def __init__(
        self,
        message: str = "Circuit breaker is open",
        target_id: str = "",
        direction: CircuitBreakerDirection = CircuitBreakerDirection.COORDINATOR_TO_AGENT,
        retry_after: float = 0.0,
    ):
        super().__init__(message)
        self.target_id = target_id
        self.direction = direction
        self.retry_after = retry_after


@dataclass
class PerTargetState:
    """State for a single target (agent or coordinator)."""
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_timestamps: deque = field(default_factory=lambda: deque())
    half_open_used: bool = False
    last_failure_time: float = 0.0
    last_state_change: datetime = field(default_factory=datetime.now)
    success_count: int = 0
    failure_count: int = 0


class TwoWayCircuitBreaker:
    """
    Two-way circuit breaker for multi-agent coordination.
    
    Protects both directions of communication:
    - Coordinator -> Agent: Opens when agent fails too many calls
    - Agent -> Coordinator: Opens when coordinator returns 5xx errors
    
    Features:
    - Sliding time window for accurate failure tracking
    - Per-direction and per-target state
    - Configurable transient error codes
    - Half-open probe limiting
    - Automatic recovery after timeout
    """
    
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        transient_error_codes: Optional[list[str]] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.transient_error_codes = transient_error_codes or [
            "MCP_ERROR",
            "TIMEOUT",
            "CONNECTION_REFUSED",
            "CONNECTION_ERROR",
            "SERVICE_UNAVAILABLE",
            "GATEWAY_TIMEOUT",
        ]
        
        # Per-target per-direction state
        self._states: Dict[str, PerTargetState] = defaultdict(PerTargetState)
        self._lock = asyncio.Lock()
        
        # Metrics
        self._total_calls = 0
        self._total_failures = 0
        self._state_changes = 0
    
    def _make_key(self, target_id: str, direction: CircuitBreakerDirection) -> str:
        """Create unique key for target + direction combination."""
        return f"{direction.value}:{target_id}"
    
    def _failure_count_in_window(self, state: PerTargetState) -> int:
        """Get failures within sliding window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        
        while state.failure_timestamps and state.failure_timestamps[0] < cutoff:
            state.failure_timestamps.popleft()
        
        return len(state.failure_timestamps)
    
    def _is_transient_failure(self, error: Exception) -> bool:
        """Check if error is transient and should trigger circuit breaker."""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        transient_patterns = [
            "connection", "timeout", "refused", "broken pipe",
            "reset", "network", "unreachable", "unavailable",
            "temporarily", "try again",
        ]
        
        for pattern in transient_patterns:
            if pattern in error_str:
                return True
        
        for code in self.transient_error_codes:
            if code.lower() in error_str:
                return True
        
        return error_type in (
            "ConnectionError", "TimeoutError", "BrokenPipeError",
            "ConnectionRefusedError", "ConnectionResetError", "OSError",
            "CircuitBreakerOpenError", "httpx.HTTPStatusError",
        )
    
    def _is_5xx_error(self, error: Exception) -> bool:
        """Check if error is a 5xx server error."""
        error_str = str(error)
        return any(
            code in error_str
            for code in ["500", "501", "502", "503", "504", "520", "521", "522", "523", "524"]
        )
    
    async def call(
        self,
        target_id: str,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        direction: CircuitBreakerDirection = CircuitBreakerDirection.COORDINATOR_TO_AGENT,
        **kwargs: Any,
    ) -> T:
        """
        Execute a function through the circuit breaker.
        
        Args:
            target_id: ID of the target (agent or coordinator)
            func: Async function to execute
            *args: Positional arguments for func
            direction: Direction of the call
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        key = self._make_key(target_id, direction)
        
        async with self._lock:
            if key not in self._states:
                self._states[key] = PerTargetState()
            state = self._states[key]
            
            # Check if we should transition from OPEN to HALF_OPEN
            if state.state == CircuitBreakerState.OPEN:
                if time.monotonic() - state.last_failure_time > self.recovery_timeout:
                    state.state = CircuitBreakerState.HALF_OPEN
                    state.half_open_used = False
                    state.last_state_change = datetime.now()
                    self._state_changes += 1
                    logger.info(
                        f"Circuit half-open for {target_id} ({direction.value})",
                        extra={"circuit": self.name},
                    )
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is open for {target_id}",
                        target_id=target_id,
                        direction=direction,
                        retry_after=self.recovery_timeout - (time.monotonic() - state.last_failure_time),
                    )
            
            # Check half-open probe limit
            if state.state == CircuitBreakerState.HALF_OPEN:
                if state.half_open_used:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is half-open for {target_id}, probe pending",
                        target_id=target_id,
                        direction=direction,
                        retry_after=1.0,
                    )
                state.half_open_used = True
        
        # Execute the call
        self._total_calls += 1
        try:
            result = await func(*args, **kwargs)
            
            # Success - close circuit if in half-open
            async with self._lock:
                if key in self._states:
                    state = self._states[key]
                    if state.state == CircuitBreakerState.HALF_OPEN:
                        state.state = CircuitBreakerState.CLOSED
                        state.failure_timestamps.clear()
                        state.half_open_used = False
                        state.last_state_change = datetime.now()
                        state.success_count += 1
                        self._state_changes += 1
                        logger.info(
                            f"Circuit closed for {target_id} ({direction.value})",
                            extra={"circuit": self.name},
                        )
            
            return result
            
        except Exception as e:
            # Determine if error should trigger circuit
            should_circuit = self._is_transient_failure(e)
            
            # For agent->coordinator, also check 5xx errors
            if direction == CircuitBreakerDirection.AGENT_TO_COORDINATOR:
                should_circuit = should_circuit or self._is_5xx_error(e)
            
            if should_circuit:
                await self._record_failure(key, state, target_id, direction)
            else:
                logger.warning(
                    f"Non-transient error for {target_id}: {e}",
                    extra={"circuit": self.name},
                )
            
            raise
    
    async def _record_failure(
        self,
        key: str,
        state: PerTargetState,
        target_id: str,
        direction: CircuitBreakerDirection,
    ) -> None:
        """Record a failure and potentially open the circuit."""
        now = time.monotonic()
        state.failure_timestamps.append(now)
        state.last_failure_time = now
        state.failure_count += 1
        self._total_failures += 1
        
        current_count = self._failure_count_in_window(state)
        
        async with self._lock:
            if state.state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open reopens circuit
                state.state = CircuitBreakerState.OPEN
                state.half_open_used = False
                state.last_state_change = datetime.now()
                self._state_changes += 1
                logger.error(
                    f"Circuit reopened after probe failure for {target_id}",
                    extra={"circuit": self.name, "failures": current_count},
                )
            elif current_count >= self.failure_threshold:
                state.state = CircuitBreakerState.OPEN
                state.last_state_change = datetime.now()
                self._state_changes += 1
                logger.error(
                    f"Circuit opened for {target_id} after {current_count} failures",
                    extra={"circuit": self.name},
                )
    
    def get_state(
        self,
        target_id: str,
        direction: CircuitBreakerDirection = CircuitBreakerDirection.COORDINATOR_TO_AGENT,
    ) -> CircuitBreakerState:
        """Get current state for a target."""
        key = self._make_key(target_id, direction)
        return self._states.get(key, PerTargetState()).state
    
    def get_info(
        self,
        target_id: str,
        direction: CircuitBreakerDirection = CircuitBreakerDirection.COORDINATOR_TO_AGENT,
    ) -> CircuitBreakerInfo:
        """Get detailed state info for a target."""
        key = self._make_key(target_id, direction)
        state = self._states.get(key, PerTargetState())
        return CircuitBreakerInfo(
            name=self.name,
            direction=direction,
            state=state.state,
            failure_count=self._failure_count_in_window(state),
            last_failure_time=datetime.fromtimestamp(state.last_failure_time) if state.last_failure_time else None,
            last_state_change=state.last_state_change,
        )
    
    def get_all_states(self) -> Dict[str, CircuitBreakerInfo]:
        """Get all circuit breaker states."""
        states = {}
        for key, state in self._states.items():
            parts = key.split(":", 1)
            if len(parts) == 2:
                direction = CircuitBreakerDirection(parts[0])
                target_id = parts[1]
                states[key] = CircuitBreakerInfo(
                    name=self.name,
                    direction=direction,
                    state=state.state,
                    failure_count=self._failure_count_in_window(state),
                    last_failure_time=datetime.fromtimestamp(state.last_failure_time) if state.last_failure_time else None,
                    last_state_change=state.last_state_change,
                )
        return states
    
    def reset(self, target_id: Optional[str] = None) -> None:
        """
        Reset circuit breaker(s).
        
        Args:
            target_id: If provided, reset only this target. Otherwise reset all.
        """
        if target_id:
            for direction in CircuitBreakerDirection:
                key = self._make_key(target_id, direction)
                if key in self._states:
                    self._states[key] = PerTargetState()
                    logger.info(f"Circuit reset for {target_id}", extra={"circuit": self.name})
        else:
            self._states.clear()
            logger.info("All circuits reset", extra={"circuit": self.name})
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics."""
        open_count = sum(
            1 for s in self._states.values() if s.state == CircuitBreakerState.OPEN
        )
        half_open_count = sum(
            1 for s in self._states.values() if s.state == CircuitBreakerState.HALF_OPEN
        )
        
        return {
            "name": self.name,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "state_changes": self._state_changes,
            "open_circuits": open_count,
            "half_open_circuits": half_open_count,
            "closed_circuits": len(self._states) - open_count - half_open_count,
            "tracked_targets": len(self._states),
        }


class InMemoryCircuitBreakerStore:
    """
    In-memory store for circuit breaker state.
    
    For production, use Redis-based store for distributed deployments.
    """
    
    def __init__(self):
        self._breakers: Dict[str, TwoWayCircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(
        self,
        name: str,
        **kwargs,
    ) -> TwoWayCircuitBreaker:
        """Get existing or create new circuit breaker."""
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = TwoWayCircuitBreaker(name=name, **kwargs)
            return self._breakers[name]
    
    async def get(self, name: str) -> Optional[TwoWayCircuitBreaker]:
        """Get circuit breaker by name."""
        return self._breakers.get(name)
    
    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
    
    async def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all circuit breakers."""
        return {name: cb.get_metrics() for name, cb in self._breakers.items()}
