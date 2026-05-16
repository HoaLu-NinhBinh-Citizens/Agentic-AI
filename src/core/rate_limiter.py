"""Sliding window rate limiter for Phase 1B.

Provides per-session rate limiting using a sliding window algorithm.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps within a sliding time window.
    If the number of requests exceeds max_requests within the window,
    new requests are rejected.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        """Initialize the rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the window.
            window_seconds: Time window in seconds.
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: list[float] = []
        self._lock = Lock()

    def allow(self) -> bool:
        """Check if a new request is allowed.

        Returns:
            True if allowed, False if rate limited.
        """
        with self._lock:
            now = time.monotonic()
            self._requests = [ts for ts in self._requests if now - ts < self._window_seconds]
            if len(self._requests) < self._max_requests:
                self._requests.append(now)
                return True
            return False

    def reset(self) -> None:
        """Reset the rate limiter (clear all timestamps)."""
        with self._lock:
            self._requests.clear()

    @property
    def remaining(self) -> int:
        """Get remaining requests in current window.

        Returns:
            Number of remaining allowed requests.
        """
        with self._lock:
            now = time.monotonic()
            self._requests = [ts for ts in self._requests if now - ts < self._window_seconds]
            return max(0, self._max_requests - len(self._requests))
