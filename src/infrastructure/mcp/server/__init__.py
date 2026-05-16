"""MCP server module."""

from typing import Any


class MCPServer:
    """Model Context Protocol server."""
    
    def __init__(self):
        self._running = False
    
    async def start(self) -> None:
        """Start MCP server."""
        self._running = True
    
    async def stop(self) -> None:
        """Stop MCP server."""
        self._running = False
