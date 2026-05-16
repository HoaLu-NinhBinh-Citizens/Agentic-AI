"""Task decomposition application module."""

from typing import Any


class Decomposition:
    """Decomposes complex tasks."""
    
    async def decompose(self, task: str) -> list[dict[str, Any]]:
        """Decompose task into subtasks."""
        return [{"description": task, "subtasks": []}]
