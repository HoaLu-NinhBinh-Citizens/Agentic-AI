"""
Runtime Backpressure - Cascade failure prevention

Prevents death spirals like:
  retrieval slow → queue buildup → orchestration retries → event storm → memory spike → collapse

Rules:
1. Every subsystem exports pressure state
2. Upstream must react to downstream pressure
3. Retries disabled under saturation
4. Low-priority tasks dropped first under shedding
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class BackpressureSignal(Enum):
    """Pressure level signals."""

    NORMAL = "normal"  # < 70% capacity
    DEGRADED = "degraded"  # 70-85% capacity
    SATURATED = "saturated"  # 85-95% capacity
    SHEDDING = "shedding"  # > 95% capacity


@dataclass
class PressureState:
    """Current pressure state of a subsystem."""

    signal: BackpressureSignal
    queue_depth: int
    processing_rate: float  # items/second
    capacity: int  # max capacity
    last_updated: float = field(default_factory=time.time)

    @property
    def utilization(self) -> float:
        """Current utilization as percentage."""
        if self.capacity == 0:
            return 0
        return self.queue_depth / self.capacity


@dataclass
class RetryStrategy:
    """Retry strategy based on pressure."""

    enabled: bool
    max_retries: int
    base_delay: float
    max_delay: float
    jitter: bool


class BackpressureManager:
    """
    Manages backpressure across subsystems.

    Prevents cascade failures by:
    1. Tracking pressure state of each subsystem
    2. Providing signals for upstream to react
    3. Adjusting retry strategies based on pressure

    Usage:
        manager = BackpressureManager()

        # Update subsystem pressure
        manager.update("retrieval", depth=80, rate=10.0, capacity=100)

        # Check if should retry
        if not manager.should_retry("retrieval"):
            return  # Don't retry, system overloaded

        # Check if should shed load
        if manager.should_reject("retrieval", priority=0):  # LOW
            return  # Reject low priority
    """

    def __init__(
        self,
        normal_threshold: float = 0.70,
        degraded_threshold: float = 0.85,
        saturated_threshold: float = 0.95,
    ):
        """
        Initialize backpressure manager.

        Args:
            normal_threshold: Utilization below this is NORMAL
            degraded_threshold: Utilization below this is DEGRADED
            saturated_threshold: Utilization below this is SATURATED
        """
        self._normal_threshold = normal_threshold
        self._degraded_threshold = degraded_threshold
        self._saturated_threshold = saturated_threshold

        self._states: dict[str, PressureState] = {}
        self._lock = asyncio.Lock()

        self._retry_strategies = {
            BackpressureSignal.NORMAL: RetryStrategy(
                enabled=True, max_retries=3, base_delay=1.0, max_delay=30.0, jitter=True
            ),
            BackpressureSignal.DEGRADED: RetryStrategy(
                enabled=True, max_retries=2, base_delay=2.0, max_delay=60.0, jitter=True
            ),
            BackpressureSignal.SATURATED: RetryStrategy(
                enabled=True, max_retries=1, base_delay=5.0, max_delay=120.0, jitter=True
            ),
            BackpressureSignal.SHEDDING: RetryStrategy(
                enabled=False, max_retries=0, base_delay=0, max_delay=0, jitter=False
            ),
        }

    def _calculate_signal(self, queue_depth: int, capacity: int) -> BackpressureSignal:
        """Calculate pressure signal from queue depth and capacity."""
        if capacity == 0:
            return BackpressureSignal.SHEDDING

        util = queue_depth / capacity

        if util >= self._saturated_threshold:
            return BackpressureSignal.SHEDDING
        elif util >= self._degraded_threshold:
            return BackpressureSignal.SATURATED
        elif util >= self._normal_threshold:
            return BackpressureSignal.DEGRADED
        return BackpressureSignal.NORMAL

    async def update(
        self,
        subsystem: str,
        queue_depth: int,
        processing_rate: float | None = None,
        capacity: int | None = None,
    ) -> PressureState:
        """
        Update pressure state for a subsystem.

        Args:
            subsystem: Name of subsystem (e.g., "retrieval", "llm")
            queue_depth: Current number of items in queue
            processing_rate: Items processed per second
            capacity: Maximum queue capacity

        Returns:
            Current PressureState
        """
        async with self._lock:
            # Get existing or default capacity
            if capacity is None:
                existing = self._states.get(subsystem)
                capacity = existing.capacity if existing else 100

            if processing_rate is None:
                existing = self._states.get(subsystem)
                processing_rate = existing.processing_rate if existing else 0

            signal = self._calculate_signal(queue_depth, capacity)

            state = PressureState(
                signal=signal,
                queue_depth=queue_depth,
                processing_rate=processing_rate,
                capacity=capacity,
                last_updated=time.time(),
            )

            old_state = self._states.get(subsystem)
            self._states[subsystem] = state

            # Log state changes
            if old_state and old_state.signal != signal:
                logger.warning(
                    f"Backpressure '{subsystem}': {old_state.signal.value} → {signal.value} "
                    f"(depth={queue_depth}/{capacity})"
                )

            return state

    def get_state(self, subsystem: str) -> PressureState | None:
        """Get pressure state of a subsystem."""
        return self._states.get(subsystem)

    def get_all_states(self) -> dict[str, PressureState]:
        """Get pressure states of all subsystems."""
        return dict(self._states)

    def should_retry(self, subsystem: str) -> bool:
        """
        Should we retry requests to this subsystem?

        Returns False when subsystem is overloaded and retries would make it worse.
        """
        state = self._states.get(subsystem)
        if not state:
            return True  # Unknown subsystem, allow retry

        strategy = self._retry_strategies.get(state.signal)
        return strategy.enabled if strategy else True

    def get_retry_strategy(self, subsystem: str) -> RetryStrategy:
        """Get retry strategy for subsystem based on current pressure."""
        state = self._states.get(subsystem)
        if not state:
            return self._retry_strategies[BackpressureSignal.NORMAL]

        strategy = self._retry_strategies.get(state.signal)
        return strategy or self._retry_strategies[BackpressureSignal.NORMAL]

    def should_reject(
        self,
        subsystem: str,
        priority: int = 1,
        threshold: int = 1,
    ) -> bool:
        """
        Should we reject new work to this subsystem?

        Args:
            subsystem: Name of subsystem
            priority: Priority of incoming work (0=LOW, 3=CRITICAL)
            threshold: Minimum priority to admit under load

        Returns:
            True if work should be rejected
        """
        state = self._states.get(subsystem)
        if not state:
            return False  # Unknown subsystem, accept

        # SHEDDING: Only admit high priority
        if state.signal == BackpressureSignal.SHEDDING:
            return priority < threshold

        # SATURATED: Only admit above threshold
        if state.signal == BackpressureSignal.SATURATED:
            return priority < threshold

        return False

    def should_backpressure_upstream(self, subsystem: str) -> bool:
        """
        Should we signal upstream to slow down?

        Returns True when downstream is getting overwhelmed.
        """
        state = self._states.get(subsystem)
        if not state:
            return False

        return state.signal in [
            BackpressureSignal.SATURATED,
            BackpressureSignal.SHEDDING,
        ]

    def get_shed_priority(self, subsystem: str) -> int:
        """
        Get minimum priority that will be admitted under shedding.

        Lower priority tasks will be dropped first.
        """
        state = self._states.get(subsystem)
        if not state or state.signal != BackpressureSignal.SHEDDING:
            return 0  # No shedding, admit all

        # Under shedding, only admit HIGH (2) and CRITICAL (3)
        return 2

    def is_healthy(self, subsystem: str) -> bool:
        """Check if subsystem is healthy (not under pressure)."""
        state = self._states.get(subsystem)
        if not state:
            return True  # Unknown is assumed healthy

        return state.signal == BackpressureSignal.NORMAL

    def is_degraded(self, subsystem: str) -> bool:
        """Check if subsystem is degraded."""
        state = self._states.get(subsystem)
        if not state:
            return False

        return state.signal != BackpressureSignal.NORMAL

    def get_stats(self) -> dict:
        """Get backpressure statistics."""
        return {
            subsystem: {
                "signal": state.signal.value,
                "queue_depth": state.queue_depth,
                "capacity": state.capacity,
                "utilization": f"{state.utilization:.1%}",
                "processing_rate": state.processing_rate,
                "last_updated": datetime.fromtimestamp(state.last_updated).isoformat(),
            }
            for subsystem, state in self._states.items()
        }


# Global backpressure manager
_backpressure_manager: BackpressureManager | None = None


def get_backpressure_manager() -> BackpressureManager:
    """Get or create default backpressure manager."""
    global _backpressure_manager
    if _backpressure_manager is None:
        _backpressure_manager = BackpressureManager()
    return _backpressure_manager


# Convenience alias
backpressure_manager = get_backpressure_manager()


# Integration helpers
async def retry_with_backpressure(
    subsystem: str,
    func,
    *args,
    max_retries: int | None = None,
    **kwargs,
):
    """
    Retry a function with backpressure-aware retry logic.

    Args:
        subsystem: Subsystem name for backpressure tracking
        func: Async function to retry
        *args: Arguments for func
        max_retries: Override max retries (uses backpressure strategy if None)
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Exception: If all retries exhausted
    """
    manager = get_backpressure_manager()
    strategy = manager.get_retry_strategy(subsystem)

    if not strategy.enabled:
        return await func(*args, **kwargs)

    retries = max_retries if max_retries is not None else strategy.max_retries

    last_error = None
    for attempt in range(retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < retries:
                # Check if we should continue retrying
                if not manager.should_retry(subsystem):
                    logger.warning(f"Backpressure: stopping retries for {subsystem}")
                    break

                # Calculate delay
                delay = min(
                    strategy.base_delay * (2**attempt),
                    strategy.max_delay,
                )
                if strategy.jitter:
                    import random

                    delay = delay * (0.5 + random.random())

                logger.warning(
                    f"Retry {attempt + 1}/{retries} for {subsystem} "
                    f"after {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)

    raise last_error
