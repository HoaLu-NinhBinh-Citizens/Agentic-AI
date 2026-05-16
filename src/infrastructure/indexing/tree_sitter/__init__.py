"""Tree-sitter indexing stub."""

from typing import Any


class TreeSitterIndexer:
    """Indexes code using tree-sitter."""
    
    def __init__(self):
        self._index: dict[str, Any] = {}
    
    def index_file(self, path: str, content: str) -> None:
        """Index a file."""
        self._index[path] = {"ast": "stub", "symbols": []}
    
    def search(self, query: str) -> list[str]:
        """Search indexed files."""
        return []
