"""Tracing gateway stub."""

from typing import Any


class TracingGateway:
    """Tracing for gateway operations."""
    
    def __init__(self):
        self._traces: list[dict[str, Any]] = []
    
    async def trace(self, operation: str, context: dict[str, Any]) -> None:
        """Record a trace."""
        self._traces.append({
            "operation": operation,
            "context": context,
            "timestamp": "now",
        })
    
    def get_traces(self) -> list[dict[str, Any]]:
        """Get all traces."""
        return self._traces.copy()
