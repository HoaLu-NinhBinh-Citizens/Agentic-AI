"""Symbol graph stub."""

from typing import Any


class SymbolGraph:
    """Builds symbol dependency graphs."""
    
    def __init__(self):
        self._nodes: dict[str, Any] = {}
        self._edges: list[tuple[str, str]] = []
    
    def add_node(self, name: str, symbol_type: str) -> None:
        """Add a symbol node."""
        self._nodes[name] = {"name": name, "type": symbol_type}
    
    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add dependency edge."""
        self._edges.append((from_node, to_node))
    
    def get_dependents(self, symbol: str) -> list[str]:
        """Get symbols that depend on this symbol."""
        return [to_ for from_, to_ in self._edges if from_ == symbol]
