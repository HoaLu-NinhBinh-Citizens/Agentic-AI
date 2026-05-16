"""Dependency graph module."""

from typing import Any


class DependencyGraph:
    """Code dependency graph."""
    
    def __init__(self):
        self._deps: dict[str, list[str]] = {}
    
    def add_dependency(self, module: str, depends_on: str) -> None:
        """Add dependency."""
        if module not in self._deps:
            self._deps[module] = []
        self._deps[module].append(depends_on)
    
    def get_dependencies(self, module: str) -> list[str]:
        """Get module dependencies."""
        return self._deps.get(module, [])
