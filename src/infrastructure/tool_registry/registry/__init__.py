"""Tool registry stub."""

from typing import Any, Callable, TypeVar

T = TypeVar('T')


class ToolRegistry:
    """Registry for available tools."""
    
    def __init__(self):
        self._tools: dict[str, Callable] = {}
    
    def register(self, name: str, func: Callable) -> None:
        """Register a tool."""
        self._tools[name] = func
    
    def get(self, name: str) -> Callable | None:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> list[str]:
        """List all registered tools."""
        return list(self._tools.keys())
    
    async def execute(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a tool."""
        tool = self.get(name)
        if tool:
            return await tool(*args, **kwargs)
        raise ValueError(f"Tool not found: {name}")
