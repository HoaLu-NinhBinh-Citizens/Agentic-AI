"""Multi-root workspace module."""

from typing import Any


class MultiRootWorkspace:
    """Manages multiple workspace roots."""
    
    def __init__(self):
        self._roots: dict[str, str] = {}
    
    def add_root(self, name: str, path: str) -> None:
        """Add workspace root."""
        self._roots[name] = path
    
    def get_root(self, name: str) -> str | None:
        """Get workspace root."""
        return self._roots.get(name)
