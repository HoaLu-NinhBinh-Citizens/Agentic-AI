"""Dead letter queue stub."""

from typing import Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FailedTask:
    """Task that failed processing."""
    
    task: dict[str, Any]
    error: str
    timestamp: datetime = field(default_factory=datetime.now)
    attempts: int = 0


class DeadLetterQueue:
    """Queue for failed tasks."""
    
    def __init__(self):
        self._queue: list[FailedTask] = []
    
    def add(self, task: dict[str, Any], error: Exception) -> None:
        """Add a failed task to the queue."""
        self._queue.append(FailedTask(task=task, error=str(error)))
    
    def get_failed(self) -> list[FailedTask]:
        """Get all failed tasks."""
        return self._queue.copy()
