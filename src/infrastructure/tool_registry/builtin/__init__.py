"""Tool builtin module."""

from typing import Any, Callable


class BuiltinTool:
    """Base builtin tool."""
    
    name: str = ""
    
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute tool."""
        return None


class FileSystemTool(BuiltinTool):
    """Filesystem builtin tool."""
    name = "filesystem"
    
    async def execute(self, operation: str, path: str) -> Any:
        return {"operation": operation, "path": path}
