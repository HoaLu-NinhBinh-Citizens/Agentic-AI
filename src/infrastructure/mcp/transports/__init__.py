"""MCP transports module."""

from typing import Any


class Transport:
    """Base transport class."""
    
    async def send(self, data: Any) -> None:
        """Send data."""
        pass
    
    async def receive(self) -> Any:
        """Receive data."""
        return None
