"""Execution graph module."""

from typing import Any


class ExecutionGraph:
    """Task execution graph."""
    
    def __init__(self):
        self._nodes: list[dict[str, Any]] = []
        self._edges: list[tuple[str, str]] = []
    
    def add_node(self, node: dict[str, Any]) -> None:
        """Add node."""
        self._nodes.append(node)
    
    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add edge."""
        self._edges.append((from_node, to_node))
