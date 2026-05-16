"""TUI application stub."""

import asyncio
from typing import Any


class TUIApp:
    """Terminal UI application."""
    
    def __init__(self):
        self._running = False
    
    async def run(self) -> None:
        """Run the TUI."""
        self._running = True
        print("TUI running...")
        while self._running:
            await asyncio.sleep(0.1)
    
    def stop(self) -> None:
        """Stop the TUI."""
        self._running = False
