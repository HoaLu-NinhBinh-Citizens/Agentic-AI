"""Liveness probe stub."""

from typing import Any


class LivenessProbe:
    """Liveness check for the agent."""
    
    def __init__(self):
        self._healthy = True
    
    async def check(self) -> dict[str, Any]:
        """Perform liveness check."""
        return {
            "status": "healthy" if self._healthy else "unhealthy",
            "timestamp": "now",
        }
    
    def set_healthy(self, healthy: bool) -> None:
        """Set health status."""
        self._healthy = healthy
