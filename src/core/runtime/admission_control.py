"""Admission control stub."""

from typing import Any


class AdmissionControl:
    """Controls admission of new tasks."""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._current = 0
    
    async def admit(self) -> bool:
        """Admit a new task if capacity allows."""
        if self._current < self.max_concurrent:
            self._current += 1
            return True
        return False
    
    def release(self) -> None:
        """Release a task slot."""
        self._current = max(0, self._current - 1)
