"""IDE STDIO bridge module."""

from typing import Any


class STDIOBridge:
    """Bridge between IDE and agent via STDIO."""
    
    def __init__(self):
        self._running = False
    
    async def start(self) -> None:
        """Start STDIO bridge."""
        self._running = True
    
    async def send(self, message: dict[str, Any]) -> None:
        """Send message."""
        print(message)
    
    async def receive(self) -> dict[str, Any]:
        """Receive message."""
        return {}
    
    def stop(self) -> None:
        """Stop STDIO bridge."""
        self._running = False
