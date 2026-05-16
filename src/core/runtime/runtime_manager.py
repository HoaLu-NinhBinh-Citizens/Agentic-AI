"""Runtime manager stub."""

from typing import Any


class RuntimeManager:
    """Manages agent runtime lifecycle."""
    
    async def start(self) -> None:
        """Start the runtime."""
        pass
    
    async def stop(self) -> None:
        """Stop the runtime."""
        pass
    
    async def execute(self, task: str) -> dict[str, Any]:
        """Execute a task."""
        return {"status": "success"}
