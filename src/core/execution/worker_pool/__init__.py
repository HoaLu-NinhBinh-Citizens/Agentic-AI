"""Worker pool module."""

from typing import Any
from .worker import Worker


class WorkerPool:
    """Pool of workers."""
    
    def __init__(self, size: int = 4):
        self._workers = [Worker(f"worker_{i}") for i in range(size)]
    
    def get_worker(self) -> Worker:
        """Get available worker."""
        for worker in self._workers:
            if not worker._busy:
                return worker
        return self._workers[0]
