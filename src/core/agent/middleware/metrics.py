"""Metrics middleware stub."""

import time
from typing import Any


class MetricsMiddleware:
    """Middleware for collecting metrics."""
    
    def __init__(self):
        self._counters: dict[str, int] = {}
        self._timers: dict[str, float] = {}
    
    async def process(self, context: dict[str, Any], next_handler) -> Any:
        """Process and record metrics."""
        start = time.perf_counter()
        result = await next_handler(context)
        elapsed = time.perf_counter() - start
        
        operation = context.get("operation", "unknown")
        self._counters[operation] = self._counters.get(operation, 0) + 1
        self._timers[operation] = self._timers.get(operation, 0) + elapsed
        
        return result
    
    def get_stats(self) -> dict[str, Any]:
        """Get collected stats."""
        return {"counters": self._counters, "timers": self._timers}
