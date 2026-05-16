"""Tool namespaces module."""

from typing import Any


class ToolNamespace:
    """Groups tools by namespace."""
    
    def __init__(self, name: str):
        self.name = name
        self._tools: dict[str, Any] = {}
    
    def add(self, name: str, tool: Any) -> None:
        """Add tool to namespace."""
        self._tools[name] = tool
    
    def get(self, name: str) -> Any | None:
        """Get tool from namespace."""
        return self._tools.get(name)
