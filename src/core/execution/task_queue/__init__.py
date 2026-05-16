"""Task queue module."""

import asyncio
from typing import Any


class TaskQueue:
    """Task execution queue."""
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
    
    async def enqueue(self, task: dict[str, Any]) -> None:
        """Enqueue task."""
        await self._queue.put(task)
    
    async def dequeue(self) -> dict[str, Any]:
        """Dequeue task."""
        return await self._queue.get()
