"""Unit tests for SlidingWindowRateLimiter."""

from __future__ import annotations

import pytest
from core.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    """Test suite for SlidingWindowRateLimiter."""

    def setup_method(self):
        """Create a fresh rate limiter for each test."""
        self.rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=1.0)

    def test_allow_within_limit(self):
        """Test that requests within limit are allowed."""
        assert self.rl.allow() is True
        assert self.rl.allow() is True
        assert self.rl.allow() is True

    def test_deny_when_exceeded(self):
        """Test that requests exceeding limit are denied."""
        assert self.rl.allow() is True
        assert self.rl.allow() is True
        assert self.rl.allow() is True
        assert self.rl.allow() is False

    def test_reset_clears_requests(self):
        """Test that reset clears all timestamps."""
        assert self.rl.allow() is True
        assert self.rl.allow() is True
        self.rl.reset()
        assert self.rl.allow() is True
        assert self.rl.allow() is True
        assert self.rl.allow() is True

    def test_remaining_count(self):
        """Test that remaining count is correct."""
        assert self.rl.remaining == 3
        self.rl.allow()
        assert self.rl.remaining == 2
        self.rl.allow()
        assert self.rl.remaining == 1
        self.rl.allow()
        assert self.rl.remaining == 0

    def test_window_expiry(self):
        """Test that requests expire after window."""
        import time

        rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False
        time.sleep(0.15)
        assert rl.allow() is True

    def test_concurrent_access(self):
        """Test thread-safe access to rate limiter."""
        import threading

        rl = SlidingWindowRateLimiter(max_requests=10, window_seconds=1.0)
        results = []

        def worker():
            result = rl.allow()
            results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = sum(results)
        assert allowed == 10
