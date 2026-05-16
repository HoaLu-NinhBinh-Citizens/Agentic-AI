"""Rate limit middleware stub."""

import time
from typing import Any


class RateLimitMiddleware:
    """Middleware for rate limiting."""
    
    def __init__(self, max_per_second: int = 10):
        self._max = max_per_second
        self._window: list[float] = []
    
    async def process(self, context: dict[str, Any], next_handler) -> Any:
        """Process with rate limiting."""
        now = time.time()
        self._window = [t for t in self._window if now - t < 1.0]
        
        if len(self._window) >= self._max:
            raise Exception("Rate limit exceeded")
        
        self._window.append(now)
        return await next_handler(context)
