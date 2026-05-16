"""CLI interactive module."""

from typing import Any


class InteractiveMode:
    """Interactive CLI mode."""
    
    def __init__(self):
        self._running = False
    
    async def start(self) -> None:
        """Start interactive mode."""
        self._running = True
        while self._running:
            pass
    
    def stop(self) -> None:
        """Stop interactive mode."""
        self._running = False
