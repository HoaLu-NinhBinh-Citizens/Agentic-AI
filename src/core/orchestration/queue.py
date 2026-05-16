"""
Task Queue

Priority-based task queue for workflow orchestration.
"""

import asyncio
import heapq
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Task priority levels."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
    """
    Task in the queue.

    Attributes:
        id: Unique task identifier
        name: Task name
        data: Task data/payload
        priority: Task priority
        created_at: When task was created
        scheduled_at: When to execute (for delayed tasks)
        expires_at: When task expires
        retries: Number of retries remaining
        metadata: Additional metadata
        callbacks: Completion callbacks
    """

    id: str
    name: str
    data: Any
    priority: Priority = Priority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    callbacks: List[Callable] = field(default_factory=list)

    def __lt__(self, other: "Task") -> bool:
        """Compare tasks by priority and creation time."""
        if self.priority != other.priority:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at

    def is_ready(self) -> bool:
        """Check if task is ready to execute."""
        now = datetime.now()

        # Check scheduled time
        if self.scheduled_at and now < self.scheduled_at:
            return False

        # Check expiration
        if self.expires_at and now > self.expires_at:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority.name,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "retries": self.retries,
            "metadata": self.metadata,
        }


@dataclass
class TaskResult:
    """Result of task execution."""

    task_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "executed_at": self.executed_at.isoformat(),
            "duration_ms": self.duration_ms,
        }


