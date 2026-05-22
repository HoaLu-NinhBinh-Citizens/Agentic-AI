"""Agent Scheduler - priority, fairness, backpressure scheduling.

Provides scheduling capabilities for agent execution:
- Priority-based scheduling
- Fair share allocation
- Backpressure handling
- Queue management
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PriorityLevel(int, Enum):
    """Priority levels for scheduling."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class SchedulingPolicy(str, Enum):
    """Scheduling policies."""

    PRIORITY = "priority"
    FAIR_SHARE = "fair_share"
    FIFO = "fifo"
    ROUND_ROBIN = "round_robin"


@dataclass
class ScheduledTask:
    """A task in the scheduler queue."""

    task_id: str
    priority: PriorityLevel
    created_at: int
    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3

    def __lt__(self, other: "ScheduledTask") -> bool:
        """Compare tasks by priority for heap ordering."""
        return self.priority > other.priority


@dataclass
class SchedulingResult:
    """Result of a scheduling operation."""

    task_id: str
    success: bool
    position: int = -1
    reason: str = ""


class AgentScheduler:
    """Scheduler for agent execution with priority and fairness.

    Features:
    - Priority-based scheduling
    - Fair share allocation
    - Backpressure handling
    - Task queue management
    """

    def __init__(
        self,
        policy: SchedulingPolicy = SchedulingPolicy.PRIORITY,
        max_queue_size: int = 1000,
        backpressure_threshold: float = 0.8,
    ) -> None:
        """Initialize scheduler.

        Args:
            policy: Scheduling policy.
            max_queue_size: Maximum queue size before backpressure.
            backpressure_threshold: Threshold (0-1) for triggering backpressure.
        """
        self._policy = policy
        self._max_queue_size = max_queue_size
        self._backpressure_threshold = backpressure_threshold
        self._queue: deque[ScheduledTask] = deque()
        self._priority_queues: dict[PriorityLevel, list[ScheduledTask]] = {
            PriorityLevel.CRITICAL: [],
            PriorityLevel.HIGH: [],
            PriorityLevel.NORMAL: [],
            PriorityLevel.LOW: [],
        }
        self._lock = asyncio.Lock()
        self._backpressure_active = False
        self._total_scheduled = 0
        self._total_completed = 0
        self._fair_share_counters: dict[str, int] = {}

    @property
    def policy(self) -> SchedulingPolicy:
        """Get scheduling policy."""
        return self._policy

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue) + sum(len(q) for q in self._priority_queues.values())

    @property
    def backpressure_active(self) -> bool:
        """Check if backpressure is active."""
        return self._backpressure_active

    async def submit(
        self,
        task_id: str,
        payload: Any,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> SchedulingResult:
        """Submit a task for scheduling.

        Args:
            task_id: Unique task identifier.
            payload: Task payload.
            priority: Task priority.
            metadata: Optional task metadata.

        Returns:
            SchedulingResult with submission status.
        """
        async with self._lock:
            self._update_backpressure()

            if self._backpressure_active and priority < PriorityLevel.HIGH:
                return SchedulingResult(
                    task_id=task_id,
                    success=False,
                    reason="Backpressure active: queue overloaded",
                )

            if self.queue_size >= self._max_queue_size:
                return SchedulingResult(
                    task_id=task_id,
                    success=False,
                    reason=f"Queue full: {self.queue_size}/{self._max_queue_size}",
                )

            task = ScheduledTask(
                task_id=task_id,
                priority=priority,
                created_at=int(time.time()),
                payload=payload,
                metadata=metadata or {},
            )

            if self._policy == SchedulingPolicy.PRIORITY:
                self._priority_queues[priority].append(task)
            else:
                self._queue.append(task)

            self._total_scheduled += 1
            position = self.queue_size

            logger.debug(
                "Task submitted: id=%s priority=%s position=%d",
                task_id,
                priority.name,
                position,
            )

            return SchedulingResult(
                task_id=task_id,
                success=True,
                position=position,
            )

    async def next(self) -> ScheduledTask | None:
        """Get the next task according to scheduling policy.

        Returns:
            Next scheduled task or None if queue is empty.
        """
        async with self._lock:
            if self._policy == SchedulingPolicy.PRIORITY:
                return self._get_next_priority()

            if self._policy == SchedulingPolicy.FAIR_SHARE:
                return self._get_next_fair_share()

            if self._queue:
                return self._queue.popleft()

            return None

    def _get_next_priority(self) -> ScheduledTask | None:
        """Get next task using priority scheduling."""
        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.NORMAL, PriorityLevel.LOW]:
            if self._priority_queues[priority]:
                return self._priority_queues[priority].pop(0)

        return None

    def _get_next_fair_share(self) -> ScheduledTask | None:
        """Get next task using fair share scheduling."""
        for queue in self._priority_queues.values():
            if queue:
                task = queue.pop(0)
                counter_key = task.metadata.get("client_id", "default")
                self._fair_share_counters[counter_key] = self._fair_share_counters.get(counter_key, 0) + 1
                return task

        return None

    async def complete(self, task_id: str) -> bool:
        """Mark a task as completed.

        Args:
            task_id: Completed task identifier.

        Returns:
            True if task was found and marked.
        """
        async with self._lock:
            self._total_completed += 1
            self._update_backpressure()
            logger.debug("Task completed: id=%s", task_id)
            return True

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task.

        Args:
            task_id: Task identifier to cancel.

        Returns:
            True if task was found and cancelled.
        """
        async with self._lock:
            for queue in [self._queue] + list(self._priority_queues.values()):
                for i, task in enumerate(queue):
                    if task.task_id == task_id:
                        queue.pop(i)
                        logger.info("Task cancelled: id=%s", task_id)
                        return True

            return False

    async def requeue(self, task_id: str) -> bool:
        """Requeue a failed task for retry.

        Args:
            task_id: Task identifier to requeue.

        Returns:
            True if task was found and requeued.
        """
        async with self._lock:
            for queue in [self._queue] + list(self._priority_queues.values()):
                for i, task in enumerate(queue):
                    if task.task_id == task_id:
                        if task.attempts >= task.max_attempts:
                            logger.warning("Task max attempts reached: id=%s", task_id)
                            return False

                        task.attempts += 1
                        logger.info(
                            "Task requeued: id=%s attempt=%d/%d",
                            task_id,
                            task.attempts,
                            task.max_attempts,
                        )
                        return True

            return False

    def _update_backpressure(self) -> None:
        """Update backpressure state based on queue size."""
        utilization = self.queue_size / self._max_queue_size if self._max_queue_size > 0 else 0

        was_active = self._backpressure_active
        self._backpressure_active = utilization >= self._backpressure_threshold

        if self._backpressure_active and not was_active:
            logger.warning(
                "Backpressure activated: queue=%d/%d (%.1f%%)",
                self.queue_size,
                self._max_queue_size,
                utilization * 100,
            )
        elif not self._backpressure_active and was_active:
            logger.info("Backpressure deactivated: queue=%d/%d", self.queue_size, self._max_queue_size)

    async def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "policy": self._policy.value,
            "queue_size": self.queue_size,
            "max_queue_size": self._max_queue_size,
            "backpressure_active": self._backpressure_active,
            "total_scheduled": self._total_scheduled,
            "total_completed": self._total_completed,
            "pending": self.queue_size,
            "priority_queues": {
                p.name: len(q) for p, q in self._priority_queues.items()
            },
            "utilization": self.queue_size / self._max_queue_size if self._max_queue_size > 0 else 0,
        }

    async def clear(self) -> int:
        """Clear all queued tasks.

        Returns:
            Number of tasks cleared.
        """
        async with self._lock:
            count = self.queue_size
            self._queue.clear()
            for queue in self._priority_queues.values():
                queue.clear()
            logger.info("Scheduler cleared: tasks=%d", count)
            return count
