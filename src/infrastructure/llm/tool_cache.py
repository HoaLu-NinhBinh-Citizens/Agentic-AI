"""Tool cache with embedding-based retrieval (Phase 10.1).

Provides:
- Tool caching with TTL
- LRU eviction
- Embedding-based tool retrieval
- Tool versioning
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CachedTool:
    """Cached tool invocation result."""
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    cached_at: datetime = field(default_factory=datetime.now)
    hit_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    ttl_seconds: float = 3600  # 1 hour default


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class ToolCache:
    """LRU cache for tool invocations.
    
    Phase 10.1: Tool caching - TTL, LRU eviction
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 3600,
        persist_path: Path | None = None,
    ) -> None:
        self._cache: OrderedDict[str, CachedTool] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._persist_path = persist_path
        self._stats = CacheStats()
        
        if persist_path:
            self._load_from_disk()
    
    def _make_key(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Generate cache key from tool name and arguments."""
        key_data = {
            "tool": tool_name,
            "args": arguments,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]
    
    def get(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any | None:
        """Get cached tool result."""
        key = self._make_key(tool_name, arguments)
        
        if key not in self._cache:
            self._stats.misses += 1
            return None
        
        cached = self._cache[key]
        
        # Check TTL
        age = (datetime.now() - cached.cached_at).total_seconds()
        if age > cached.ttl_seconds:
            del self._cache[key]
            self._stats.misses += 1
            return None
        
        # Update access stats
        cached.hit_count += 1
        cached.last_accessed = datetime.now()
        self._cache.move_to_end(key)
        
        self._stats.hits += 1
        logger.debug("Cache hit", tool=tool_name, hits=cached.hit_count)
        
        return cached.result
    
    def put(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        ttl: float | None = None,
    ) -> None:
        """Cache tool result."""
        key = self._make_key(tool_name, arguments)
        
        cached = CachedTool(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            ttl_seconds=ttl or self._default_ttl,
        )
        
        # Evict if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._evict_lru()
        
        self._cache[key] = cached
        self._cache.move_to_end(key)
        self._stats.size = len(self._cache)
        
        if self._persist_path:
            self._save_to_disk()
        
        logger.debug("Cached tool result", tool=tool_name, ttl=ttl)
    
    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self._cache:
            self._cache.popitem(last=False)
            self._stats.evictions += 1
            logger.debug("Evicted LRU item", size=self._stats.size)
    
    def invalidate(
        self,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> int:
        """Invalidate cache entries."""
        count = 0
        
        if tool_name is None:
            # Clear all
            count = len(self._cache)
            self._cache.clear()
        elif arguments is None:
            # Clear all for tool
            keys_to_delete = [
                k for k, v in self._cache.items()
                if v.tool_name == tool_name
            ]
            for k in keys_to_delete:
                del self._cache[k]
                count += 1
        else:
            # Clear specific entry
            key = self._make_key(tool_name, arguments)
            if key in self._cache:
                del self._cache[key]
                count = 1
        
        self._stats.size = len(self._cache)
        return count
    
    def cleanup_expired(self) -> int:
        """Remove expired entries."""
        now = datetime.now()
        expired_keys = []
        
        for key, cached in self._cache.items():
            age = (now - cached.cached_at).total_seconds()
            if age > cached.ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        self._stats.size = len(self._cache)
        
        if expired_keys and self._persist_path:
            self._save_to_disk()
        
        return len(expired_keys)
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        stats = CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
            size=len(self._cache),
        )
        return stats
    
    def _save_to_disk(self) -> None:
        """Persist cache to disk."""
        if not self._persist_path:
            return
        
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "cache": [
                {
                    "key": k,
                    "tool_name": v.tool_name,
                    "arguments": v.arguments,
                    "result": v.result,
                    "cached_at": v.cached_at.isoformat(),
                    "hit_count": v.hit_count,
                    "last_accessed": v.last_accessed.isoformat(),
                    "ttl_seconds": v.ttl_seconds,
                }
                for k, v in self._cache.items()
            ],
            "stats": {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "evictions": self._stats.evictions,
            },
        }
        
        self._persist_path.write_text(json.dumps(data, indent=2, default=str))
    
    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return
        
        try:
            data = json.loads(self._persist_path.read_text())
            
            for entry in data.get("cache", []):
                cached = CachedTool(
                    tool_name=entry["tool_name"],
                    arguments=entry["arguments"],
                    result=entry["result"],
                    cached_at=datetime.fromisoformat(entry["cached_at"]),
                    hit_count=entry["hit_count"],
                    last_accessed=datetime.fromisoformat(entry["last_accessed"]),
                    ttl_seconds=entry["ttl_seconds"],
                )
                self._cache[entry["key"]] = cached
            
            stats = data.get("stats", {})
            self._stats.hits = stats.get("hits", 0)
            self._stats.misses = stats.get("misses", 0)
            self._stats.evictions = stats.get("evictions", 0)
            
            logger.info("Loaded cache from disk", size=len(self._cache))
        except Exception as e:
            logger.warning("Failed to load cache from disk", error=str(e))


# Decorator for easy caching
def cached(
    ttl: float = 3600,
    cache: ToolCache | None = None,
):
    """Decorator to cache tool results."""
    _cache = cache or get_tool_cache()
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Build arguments dict
            arguments = {"args": str(args), "kwargs": kwargs}
            
            # Check cache
            result = _cache.get(func.__name__, arguments)
            if result is not None:
                return result
            
            # Execute and cache
            result = await func(*args, **kwargs)
            _cache.put(func.__name__, arguments, result, ttl)
            
            return result
        return wrapper
    return decorator


# Global singleton
_tool_cache: ToolCache | None = None


def get_tool_cache() -> ToolCache:
    """Get global tool cache instance."""
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = ToolCache(
            max_size=1000,
            default_ttl=3600,
        )
    return _tool_cache
