"""
Tool Result Cache

Caching for tool execution results.
"""

import hashlib
import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.tools.schema import ToolResult

logger = logging.getLogger(__name__)


class ToolResultCache:
    """
    Cache for tool execution results.

    Features:
    - LRU eviction
    - TTL expiration
    - Size limits
    - Persistence to disk
    - Statistics tracking

    Usage:
        cache = ToolResultCache(max_size=100, ttl_seconds=3600)

        # Store result
        cache.set("key123", result)

        # Get result
        result = cache.get("key123")

        # Clear
        cache.clear()
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: int = 3600,
        persist_path: Optional[Path] = None,
        collect_stats: bool = True,
    ):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of cached items
            ttl_seconds: Time-to-live in seconds
            persist_path: Optional path for disk persistence
            collect_stats: Whether to collect statistics
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.persist_path = persist_path
        self.collect_stats = collect_stats

        self._cache: OrderedDict = OrderedDict()
        self._expiry: Dict[str, datetime] = {}
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        # Load from disk if path provided
        if persist_path and persist_path.exists():
            self._load_from_disk()

    def get(self, key: str) -> Optional[ToolResult]:
        """
        Get a cached result.

        Args:
            key: Cache key

        Returns:
            Cached ToolResult or None
        """
        # Check if key exists
        if key not in self._cache:
            if self.collect_stats:
                self._misses += 1
            return None

        # Check if expired
        if self._is_expired(key):
            self._remove(key)
            if self.collect_stats:
                self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)

        if self.collect_stats:
            self._hits += 1

        # Deserialize if needed
        result = self._cache[key]
        if isinstance(result, dict):
            result = ToolResult.from_dict(result)
            self._cache[key] = result

        return result

    def set(self, key: str, result: ToolResult) -> None:
        """
        Cache a result.

        Args:
            key: Cache key
            result: ToolResult to cache
        """
        # Evict if at capacity
        if key not in self._cache and len(self._cache) >= self.max_size:
            self._evict_lru()

        # Store result
        self._cache[key] = result
        self._cache.move_to_end(key)
        self._expiry[key] = datetime.now() + timedelta(seconds=self.ttl_seconds)

        # Persist to disk
        if self.persist_path:
            self._save_to_disk()

    def _is_expired(self, key: str) -> bool:
        """Check if a key is expired."""
        if key not in self._expiry:
            return False
        return datetime.now() > self._expiry[key]

    def _remove(self, key: str) -> None:
        """Remove a key from cache."""
        if key in self._cache:
            del self._cache[key]
        if key in self._expiry:
            del self._expiry[key]

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            self._remove(oldest_key)
            if self.collect_stats:
                self._evictions += 1
            logger.debug(f"Evicted LRU key: {oldest_key}")

    def clear(self) -> None:
        """Clear all cached items."""
        self._cache.clear()
        self._expiry.clear()

        if self.persist_path and self.persist_path.exists():
            self.persist_path.unlink()

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a specific key.

        Args:
            key: Key to invalidate

        Returns:
            True if key was found and removed
        """
        if key in self._cache:
            self._remove(key)
            if self.persist_path:
                self._save_to_disk()
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            pattern: Pattern to match (supports * wildcard)

        Returns:
            Number of keys invalidated
        """
        import fnmatch

        keys_to_remove = [
            key for key in self._cache.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

        for key in keys_to_remove:
            self._remove(key)

        if self.persist_path and keys_to_remove:
            self._save_to_disk()

        return len(keys_to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        if not self.persist_path:
            return

        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for key, result in self._cache.items():
                if isinstance(result, ToolResult):
                    data[key] = result.to_dict()
                else:
                    data[key] = result

            with open(self.persist_path, "w") as f:
                json.dump(data, f)

        except Exception as e:
            logger.warning(f"Failed to save cache to disk: {e}")

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return

        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)

            for key, result_dict in data.items():
                result = ToolResult.from_dict(result_dict)
                self._cache[key] = result
                self._expiry[key] = datetime.now() + timedelta(seconds=self.ttl_seconds)

            logger.info(f"Loaded {len(self._cache)} items from cache")

        except Exception as e:
            logger.warning(f"Failed to load cache from disk: {e}")

    def cleanup_expired(self) -> int:
        """
        Remove all expired items.

        Returns:
            Number of items removed
        """
        expired_keys = [
            key for key in self._cache.keys()
            if self._is_expired(key)
        ]

        for key in expired_keys:
            self._remove(key)

        if self.persist_path and expired_keys:
            self._save_to_disk()

        return len(expired_keys)

    def get_keys(self) -> List[str]:
        """Get all cache keys."""
        return list(self._cache.keys())

    def __len__(self) -> int:
        """Get number of cached items."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if key is in cache."""
        return key in self._cache and not self._is_expired(key)


# Decorator for caching tool results
def cached(cache: ToolResultCache, key_func: callable = None):
    """
    Decorator to cache function results.

    Args:
        cache: ToolResultCache instance
        key_func: Function to generate cache key from args

    Usage:
        @cached(my_cache)
        def expensive_function(param):
            return compute(param)
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                import hashlib
                import json

                key_data = {"args": args, "kwargs": kwargs}
                key = hashlib.sha256(
                    json.dumps(key_data, sort_keys=True, default=str).encode()
                ).hexdigest()[:32]

            # Check cache
            cached_result = cache.get(key)
            if cached_result:
                return cached_result

            # Execute and cache
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        return wrapper

    return decorator
