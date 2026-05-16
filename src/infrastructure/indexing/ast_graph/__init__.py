"""AST graph module."""

from typing import Any


class ASTGraph:
    """Abstract syntax tree graph."""
    
    def __init__(self):
        self._nodes: dict[str, Any] = {}
        self._edges: list[tuple[str, str]] = []
    
    def add_node(self, id: str, node_type: str, data: dict[str, Any]) -> None:
        """Add AST node."""
        self._nodes[id] = {"type": node_type, "data": data}
    
    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add edge between nodes."""
        self._edges.append((from_id, to_id))
