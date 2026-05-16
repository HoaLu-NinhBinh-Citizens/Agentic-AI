"""Gateway rate limit module."""

from typing import Any


class RateLimitGateway:
    """Rate limiting for gateway."""
    
    def __init__(self, max_per_second: int = 100):
        self._max = max_per_second
    
    async def check_limit(self, key: str) -> bool:
        """Check rate limit."""
        return True
