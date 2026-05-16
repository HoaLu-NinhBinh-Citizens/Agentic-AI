"""
Search result cache with TTL-based eviction.

Provides in-memory caching for retrieval results to avoid redundant
LLM calls and vector index lookups.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from src.core.config.agent_prompts import SEARCH_CACHE_TTL_SECONDS, SEARCH_CACHE_MAX_ENTRIES

logger = logging.getLogger(__name__)


class SearchCache:
    """
    Simple TTL-based cache for search results.

    Stores query -> result mappings with automatic expiration.
    When max entries is reached, oldest entries are evicted.
    """

    def __init__(self, ttl_seconds: int = SEARCH_CACHE_TTL_SECONDS, max_entries: int = SEARCH_CACHE_MAX_ENTRIES):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[List]:
        """
        Get cached result for a query.

        Returns None if key doesn't exist or has expired.
        """
        self._evict_expired()

        entry = self._cache.get(key)
        if entry is None:
            return None

        # Check if expired
        if time.time() > entry["expires_at"]:
            self._cache.pop(key, None)
            return None

        logger.debug("Cache hit for key: %s", key[:80])
        return entry["result"]

    def set(self, key: str, result: List) -> None:
        """
        Store a result in the cache.

        Evicts oldest entries if max capacity reached.
        """
        self._evict_expired()

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_entries:
            self._evict_oldest(count=max(1, self._max_entries // 4))

        self._cache[key] = {
            "result": result,
            "expires_at": time.time() + self._ttl,
            "created_at": time.time(),
        }

    def invalidate(self, key: str) -> bool:
        """Remove a specific entry from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Search cache cleared")

    def _evict_expired(self) -> int:
        """Remove all expired entries. Returns count of evicted entries."""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry["expires_at"]
        ]

        for key in expired_keys:
            self._cache.pop(key, None)

        if expired_keys:
            logger.debug("Evicted %d expired cache entries", len(expired_keys))

        return len(expired_keys)

    def _evict_oldest(self, count: int = 1) -> int:
        """Evict the oldest entries. Returns count of evicted entries."""
        if not self._cache:
            return 0

        # Sort by creation time
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda item: item[1]["created_at"]
        )

        evicted = 0
        for key, _ in sorted_entries[:count]:
            self._cache.pop(key, None)
            evicted += 1

        return evicted

    @property
    def size(self) -> int:
        """Current number of entries in cache."""
        self._evict_expired()
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        self._evict_expired()
        now = time.time()
        ages = [now - entry["created_at"] for entry in self._cache.values()]
        return {
            "size": len(self._cache),
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl,
            "avg_age_seconds": sum(ages) / len(ages) if ages else 0,
            "oldest_age_seconds": max(ages) if ages else 0,
        }


# Global cache instance for sharing across retriever instances
_search_cache: Optional[SearchCache] = None


def get_search_cache() -> SearchCache:
    """Get or create the global search cache instance."""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache()
    return _search_cache


def clear_search_cache() -> None:
    """Clear the global search cache."""
    global _search_cache
    if _search_cache is not None:
        _search_cache.clear()
