"""
Task Scheduler - Priority-based task scheduling

Provides:
- Priority queuing (CRITICAL > HIGH > NORMAL > LOW)
- Fairness within same priority (FIFO)
- Starvation prevention (aging for long-waiting tasks)
- Deadline awareness
- Async task management
"""

from .task_scheduler import (
    Priority,
    ScheduledTask,
    TaskScheduler,
    SchedulerStats,
    QueueFullError,
    SchedulerError,
)

__all__ = [
    "Priority",
    "ScheduledTask",
    "TaskScheduler",
    "SchedulerStats",
    "QueueFullError",
    "SchedulerError",
]
