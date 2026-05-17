"""Decompression cache with LRU eviction, TTL support, and checksum validation."""

from __future__ import annotations

import hashlib
import time
import threading
from collections import OrderedDict
from typing import Optional


class DecompressionCache:
    """LRU cache for decompressed content with TTL and checksum validation.
    
    Features:
    - LRU eviction when maxsize is reached
    - TTL-based expiration
    - Thread-safe operations
    - Hit/miss tracking for metrics
    - Checksum validation to detect cache corruption
    """
    
    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        """Initialize the decompression cache.
        
        Args:
            maxsize: Maximum number of entries.
            ttl_seconds: Time-to-live in seconds.
        """
        # Cache stores: key -> (content, timestamp, checksum)
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        
        self._hits = 0
        self._misses = 0
        self._corruption_detected = 0
    
    @staticmethod
    def _compute_checksum(content: str) -> str:
        """Compute SHA256 checksum of content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[str]:
        """Get content from cache if not expired and checksum valid.
        
        Args:
            key: Cache key.
            
        Returns:
            Content if found, not expired, and checksum valid. None otherwise.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            content, timestamp, stored_checksum = self._cache[key]
            
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Fix #4: Verify checksum to detect cache corruption
            current_checksum = self._compute_checksum(content)
            if current_checksum != stored_checksum:
                # Cache corruption detected - remove invalid entry
                del self._cache[key]
                self._misses += 1
                self._corruption_detected += 1
                return None
            
            self._cache.move_to_end(key)
            self._hits += 1
            return content
    
    def set(self, key: str, content: str, checksum: str | None = None) -> None:
        """Set content in cache with LRU eviction.
        
        Args:
            key: Cache key.
            content: Content to cache.
            checksum: Optional pre-computed checksum. If None, computed automatically.
        """
        with self._lock:
            if checksum is None:
                checksum = self._compute_checksum(content)
            
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (content, time.time(), checksum)
                return
            
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            
            self._cache[key] = (content, time.time(), checksum)
    
    def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry.
        
        Args:
            key: Cache key to invalidate.
            
        Returns:
            True if key was found and removed.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def _evict_expired(self) -> int:
        """Evict all expired entries.
        
        Returns:
            Number of entries evicted.
        """
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if now - timestamp > self._ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        return len(expired_keys)
    
    @property
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)
    
    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total
    
    @property
    def hits(self) -> int:
        """Get number of cache hits."""
        return self._hits
    
    @property
    def misses(self) -> int:
        """Get number of cache misses."""
        return self._misses
    
    @property
    def corruption_detected(self) -> int:
        """Get number of cache corruption events detected."""
        with self._lock:
            return self._corruption_detected
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": self.size,
            "maxsize": self._maxsize,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "corruption_detected": self._corruption_detected,
        }
