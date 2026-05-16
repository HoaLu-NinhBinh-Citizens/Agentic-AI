"""Redis cache stub."""

from typing import Any


class RedisCache:
    """Redis-backed cache."""
    
    def __init__(self, url: str = "redis://localhost:6379"):
        self._url = url
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to Redis."""
        self._connected = True
    
    async def set(self, key: str, value: Any) -> None:
        """Set cache value."""
        pass
    
    async def get(self, key: str) -> Any | None:
        """Get cache value."""
        return None
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._connected = False
