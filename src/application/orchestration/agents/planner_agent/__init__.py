"""Planner orchestration module."""

from typing import Any


class PlannerAgent:
    """Agent for task planning."""
    
    async def plan(self, task: str) -> list[dict[str, Any]]:
        """Create execution plan."""
        return [{"step": 1, "action": "analyze"}]
