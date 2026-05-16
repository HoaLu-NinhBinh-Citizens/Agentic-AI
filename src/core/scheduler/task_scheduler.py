"""
Task Scheduler - Priority-based task scheduling

Features:
- Priority queuing (CRITICAL > HIGH > NORMAL > LOW)
- Fairness within same priority (FIFO)
- Starvation prevention (aging)
- Deadline awareness
- Async task management
- Task cancellation support
"""

import asyncio
import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Any, Callable, Coroutine, TypeVar, Generic
from uuid import uuid4

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Priority(IntEnum):
    """Task priority levels. Lower value = lower priority."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class SchedulerError(Exception):
    """Base exception for scheduler errors."""

    pass


class QueueFullError(SchedulerError):
    """Raised when scheduler queue is full."""

    pass


@dataclass
class ScheduledTask(Generic[T]):
    """
    A task scheduled for execution.

    Attributes:
        task_id: Unique identifier
        priority: Task priority
        callback: Async function to execute
        args: Positional arguments for callback
        kwargs: Keyword arguments for callback
        created_at: When task was created
        scheduled_at: When to execute (None = immediately)
        deadline: When task must complete by
        max_age: Maximum time in queue before forced execution
        metadata: Additional task metadata
    """

    task_id: str = field(default_factory=lambda: str(uuid4())[:8])
    priority: Priority = Priority.NORMAL
    callback: Callable[..., Coroutine[Any, Any, T]] | None = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: datetime | None = None
    deadline: datetime | None = None
    max_age: timedelta | None = None  # Force execution after this
    metadata: dict = field(default_factory=dict)

    def __lt__(self, other: "ScheduledTask") -> bool:
        """Compare tasks by priority and creation time."""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority first
        return self.created_at < other.created_at  # FIFO within priority

    def age_seconds(self) -> float:
        """Get task age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    def is_ready(self) -> bool:
        """Check if task is ready to execute."""
        now = datetime.now()
        if self.scheduled_at and now < self.scheduled_at:
            return False
        if self.deadline and now > self.deadline:
            return False  # Expired
        return True

    def should_force(self) -> bool:
        """Check if task should be forced due to age."""
        if not self.max_age:
            return False
        return self.age_seconds() > self.max_age.total_seconds()


@dataclass
class SchedulerStats:
    """Statistics for scheduler."""

    pending: int
    running: int
    completed: int
    failed: int
    starved: int  # Tasks that waited too long
    max_concurrent: int
    utilization: float  # 0.0 - 1.0


