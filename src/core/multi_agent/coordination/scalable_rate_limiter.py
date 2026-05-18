"""
Scalable Rate Limiting with Count-Min Sketch Hybrid.

Features:
- Count-min sketch for approximate counting at scale
- Sliding window counter hybrid
- Memory-efficient for 100k+ RPS
- Configurable accuracy/memory trade-off
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CountMinSketch:
    """
    Count-Min Sketch for approximate frequency counting.
    
    Space-efficient probabilistic data structure.
    Guarantees:
    - Never under-counts (may over-count)
    - Error bound: actual <= reported <= actual + epsilon * N
    
    Parameters:
    - width: Number of counters per hash function
    - depth: Number of hash functions
    - seed: Random seed for reproducibility
    """
    
    width: int
    depth: int
    seed: int = 42
    
    def __post_init__(self):
        # Initialize counters
        self._counters: List[List[int]] = [
            [0] * self.width for _ in range(self.depth)
        ]
        
        # Generate hash seeds
        self._seeds = [
            self.seed + i * 31 for i in range(self.depth)
        ]
        
        self._total_count = 0
    
    def _hash(self, item: str, seed: int) -> int:
        """Hash item to index."""
        h = hashlib.sha256(f"{seed}:{item}".encode()).digest()
        return struct.unpack('<Q', h[:8])[0] % self.width
    
    def add(self, item: str, count: int = 1) -> None:
        """Add item to sketch."""
        self._total_count += count
        for i, seed in enumerate(self._seeds):
            idx = self._hash(item, seed)
            self._counters[i][idx] += count
    
    def estimate(self, item: str) -> int:
        """Estimate count for item (may be over-estimate)."""
        return min(
            self._counters[i][self._hash(item, self._seeds[i])]
            for i in range(self.depth)
        )
    
    def reset(self) -> None:
        """Reset all counters."""
        self._counters = [
            [0] * self.width for _ in range(self.depth)
        ]
        self._total_count = 0
    
    def get_memory_usage(self) -> int:
        """Get approximate memory usage in bytes."""
        return self.width * self.depth * 8  # 8 bytes per counter


@dataclass
class SlidingWindowCounter:
    """
    Sliding window counter for precise rate limiting.
    
    Stores timestamps in windows for accurate counting.
    More memory-intensive than count-min sketch.
    """
    
    window_seconds: float
    max_items: int = 10000
    
    def __post_init__(self):
        self._buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def add(self, key: str, timestamp: float) -> int:
        """Add request and return count in window."""
        async with self._lock:
            now = timestamp or datetime.now().timestamp()
            cutoff = now - self.window_seconds
            
            # Add new timestamp
            self._buckets[key].append(now)
            
            # Remove old timestamps
            self._buckets[key] = [
                t for t in self._buckets[key] if t > cutoff
            ]
            
            # Limit size
            if len(self._buckets[key]) > self.max_items:
                self._buckets[key] = self._buckets[key][-self.max_items:]
            
            return len(self._buckets[key])
    
    async def count(self, key: str, timestamp: Optional[float] = None) -> int:
        """Get count in window."""
        async with self._lock:
            now = timestamp or datetime.now().timestamp()
            cutoff = now - self.window_seconds
            
            self._buckets[key] = [
                t for t in self._buckets[key] if t > cutoff
            ]
            
            return len(self._buckets[key])
    
    async def reset(self, key: str) -> None:
        """Reset counter for key."""
        async with self._lock:
            self._buckets.pop(key, None)


class HybridRateLimiter:
    """
    Hybrid rate limiter combining count-min sketch and sliding window.
    
    Strategy:
    1. Use count-min sketch for high-volume keys (>1000 RPS)
    2. Use sliding window for low-volume keys (<1000 RPS)
    3. Dynamically upgrade/downgrade based on traffic
    
    Benefits:
    - Memory efficient for 100k+ RPS
    - Accurate for low-volume keys
    - Adaptive based on traffic patterns
    """
    
    def __init__(
        self,
        sketch_width: int = 10000,
        sketch_depth: int = 5,
        sliding_window_seconds: float = 10.0,
        high_volume_threshold: int = 1000,
        memory_budget_mb: float = 100.0,
    ):
        self.high_volume_threshold = high_volume_threshold
        self.sliding_window_seconds = sliding_window_seconds
        
        # Global count-min sketch for high-volume
        self._sketch = CountMinSketch(
            width=sketch_width,
            depth=sketch_depth,
        )
        
        # Per-key sliding windows for low-volume
        self._sliding_windows: Dict[str, SlidingWindowCounter] = {}
        
        # Key classification
        self._key_classification: Dict[str, str] = {}  # key -> "high" or "low"
        
        # Memory tracking
        self._memory_budget = memory_budget_mb * 1024 * 1024
        self._current_memory = self._sketch.get_memory_usage()
        
        self._lock = asyncio.Lock()
    
    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Check rate limit.
        
        Returns:
        - allowed: bool
        - current_count: int
        - limit: int
        - mode: "sketch" or "sliding"
        - estimated_error: float (for sketch mode)
        """
        window = window_seconds or self.sliding_window_seconds
        now = datetime.now().timestamp()
        
        # Determine mode
        mode = await self._get_mode(key)
        
        if mode == "sketch":
            # Use count-min sketch
            current_count = self._sketch.estimate(key)
            
            # Check limit
            if current_count >= limit:
                return {
                    "allowed": False,
                    "current_count": current_count,
                    "limit": limit,
                    "mode": "sketch",
                    "estimated_error": self._estimate_error(),
                    "retry_after": 1.0,
                }
            
            # Add to sketch
            self._sketch.add(key)
            
            return {
                "allowed": True,
                "current_count": current_count + 1,
                "limit": limit,
                "mode": "sketch",
                "estimated_error": self._estimate_error(),
            }
        
        else:
            # Use sliding window
            if key not in self._sliding_windows:
                self._sliding_windows[key] = SlidingWindowCounter(
                    window_seconds=window,
                )
            
            sw = self._sliding_windows[key]
            current_count = await sw.add(key, now)
            
            # Check limit
            if current_count > limit:
                return {
                    "allowed": False,
                    "current_count": current_count - 1,  # Don't count rejected
                    "limit": limit,
                    "mode": "sliding",
                    "retry_after": 1.0,
                }
            
            return {
                "allowed": True,
                "current_count": current_count,
                "limit": limit,
                "mode": "sliding",
            }
    
    async def _get_mode(self, key: str) -> str:
        """Get rate limiting mode for key."""
        if key in self._key_classification:
            return self._key_classification[key]
        
        # First request - use sliding window for accuracy
        return "sliding"
    
    async def _update_classification(self, key: str) -> None:
        """Update key classification based on traffic."""
        current_count = self._sketch.estimate(key)
        
        if current_count > self.high_volume_threshold:
            self._key_classification[key] = "sketch"
        else:
            self._key_classification[key] = "sliding"
    
    def _estimate_error(self) -> float:
        """Estimate error bound for count-min sketch."""
        # Error bound: epsilon * N where epsilon = 2 / width
        epsilon = 2.0 / self._sketch.width
        total = self._sketch._total_count or 1
        return epsilon * total
    
    async def migrate_to_sliding(self, key: str) -> None:
        """Migrate high-volume key to sliding window."""
        # Get approximate count from sketch
        approximate_count = self._sketch.estimate(key)
        
        # Create sliding window with estimated count
        sw = SlidingWindowCounter(window_seconds=self.sliding_window_seconds)
        now = datetime.now().timestamp()
        
        # Add approximate entries at staggered times
        for i in range(min(approximate_count, 100)):
            await sw.add(key, now - (i * 0.01))
        
        self._sliding_windows[key] = sw
        self._key_classification[key] = "sliding"
    
    async def migrate_to_sketch(self, key: str) -> None:
        """Migrate low-volume key to sketch."""
        # Get count from sliding window
        sw = self._sliding_windows.get(key)
        if sw:
            count = await sw.count(key)
            
            # Add to sketch
            for _ in range(count):
                self._sketch.add(key)
            
            # Remove sliding window
            await sw.reset(key)
            del self._sliding_windows[key]
        
        self._key_classification[key] = "sketch"
    
    async def cleanup_idle_keys(self, idle_seconds: float = 3600.0) -> int:
        """Clean up idle sliding windows to save memory."""
        cleaned = 0
        
        async with self._lock:
            now = datetime.now().timestamp()
            cutoff = now - idle_seconds
            
            idle_keys = []
            for key, sw in self._sliding_windows.items():
                # Check last activity
                last_times = sw._buckets.get(key, [])
                if last_times and max(last_times) < cutoff:
                    idle_keys.append(key)
            
            for key in idle_keys:
                del self._sliding_windows[key]
                self._key_classification.pop(key, None)
                cleaned += 1
        
        return cleaned
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics."""
        sketch_memory = self._sketch.get_memory_usage()
        sliding_memory = sum(
            8 * 10000 for _ in self._sliding_windows  # Rough estimate
        )
        
        high_volume_keys = sum(
            1 for m in self._key_classification.values() if m == "sketch"
        )
        low_volume_keys = len(self._sliding_windows)
        
        return {
            "mode": "hybrid",
            "sketch": {
                "width": self._sketch.width,
                "depth": self._sketch.depth,
                "memory_bytes": sketch_memory,
                "total_count": self._sketch._total_count,
            },
            "sliding_windows": {
                "active_keys": low_volume_keys,
                "memory_bytes": sliding_memory,
            },
            "high_volume_keys": high_volume_keys,
            "total_memory_bytes": sketch_memory + sliding_memory,
            "memory_budget_bytes": self._memory_budget,
            "high_volume_threshold": self.high_volume_threshold,
        }


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts based on system load.
    
    Features:
    - Dynamic limit adjustment based on system capacity
    - Proportional backoff under load
    - Per-tenant adaptive limits
    """
    
    def __init__(
        self,
        base_limit: int = 100,
        min_limit: int = 10,
        max_limit: int = 10000,
        window_seconds: float = 10.0,
    ):
        self.base_limit = base_limit
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.window_seconds = window_seconds
        
        # Per-tenant adaptive limits
        self._tenant_limits: Dict[str, int] = {}
        
        # System load tracking
        self._system_load = 0.0
        self._request_counts: Dict[str, int] = defaultdict(int)
        
        # Hybrid limiter
        self._hybrid = HybridRateLimiter()
        
        self._lock = asyncio.Lock()
    
    async def check(
        self,
        key: str,
        limit_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Check rate limit with adaptive adjustment."""
        # Get adaptive limit
        async with self._lock:
            limit = limit_override or self._tenant_limits.get(key, self.base_limit)
            
            # Adjust based on system load
            if self._system_load > 0.8:
                limit = int(limit * 0.5)  # Reduce 50%
            elif self._system_load > 0.6:
                limit = int(limit * 0.75)  # Reduce 25%
        
        # Check with hybrid limiter
        result = await self._hybrid.check(key, limit, self.window_seconds)
        
        # Track for load calculation
        async with self._lock:
            self._request_counts[key] += 1
        
        return result
    
    async def update_tenant_limit(
        self,
        tenant_id: str,
        limit: int,
    ) -> None:
        """Update adaptive limit for tenant."""
        async with self._lock:
            self._tenant_limits[tenant_id] = max(
                self.min_limit,
                min(self.max_limit, limit)
            )
    
    async def update_system_load(self, load: float) -> None:
        """Update system load factor (0-1)."""
        async with self._lock:
            self._system_load = max(0.0, min(1.0, load))
    
    async def get_effective_limit(self, key: str) -> int:
        """Get effective limit for key."""
        base = self._tenant_limits.get(key, self.base_limit)
        
        if self._system_load > 0.8:
            return int(base * 0.5)
        elif self._system_load > 0.6:
            return int(base * 0.75)
        
        return base
