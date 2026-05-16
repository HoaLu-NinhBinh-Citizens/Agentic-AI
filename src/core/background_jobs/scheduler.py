"""Background job scheduler stub."""

import asyncio
from typing import Callable, Any
from datetime import datetime


class BackgroundScheduler:
    """Schedules background jobs."""
    
    def __init__(self):
        self._jobs: dict[str, asyncio.Task] = {}
    
    def schedule(self, name: str, func: Callable, interval: float) -> None:
        """Schedule a recurring job."""
        async def run_loop():
            while True:
                await func()
                await asyncio.sleep(interval)
        
        self._jobs[name] = asyncio.create_task(run_loop())
    
    def cancel(self, name: str) -> None:
        """Cancel a scheduled job."""
        if name in self._jobs:
            self._jobs[name].cancel()
