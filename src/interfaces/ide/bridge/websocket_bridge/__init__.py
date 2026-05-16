"""IDE WebSocket bridge module."""

from typing import Any


class WebSocketBridge:
    """Bridge between IDE and agent via WebSocket."""
    
    def __init__(self):
        self._connected = False
    
    async def connect(self, url: str) -> None:
        """Connect to IDE."""
        self._connected = True
    
    async def send(self, message: dict[str, Any]) -> None:
        """Send message to IDE."""
        pass
    
    async def receive(self) -> dict[str, Any]:
        """Receive message from IDE."""
        return {}
    
    async def disconnect(self) -> None:
        """Disconnect from IDE."""
        self._connected = False
