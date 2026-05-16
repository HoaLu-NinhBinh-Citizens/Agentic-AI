"""In-memory cache stub."""

from typing import Any
import time


class InMemoryCache:
    """Simple in-memory cache."""
    
    def __init__(self, ttl: int = 300):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl
    
    def set(self, key: str, value: Any) -> None:
        """Set cache value."""
        self._cache[key] = (value, time.time())
    
    def get(self, key: str) -> Any | None:
        """Get cache value."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None
    
    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