class TaskQueue:
    """
    Priority-based task queue.

    Features:
    - Priority queuing (CRITICAL > HIGH > NORMAL > LOW)
    - Delayed task scheduling
    - Task expiration
    - Retry support
    - Batch processing
    - Async operation

    Usage:
        queue = TaskQueue()

        # Enqueue tasks
        queue.enqueue(Task(name="task1", data={...}))
        queue.enqueue(Task(name="task2", data={...}, priority=Priority.HIGH))

        # Dequeue
        task = queue.dequeue()
        if task:
            execute(task)

        # Batch dequeue
        tasks = queue.dequeue_batch(10)
    """

    def __init__(self, max_size: int = 0):
        """
        Initialize task queue.

        Args:
            max_size: Maximum queue size (0 = unlimited)
        """
        self.max_size = max_size
        self._heap: List[Task] = []  # Priority heap
        self._deque: deque = deque()  # FIFO for same priority
        self._tasks: Dict[str, Task] = {}  # Task lookup
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)

    async def enqueue(
        self,
        name: str,
        data: Any,
        priority: Priority = Priority.NORMAL,
        scheduled_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        Add a task to the queue.

        Args:
            name: Task name
            data: Task data
            priority: Task priority
            scheduled_at: When to execute
            expires_at: When task expires
            retries: Number of retries
            metadata: Additional metadata

        Returns:
            Created task
        """
        async with self._lock:
            # Check size limit
            if self.max_size > 0 and len(self._tasks) >= self.max_size:
                raise QueueFullError(f"Queue is full (max: {self.max_size})")

            task = Task(
                id=str(uuid4()),
                name=name,
                data=data,
                priority=priority,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                retries=retries,
                metadata=metadata or {},
            )

            # Store task
            self._tasks[task.id] = task

            # Add to appropriate structure
            if scheduled_at:
                # Delayed task - add to heap with scheduled time as sort key
                heapq.heappush(self._heap, (scheduled_at, task))
            else:
                # Immediate task - add to heap and deque
                heapq.heappush(self._heap, (task.created_at, task))
                self._deque.append(task)

            # Notify waiting consumers
            self._not_empty.notify()

            logger.debug(f"Enqueued task: {task.name} (priority={priority.name})")
            return task

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        Remove and return the highest priority task.

        Args:
            timeout: Wait timeout in seconds (None = wait forever)

        Returns:
            Task or None if queue is empty (with timeout)
        """
        async with self._not_empty:
            # Wait for task
            deadline = None
            if timeout:
                deadline = asyncio.get_event_loop().time() + timeout

            while True:
                # Check for ready task
                task = self._get_ready_task()
                if task:
                    return task

                # Check timeout
                if deadline:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        return None

                    try:
                        await asyncio.wait_for(
                            self._not_empty.wait(),
                            timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        return None
                else:
                    await self._not_empty.wait()

    def dequeue_sync(self) -> Optional[Task]:
        """
        Synchronous dequeue (non-blocking).

        Returns:
            Task or None
        """
        return self._get_ready_task()

    def _get_ready_task(self) -> Optional[Task]:
        """Get a ready task from the queue."""
        now = datetime.now()

        # Check heap for scheduled tasks
        while self._heap:
            scheduled_time, task = self._heap[0]

            # Skip if task was removed
            if task.id not in self._tasks:
                heapq.heappop(self._heap)
                continue

            # Check if ready
            if task.scheduled_at and now < task.scheduled_at:
                break  # Not ready yet

            # Check expiration
            if task.expires_at and now > task.expires_at:
                heapq.heappop(self._heap)
                del self._tasks[task.id]
                logger.debug(f"Task expired: {task.name}")
                continue

            # Found ready task
            heapq.heappop(self._heap)
            return self._tasks.pop(task.id)

        return None

    async def dequeue_batch(self, batch_size: int = 10) -> List[Task]:
        """
        Dequeue multiple tasks.

        Args:
            batch_size: Maximum number of tasks

        Returns:
            List of tasks
        """
        tasks = []

        async with self._lock:
            for _ in range(batch_size):
                task = self._get_ready_task()
                if not task:
                    break
                tasks.append(task)

        return tasks

    async def requeue(self, task: Task) -> None:
        """
        Put a task back in the queue.

        Args:
            task: Task to requeue
        """
        async with self._lock:
            # Decrement retries
            task.retries -= 1

            if task.retries < 0:
                logger.debug(f"Task {task.name} out of retries")
                return

            # Store task
            self._tasks[task.id] = task

            # Add back to heap
            scheduled = task.scheduled_at or task.created_at
            heapq.heappush(self._heap, (scheduled, task))
            self._deque.append(task)

            self._not_empty.notify()
            logger.debug(f"Requeued task: {task.name} (retries left: {task.retries})")

    async def cancel(self, task_id: str) -> bool:
        """
        Cancel a task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if cancelled, False if not found
        """
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.debug(f"Cancelled task: {task_id}")
                return True
            return False

    def get(self, task_id: str) -> Optional[Task]:
        """
        Get a task without removing it.

        Args:
            task_id: Task ID

        Returns:
            Task or None
        """
        return self._tasks.get(task_id)

    def size(self) -> int:
        """Get number of tasks in queue."""
        return len(self._tasks)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._tasks) == 0

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks.clear()
        self._heap.clear()
        self._deque.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "size": len(self._tasks),
            "max_size": self.max_size,
            "priority_counts": {
                "critical": sum(1 for t in self._tasks.values() if t.priority == Priority.CRITICAL),
                "high": sum(1 for t in self._tasks.values() if t.priority == Priority.HIGH),
                "normal": sum(1 for t in self._tasks.values() if t.priority == Priority.NORMAL),
                "low": sum(1 for t in self._tasks.values() if t.priority == Priority.LOW),
            },
        }

    def peek(self) -> Optional[Task]:
        """Peek at next task without removing."""
        if self._heap:
            _, task = self._heap[0]
            return task
        return None

    def list_tasks(self) -> List[Task]:
        """List all tasks."""
        return list(self._tasks.values())

    async def wait_for_task(self, task_id: str, timeout: float = 60.0) -> Optional[TaskResult]:
        """
        Wait for a specific task to complete.

        Args:
            task_id: Task ID
            timeout: Wait timeout

        Returns:
            Task result or None
        """
        start_time = asyncio.get_event_loop().time()
        deadline = start_time + timeout

        while asyncio.get_event_loop().time() < deadline:
            if task_id not in self._tasks:
                # Task completed or cancelled
                return None

            remaining = deadline - asyncio.get_event_loop().time()
            await asyncio.sleep(min(remaining, 0.1))

        return None


class QueueFullError(Exception):
    """Queue is full."""
    pass


class QueueEmptyError(Exception):
    """Queue is empty."""
    pass


# Decorator for queue-based functions
def queued(queue: TaskQueue, priority: Priority = Priority.NORMAL):
    """
    Decorator to enqueue function calls.

    Usage:
        @queued(my_queue, priority=Priority.HIGH)
        async def my_function(data):
            return process(data)
    """

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            task_data = {"func": func.__name__, "args": args, "kwargs": kwargs}
            await queue.enqueue(
                name=func.__name__,
                data=task_data,
                priority=priority,
            )

        async def async_wrapper(*args, **kwargs):
            task_data = {"func": func.__name__, "args": args, "kwargs": kwargs}
            await queue.enqueue(
                name=func.__name__,
                data=task_data,
                priority=priority,
            )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
