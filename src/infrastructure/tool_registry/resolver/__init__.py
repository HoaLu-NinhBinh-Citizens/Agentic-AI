"""Tool resolver module."""

from typing import Any


class ToolResolver:
    """Resolves tool names to implementations."""
    
    def __init__(self):
        self._resolvers: dict[str, Any] = {}
    
    def register(self, pattern: str, resolver: Any) -> None:
        """Register a resolver."""
        self._resolvers[pattern] = resolver
    
    def resolve(self, name: str) -> Any | None:
        """Resolve tool name."""
        for pattern, resolver in self._resolvers.items():
            if pattern in name:
                return resolver
        return None
