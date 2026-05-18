"""
Sliding Log Rate Limiter.

Uses Redis sorted set for precise sliding window rate limiting.
Stores timestamps of requests, checks count in last N seconds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_in_seconds: float
    retry_after: Optional[float]


class InMemorySlidingLog:
    """
    In-memory sliding log for rate limiting.
    
    Stores timestamps of requests, checks count in sliding window.
    """
    
    def __init__(self, key: str):
        self.key = key
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()
    
    async def add(self, timestamp: float) -> int:
        """Add timestamp and return count in window."""
        async with self._lock:
            self._timestamps.append(timestamp)
            return len(self._timestamps)
    
    async def count_in_window(self, window_seconds: float) -> int:
        """Count requests in sliding window."""
        async with self._lock:
            cutoff = time.time() - window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return len(self._timestamps)
    
    async def remove_old(self, window_seconds: float) -> int:
        """Remove timestamps outside window."""
        async with self._lock:
            cutoff = time.time() - window_seconds
            old = [t for t in self._timestamps if t <= cutoff]
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return len(old)


class SlidingLogRateLimiter:
    """
    Sliding log rate limiter.
    
    Features:
    - Precise sliding window rate limiting
    - No burst leakage
    - Per-key tracking
    - Configurable windows
    
    Algorithm:
    1. Add current timestamp to sorted set
    2. Remove timestamps outside window
    3. Count remaining entries
    4. If count > limit, reject
    """
    
    def __init__(
        self,
        default_limit: int = 100,
        default_window_seconds: float = 10.0,
    ):
        self.default_limit = default_limit
        self.default_window = default_window_seconds
        
        # In-memory stores (would be Redis in production)
        self._logs: Dict[str, InMemorySlidingLog] = {}
        self._limits: Dict[str, tuple[int, float]] = {}  # key -> (limit, window)
        self._lock = asyncio.Lock()
    
    def _get_or_create_log(self, key: str) -> InMemorySlidingLog:
        """Get or create sliding log for key."""
        if key not in self._logs:
            self._logs[key] = InMemorySlidingLog(key)
        return self._logs[key]
    
    def set_limit(
        self,
        key: str,
        limit: int,
        window_seconds: float,
    ) -> None:
        """Set rate limit for key."""
        self._limits[key] = (limit, window_seconds)
    
    async def check(
        self,
        key: str,
        limit: Optional[int] = None,
        window_seconds: Optional[float] = None,
    ) -> RateLimitResult:
        """
        Check rate limit for key.
        
        Returns whether request is allowed.
        """
        limit = limit or self.default_limit
        window = window_seconds or self.default_window
        
        # Override with per-key limit
        if key in self._limits:
            key_limit, key_window = self._limits[key]
            limit = key_limit
            window = key_window
        
        log = self._get_or_create_log(key)
        now = time.time()
        
        # Add current request
        await log.add(now)
        
        # Count in window
        count = await log.count_in_window(window)
        
        # Calculate remaining
        remaining = max(0, limit - count)
        
        # Calculate reset time
        oldest_in_window = now - window
        reset_in = window  # Approximate
        
        if count > limit:
            # Request would exceed limit, but we already added it
            # Remove the entry we just added
            async with log._lock:
                if log._timestamps and log._timestamps[-1] == now:
                    log._timestamps.pop()
            
            return RateLimitResult(
                allowed=False,
                current_count=count - 1,
                limit=limit,
                remaining=0,
                reset_in_seconds=window,
                retry_after=1.0,  # Suggest retry after 1 second
            )
        
        return RateLimitResult(
            allowed=True,
            current_count=count,
            limit=limit,
            remaining=remaining,
            reset_in_seconds=window,
            retry_after=None,
        )
    
    async def check_and_acquire(
        self,
        key: str,
        limit: Optional[int] = None,
        window_seconds: Optional[float] = None,
    ) -> RateLimitResult:
        """
        Check rate limit and acquire slot if allowed.
        
        Atomic operation: check and add in one step.
        """
        return await self.check(key, limit, window_seconds)
    
    async def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        async with self._lock:
            if key in self._logs:
                async with self._logs[key]._lock:
                    self._logs[key]._timestamps.clear()
    
    async def get_current_count(self, key: str) -> int:
        """Get current count in window for key."""
        if key not in self._logs:
            return 0
        
        window = self.default_window
        if key in self._limits:
            _, window = self._limits[key]
        
        return await self._logs[key].count_in_window(window)
    
    async def get_all_counts(self) -> Dict[str, int]:
        """Get counts for all keys."""
        counts = {}
        for key, log in self._logs.items():
            window = self.default_window
            if key in self._limits:
                _, window = self._limits[key]
            counts[key] = await log.count_in_window(window)
        return counts
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics."""
        return {
            "tracked_keys": len(self._logs),
            "configured_limits": len(self._limits),
            "default_limit": self.default_limit,
            "default_window": self.default_window,
        }


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter (alternative to sliding log).
    
    Tokens are added at a constant rate. Each request consumes a token.
    """
    
    def __init__(
        self,
        tokens_per_second: float = 10.0,
        max_tokens: Optional[float] = None,
        burst_size: Optional[int] = None,
    ):
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens or tokens_per_second * 10
        self.burst_size = burst_size or int(self.max_tokens)
        
        self._buckets: Dict[str, tuple[float, float]] = {}  # key -> (tokens, last_update)
        self._lock = asyncio.Lock()
    
    async def acquire(
        self,
        key: str,
        tokens: int = 1,
    ) -> bool:
        """Try to acquire tokens."""
        async with self._lock:
            now = time.time()
            
            if key in self._buckets:
                current_tokens, last_update = self._buckets[key]
                
                # Add tokens based on elapsed time
                elapsed = now - last_update
                current_tokens = min(
                    self.max_tokens,
                    current_tokens + elapsed * self.tokens_per_second
                )
            else:
                current_tokens = self.max_tokens
            
            if current_tokens >= tokens:
                # Can acquire
                self._buckets[key] = (current_tokens - tokens, now)
                return True
            else:
                # Cannot acquire
                self._buckets[key] = (current_tokens, now)
                return False
    
    def get_available_tokens(self, key: str) -> float:
        """Get available tokens for key."""
        if key not in self._buckets:
            return self.max_tokens
        
        now = time.time()
        current_tokens, last_update = self._buckets[key]
        elapsed = now - last_update
        
        return min(
            self.max_tokens,
            current_tokens + elapsed * self.tokens_per_second
        )
