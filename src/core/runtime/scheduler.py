"""Scheduler stub."""

import asyncio
from typing import Any, Callable


class Scheduler:
    """Task scheduler for managing execution order."""
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
    
    async def schedule(self, task: Callable, *args: Any) -> None:
        """Schedule a task for execution."""
        await self._queue.put((task, args))
    
    async def run(self) -> None:
        """Run scheduled tasks."""
        while True:
            task, args = await self._queue.get()
            await task(*args)