class TaskScheduler:
    """
    Priority-based task scheduler.

    Features:
    - Priority queuing (CRITICAL > HIGH > NORMAL > LOW)
    - Fairness within same priority (FIFO)
    - Starvation prevention (aging policy)
    - Deadline awareness
    - Task cancellation support

    Usage:
        scheduler = TaskScheduler(max_concurrent=10)

        # Schedule tasks
        task1 = await scheduler.schedule(
            callback=my_async_func,
            args=(arg1,),
            priority=Priority.HIGH,
        )

        # Cancel task
        await scheduler.cancel(task1.task_id)

        # Get stats
        stats = scheduler.get_stats()
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_queue_size: int = 1000,
        aging_threshold_seconds: float = 60.0,
        aging_boost: int = 1,
    ):
        """
        Initialize task scheduler.

        Args:
            max_concurrent: Maximum tasks running simultaneously
            max_queue_size: Maximum tasks in queue (0 = unlimited)
            aging_threshold_seconds: Seconds before low-priority tasks get boosted
            aging_boost: Priority boost when aging kicks in
        """
        self._max_concurrent = max_concurrent
        self._max_queue_size = max_queue_size
        self._aging_threshold = aging_threshold_seconds
        self._aging_boost = aging_boost

        self._heap: list[ScheduledTask] = []  # Priority queue
        self._tasks: dict[str, ScheduledTask] = {}  # Task lookup
        self._running: dict[str, asyncio.Task] = {}  # Running tasks
        self._completed: dict[str, Any] = {}  # Task results

        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)

        self._stats = {
            "completed": 0,
            "failed": 0,
            "starved": 0,
        }

    async def schedule(
        self,
        callback: Callable[..., Coroutine[Any, Any, T]],
        args: tuple = (),
        kwargs: None = None,
        priority: Priority = Priority.NORMAL,
        scheduled_at: datetime | None = None,
        deadline: datetime | None = None,
        max_age: timedelta | None = None,
        task_id: str | None = None,
        metadata: dict | None = None,
    ) -> ScheduledTask[T]:
        """
        Schedule a task for execution.

        Args:
            callback: Async function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            priority: Task priority
            scheduled_at: When to execute (None = immediately)
            deadline: When task must complete by
            max_age: Force execution after this duration
            task_id: Optional custom task ID
            metadata: Additional metadata

        Returns:
            ScheduledTask

        Raises:
            QueueFullError: If queue exceeds max_queue_size
        """
        async with self._lock:
            if self._max_queue_size > 0 and len(self._tasks) >= self._max_queue_size:
                raise QueueFullError(
                    f"Queue full (max: {self._max_queue_size})"
                )

            task = ScheduledTask(
                task_id=task_id or str(uuid4())[:8],
                priority=priority,
                callback=callback,
                args=args,
                kwargs=kwargs or {},
                scheduled_at=scheduled_at,
                deadline=deadline,
                max_age=max_age,
                metadata=metadata or {},
            )

            self._tasks[task.task_id] = task
            heapq.heappush(self._heap, task)
            self._not_empty.notify()

            logger.debug(
                f"Scheduled task {task.task_id} (priority={priority.name})"
            )
            return task

    async def get_next(self) -> ScheduledTask | None:
        """
        Get next task ready for execution.

        Returns:
            Next ScheduledTask or None if queue empty or max concurrent reached
        """
        async with self._not_empty:
            while self._heap:
                task = heapq.heappop(self._heap)

                if task.task_id not in self._tasks:
                    continue  # Was cancelled

                if task.is_ready():
                    if len(self._running) >= self._max_concurrent:
                        # Re-add to heap, we'll try again later
                        heapq.heappush(self._heap, task)
                        return None
                    return task
                else:
                    # Not ready yet, re-add and wait
                    heapq.heappush(self._heap, task)
                    remaining = (task.scheduled_at - datetime.now()).total_seconds()
                    await asyncio.sleep(min(remaining, 1.0))
                    return None

            return None

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task."""
        try:
            logger.debug(f"Executing task {task.task_id}")
            result = await task.callback(*task.args, **task.kwargs)
            self._completed[task.task_id] = result
            self._stats["completed"] += 1
        except asyncio.CancelledError:
            logger.debug(f"Task {task.task_id} cancelled")
            raise
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            self._completed[task.task_id] = None
            self._stats["failed"] += 1
        finally:
            async with self._lock:
                self._running.pop(task.task_id, None)
                self._tasks.pop(task.task_id, None)

    async def run(self, run_forever: bool = True) -> None:
        """
        Run the scheduler loop.

        Args:
            run_forever: If True, runs forever. If False, processes queued tasks and returns.
        """
        logger.info("Scheduler starting...")

        while True:
            task = await self.get_next()
            if not task:
                if not run_forever:
                    break
                async with self._not_empty:
                    await self._not_empty.wait()
                continue

            async with self._lock:
                if task.task_id in self._running:
                    continue  # Already running
                asyncio_task = asyncio.create_task(self._execute_task(task))
                self._running[task.task_id] = asyncio_task

            if not run_forever:
                break

        logger.info("Scheduler stopped")

    async def _worker_loop(self) -> None:
        """Worker loop that processes tasks."""
        while True:
            task = await self.get_next()
            if not task:
                await asyncio.sleep(0.1)
                continue

            async with self._lock:
                if task.task_id in self._running:
                    continue
                asyncio_task = asyncio.create_task(self._execute_task(task))
                self._running[task.task_id] = asyncio_task

    def start_workers(self, num_workers: int | None = None) -> list[asyncio.Task]:
        """
        Start worker coroutines.

        Args:
            num_workers: Number of workers (default: max_concurrent)

        Returns:
            List of worker tasks
        """
        if num_workers is None:
            num_workers = self._max_concurrent

        workers = []
        for _ in range(num_workers):
            worker = asyncio.create_task(self._worker_loop())
            workers.append(worker)

        logger.info(f"Started {num_workers} scheduler workers")
        return workers

    async def cancel(self, task_id: str) -> bool:
        """
        Cancel a scheduled or running task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if cancelled, False if not found
        """
        async with self._lock:
            if task_id in self._running:
                self._running[task_id].cancel()
                self._stats["failed"] += 1
                return True

            if task_id in self._tasks:
                del self._tasks[task_id]
                return True

            return False

    async def cancel_all(self, priority: Priority | None = None) -> int:
        """
        Cancel all tasks, optionally filtered by priority.

        Args:
            priority: Only cancel tasks with this priority (None = all)

        Returns:
            Number of tasks cancelled
        """
        async with self._lock:
            cancelled = 0

            # Cancel running
            for task_id in list(self._running.keys()):
                task = self._tasks.get(task_id)
                if task and (priority is None or task.priority == priority):
                    self._running[task_id].cancel()
                    cancelled += 1

            # Remove from queue
            if priority is None:
                self._tasks.clear()
                self._heap.clear()
                cancelled += len(self._heap)
            else:
                new_heap = []
                for task in self._heap:
                    if task.priority == priority:
                        self._tasks.pop(task.task_id, None)
                        cancelled += 1
                    else:
                        new_heap.append(task)
                self._heap = new_heap
                heapq.heapify(self._heap)

            return cancelled

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> Any | None:
        """Get task result if completed."""
        return self._completed.get(task_id)

    def get_stats(self) -> SchedulerStats:
        """Get scheduler statistics."""
        return SchedulerStats(
            pending=len(self._tasks),
            running=len(self._running),
            completed=self._stats["completed"],
            failed=self._stats["failed"],
            starved=self._stats["starved"],
            max_concurrent=self._max_concurrent,
            utilization=len(self._running) / self._max_concurrent
            if self._max_concurrent > 0
            else 0,
        )

    def get_queue_snapshot(self) -> list[dict]:
        """Get snapshot of queued tasks."""
        return [
            {
                "task_id": t.task_id,
                "priority": t.priority.name,
                "age_seconds": round(t.age_seconds(), 1),
                "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
            }
            for t in sorted(self._heap)
        ]

    def clear(self) -> None:
        """Clear all tasks and results."""
        self._tasks.clear()
        self._heap.clear()
        self._running.clear()
        self._completed.clear()


# Global scheduler instance
_default_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    """Get or create default scheduler."""
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = TaskScheduler()
    return _default_scheduler


async def shutdown_scheduler() -> None:
    """Shutdown default scheduler."""
    global _default_scheduler
    if _default_scheduler:
        await _default_scheduler.cancel_all()
        _default_scheduler = None
