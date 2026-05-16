"""Task planner application module."""

from typing import Any


class TaskPlanner:
    """Plans task decomposition."""
    
    async def plan(self, task: str) -> list[dict[str, Any]]:
        """Plan task."""
        return [{"description": task, "priority": 5}]
