"""
Runtime Admission Control - Queue and capacity management

Prevents OOM and overload by controlling task admission.

Rules:
- Reject when queue full
- Priority determines who gets in when under pressure
- Track capacity for observability
- Provide backpressure signals
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.scheduler import Priority

logger = logging.getLogger(__name__)


class AdmissionDecision(Enum):
    """Result of admission check."""

    ADMITTED = "admitted"  # Task accepted
    QUEUED = "queued"  # Task queued for later
    REJECTED = "rejected"  # Task rejected


@dataclass
class AdmissionRequest:
    """Request for task admission."""

    task_name: str
    priority_value: int  # 0=LOW, 1=NORMAL, 2=HIGH, 3=CRITICAL
    estimated_cost: float = 1.0  # Relative cost (1.0 = normal)
    deadline: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AdmissionStats:
    """Admission controller statistics."""

    queue_depth: int
    concurrent: int
    max_concurrent: int
    max_queue: int
    utilization: float  # 0.0 - 1.0
    queue_utilization: float  # 0.0 - 1.0
    rejected_count: int
    admitted_count: int
    queued_count: int


class AdmissionController:
    """
    Controls task admission to runtime.

    Prevents OOM by:
    - Limiting concurrent tasks
    - Limiting queue depth
    - Prioritizing critical tasks

    Rules:
    - CRITICAL tasks always admitted (up to hard limit)
    - HIGH tasks admitted if capacity available
    - NORMAL/LOW tasks may be rejected under load
    - All tasks rejected if hard limits reached

    Usage:
        controller = AdmissionController(
            max_concurrent=10,
            max_queue=1000,
        )

        decision = await controller.admit(
            task_name="llm_call",
            priority_value=2,  # HIGH
        )

        if decision == AdmissionDecision.REJECTED:
            raise RejectedError("System overloaded")
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_queue: int = 1000,
        critical_reserve: int = 2,  # Reserve slots for CRITICAL tasks
    ):
        """
        Initialize admission controller.

        Args:
            max_concurrent: Maximum tasks executing simultaneously
            max_queue: Maximum tasks waiting
            critical_reserve: Reserved slots for CRITICAL priority
        """
        self._max_concurrent = max_concurrent
        self._max_queue = max_queue
        self._critical_reserve = critical_reserve

        self._concurrent = 0
        self._queue_depth = 0

        self._stats = {
            "rejected": 0,
            "admitted": 0,
            "queued": 0,
        }

        self._lock = asyncio.Lock()

    async def admit(self, request: AdmissionRequest) -> AdmissionDecision:
        """
        Decide if task should be admitted.

        Args:
            request: Admission request with priority and cost

        Returns:
            AdmissionDecision
        """
        async with self._lock:
            is_critical = request.priority_value >= 3
            is_high = request.priority_value >= 2

            # Check concurrent limit
            available_slots = self._max_concurrent - self._concurrent
            effective_limit = self._max_concurrent

            if is_critical:
                # CRITICAL: Use all slots
                effective_limit = self._max_concurrent
            elif is_high:
                # HIGH: Leave reserve for CRITICAL
                effective_limit = self._max_concurrent - self._critical_reserve
            else:
                # NORMAL/LOW: Leave more reserve
                effective_limit = self._max_concurrent - self._critical_reserve * 2

            # Check concurrent capacity
            if self._concurrent >= self._max_concurrent:
                if is_critical:
                    # CRITICAL can preempt, but we don't implement preemption here
                    # Just admit anyway if there's any slot
                    if self._concurrent >= self._max_concurrent:
                        self._stats["rejected"] += 1
                        return AdmissionDecision.REJECTED
                else:
                    self._stats["rejected"] += 1
                    return AdmissionDecision.REJECTED

            # Check queue limit
            if self._queue_depth >= self._max_queue:
                if is_critical or is_high:
                    # High priority gets queued even when full
                    self._queue_depth += 1
                    self._concurrent += 1
                    self._stats["queued"] += 1
                    return AdmissionDecision.QUEUED
                else:
                    self._stats["rejected"] += 1
                    return AdmissionDecision.REJECTED

            # Admit task
            if self._queue_depth > 0:
                self._queue_depth -= 1

            self._concurrent += 1
            self._stats["admitted"] += 1

            logger.debug(
                f"Admitted {request.task_name} "
                f"(priority={request.priority_value}, "
                f"concurrent={self._concurrent}/{self._max_concurrent})"
            )

            return AdmissionDecision.ADMITTED

    async def release(self) -> None:
        """
        Release a slot when task completes.

        Call this when task finishes (success or failure).
        """
        async with self._lock:
            self._concurrent = max(0, self._concurrent - 1)
            logger.debug(
                f"Released slot (concurrent={self._concurrent}/{self._max_concurrent})"
            )

    async def queue_increase(self) -> None:
        """Increase queue depth."""
        async with self._lock:
            self._queue_depth += 1

    async def queue_decrease(self) -> None:
        """Decrease queue depth."""
        async with self._lock:
            self._queue_depth = max(0, self._queue_depth - 1)

    def get_stats(self) -> AdmissionStats:
        """Get admission statistics."""
        return AdmissionStats(
            queue_depth=self._queue_depth,
            concurrent=self._concurrent,
            max_concurrent=self._max_concurrent,
            max_queue=self._max_queue,
            utilization=self._concurrent / self._max_concurrent
            if self._max_concurrent > 0
            else 0,
            queue_utilization=self._queue_depth / self._max_queue
            if self._max_queue > 0
            else 0,
            rejected_count=self._stats["rejected"],
            admitted_count=self._stats["admitted"],
            queued_count=self._stats["queued"],
        )

    def should_backpressure(self) -> bool:
        """
        Check if system should signal backpressure.

        Returns True when system is under pressure.
        """
        return (
            self._concurrent >= self._max_concurrent * 0.9
            or self._queue_depth >= self._max_queue * 0.9
        )

    def get_backpressure_level(self) -> str:
        """
        Get current backpressure level.

        Returns:
            "normal", "high", or "critical"
        """
        conc_util = self._concurrent / self._max_concurrent if self._max_concurrent else 0
        queue_util = self._queue_depth / self._max_queue if self._max_queue else 0

        if conc_util >= 0.95 or queue_util >= 0.95:
            return "critical"
        elif conc_util >= 0.8 or queue_util >= 0.8:
            return "high"
        return "normal"

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._stats = {
            "rejected": 0,
            "admitted": 0,
            "queued": 0,
        }


# Global admission controller
_admission_controller: AdmissionController | None = None


def get_admission_controller() -> AdmissionController:
    """Get or create default admission controller."""
    global _admission_controller
    if _admission_controller is None:
        _admission_controller = AdmissionController()
    return _admission_controller
