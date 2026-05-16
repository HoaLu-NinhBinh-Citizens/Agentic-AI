"""Workspace index module."""

from typing import Any


class WorkspaceIndex:
    """Indexes workspace files."""
    
    def __init__(self):
        self._index: dict[str, Any] = {}
    
    def index(self, path: str, content: str) -> None:
        """Index a file."""
        self._index[path] = content
    
    def search(self, query: str) -> list[str]:
        """Search indexed files."""
        return []
