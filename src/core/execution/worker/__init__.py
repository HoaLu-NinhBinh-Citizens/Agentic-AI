"""Worker module."""

from typing import Any


class Worker:
    """Task worker."""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self._busy = False
    
    async def process(self, task: dict[str, Any]) -> Any:
        """Process task."""
        self._busy = True
        result = {"task_id": task.get("id"), "status": "completed"}
        self._busy = False
        return result
