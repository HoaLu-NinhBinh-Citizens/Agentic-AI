"""MCP client module."""

from typing import Any


class MCPClient:
    """Model Context Protocol client."""
    
    def __init__(self):
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to MCP server."""
        self._connected = True
    
    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call MCP tool."""
        return None
    
    async def disconnect(self) -> None:
        """Disconnect from server."""
        self._connected = False
