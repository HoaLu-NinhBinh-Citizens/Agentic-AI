"""Readiness probe stub."""

from typing import Any


class ReadinessProbe:
    """Readiness check for the agent."""
    
    def __init__(self):
        self._ready = True
    
    async def check(self) -> dict[str, Any]:
        """Perform readiness check."""
        return {
            "status": "ready" if self._ready else "not_ready",
            "timestamp": "now",
        }
    
    def set_ready(self, ready: bool) -> None:
        """Set ready status."""
        self._ready = ready
