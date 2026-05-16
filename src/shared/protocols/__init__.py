"""Shared protocols module."""

from typing import Protocol, Any


class AgentProtocol(Protocol):
    """Protocol for agent implementations."""
    
    async def process(self, task: str) -> dict[str, Any]:
        """Process a task."""
        ...


class ToolProtocol(Protocol):
    """Protocol for tool implementations."""
    
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool."""
        ...
