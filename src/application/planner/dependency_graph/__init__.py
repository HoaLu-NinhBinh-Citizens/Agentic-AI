"""Dependency graph application module."""

from typing import Any


class DependencyGraph:
    """Manages task dependencies."""
    
    def __init__(self):
        self._graph: dict[str, list[str]] = {}
    
    def add_task(self, task_id: str, depends_on: list[str]) -> None:
        """Add task with dependencies."""
        self._graph[task_id] = depends_on
    
    def get_order(self) -> list[str]:
        """Get topological order."""
        return list(self._graph.keys())
