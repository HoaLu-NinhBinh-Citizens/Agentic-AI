"""Tests for the rate limit store."""

import pytest
from infrastructure.resilience.rate_limit_store import (
    InMemoryRateLimitStore,
    RateLimitState,
    RateLimitStore,
    SlidingWindowRateLimiterV2,
)


class TestInMemoryRateLimitStore:
    """Tests for InMemoryRateLimitStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryRateLimitStore()

    @pytest.mark.asyncio
    async def test_get_timestamps_returns_empty_for_new_key(self, store):
        """Test that get_timestamps returns empty list for new key."""
        timestamps = await store.get_timestamps("new_key")
        assert timestamps == []

    @pytest.mark.asyncio
    async def test_add_and_get_timestamps(self, store):
        """Test adding and retrieving timestamps."""
        await store.add_timestamp("key1", 1000.0)
        await store.add_timestamp("key1", 1001.0)

        timestamps = await store.get_timestamps("key1")
        assert timestamps == [1000.0, 1001.0]

    @pytest.mark.asyncio
    async def test_clear_expired(self, store):
        """Test clearing expired timestamps."""
        await store.add_timestamp("key1", 1000.0)
        await store.add_timestamp("key1", 1002.0)
        await store.add_timestamp("key1", 1005.0)

        # Clear timestamps older than 1003
        await store.clear_expired("key1", 1003.0)

        timestamps = await store.get_timestamps("key1")
        assert timestamps == [1005.0]

    @pytest.mark.asyncio
    async def test_clear_all(self, store):
        """Test clearing all state."""
        await store.add_timestamp("key1", 1000.0)
        await store.add_timestamp("key2", 1000.0)

        await store.clear_all()

        assert await store.get_timestamps("key1") == []
        assert await store.get_timestamps("key2") == []


class TestSlidingWindowRateLimiterV2:
    """Tests for SlidingWindowRateLimiterV2."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh limiter for each test."""
        return SlidingWindowRateLimiterV2(max_calls=3, period=1.0)

    @pytest.mark.asyncio
    async def test_allows_within_limit(self, limiter):
        """Test that requests within limit are allowed."""
        assert await limiter.acquire("key1")
        assert await limiter.acquire("key1")
        assert await limiter.acquire("key1")
        assert await limiter.get_remaining("key1") == 0

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self, limiter):
        """Test that requests at limit are blocked."""
        await limiter.acquire("key1")
        await limiter.acquire("key1")
        await limiter.acquire("key1")

        assert not await limiter.acquire("key1")

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, limiter):
        """Test that different keys have independent limits."""
        await limiter.acquire("key1")
        await limiter.acquire("key1")
        await limiter.acquire("key1")

        # key2 should still have capacity
        assert await limiter.acquire("key2")
        assert await limiter.get_remaining("key2") == 2

    @pytest.mark.asyncio
    async def test_window_expiry(self, limiter):
        """Test that old timestamps expire after the window."""
        import time
        import asyncio

        # Add two calls
        await limiter.acquire("key1")
        await limiter.acquire("key1")

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should have room again
        assert await limiter.get_remaining("key1") == 3

    @pytest.mark.asyncio
    async def test_get_remaining(self, limiter):
        """Test get_remaining returns correct count."""
        assert await limiter.get_remaining("key1") == 3

        await limiter.acquire("key1")
        assert await limiter.get_remaining("key1") == 2

        await limiter.acquire("key1")
        assert await limiter.get_remaining("key1") == 1

        await limiter.acquire("key1")
        assert await limiter.get_remaining("key1") == 0

    @pytest.mark.asyncio
    async def test_with_custom_store(self):
        """Test using a custom store."""
        store = InMemoryRateLimitStore()
        limiter = SlidingWindowRateLimiterV2(max_calls=2, period=1.0, store=store)

        assert await limiter.acquire("key1")
        assert await limiter.acquire("key1")
        assert not await limiter.acquire("key1")
