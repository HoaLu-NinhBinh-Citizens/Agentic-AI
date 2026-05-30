"""
Intelligent caching for performance optimization.
"""

import functools
import hashlib
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class CacheStats:
    """Statistics for cache operations."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CacheManager:
    """
    Multi-level cache with TTL and LRU eviction.
    """

    def __init__(
        self,
        cache_dir: Path,
        max_memory_mb: int = 500,
        default_ttl_seconds: int = 3600
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_memory_mb = max_memory_mb
        self.default_ttl = default_ttl_seconds
        self._memory_cache: dict[str, tuple[Any, datetime]] = {}
        self._stats = CacheStats()
        self._max_memory_bytes = max_memory_mb * 1024 * 1024

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._memory_cache:
            value, expiry = self._memory_cache[key]
            if datetime.now() < expiry:
                self._stats.hits += 1
                return value
            else:
                del self._memory_cache[key]

        disk_value = self._get_from_disk(key)
        if disk_value is not None:
            self._stats.hits += 1
            self._set_in_memory(key, disk_value)
            return disk_value

        self._stats.misses += 1
        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ):
        """Set value in cache."""
        ttl = ttl_seconds or self.default_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)

        self._set_in_memory(key, value, expiry)
        self._set_to_disk(key, value, expiry)

    def _set_in_memory(self, key: str, value: Any, expiry: datetime):
        """Set value in memory cache."""
        current_size = self._estimate_size(self._memory_cache)
        value_size = self._estimate_size({key: value})

        if current_size + value_size > self._max_memory_bytes:
            self._evict_lru()

        self._memory_cache[key] = (value, expiry)

    def _evict_lru(self):
        """Evict least recently used items."""
        self._stats.evictions += 1

        now = datetime.now()
        expired = [k for k, (_, exp) in self._memory_cache.items() if exp < now]
        for k in expired:
            del self._memory_cache[k]

        if len(self._memory_cache) > 100:
            sorted_keys = sorted(
                self._memory_cache.keys(),
                key=lambda k: self._memory_cache[k][1]
            )
            for k in sorted_keys[:len(sorted_keys) // 2]:
                del self._memory_cache[k]

    def _get_from_disk(self, key: str) -> Optional[Any]:
        """Get value from disk cache."""
        cache_file = self._get_cache_file(key)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)

            expiry = datetime.fromisoformat(data['expiry'])
            if datetime.now() < expiry:
                return data['value']
            else:
                cache_file.unlink()
                return None
        except Exception:
            return None

    def _set_to_disk(self, key: str, value: Any, expiry: datetime):
        """Set value to disk cache."""
        cache_file = self._get_cache_file(key)

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'value': value,
                    'expiry': expiry.isoformat(),
                    'key': key
                }, f)
        except Exception:
            pass

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"cache_{key_hash}.pkl"

    def _estimate_size(self, obj: Any) -> int:
        """Estimate size of object in bytes."""
        try:
            return len(pickle.dumps(obj))
        except Exception:
            return 0

    @property
    def stats(self) -> CacheStats:
        return self._stats


def cached(cache_manager: CacheManager, ttl_seconds: int = 3600):
    """
    Decorator to cache function results.

    Usage:
        @cached(cache_manager)
        def expensive_function(arg1, arg2):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            result = cache_manager.get(key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache_manager.set(key, result, ttl_seconds)
            return result

        return wrapper
    return decorator
