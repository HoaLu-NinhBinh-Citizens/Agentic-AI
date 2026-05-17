"""Unit tests for rate limiter."""

import asyncio
import pytest
import time

from src.infrastructure.cache.tool.rate_limiter import (
    FairQueue,
    RateLimitConfig,
    TokenBucket,
    ToolRateLimiter,
)


class TestTokenBucket:
    """Tests for TokenBucket."""

    def test_initial_tokens(self):
        """Test initial token count equals burst."""
        bucket = TokenBucket(rate=10.0, burst=5.0)
        assert bucket.available_tokens == 5.0

    def test_acquire_success(self):
        """Test successful token acquisition."""
        bucket = TokenBucket(rate=10.0, burst=5.0)
        result = asyncio.run(bucket.acquire(1.0))

        assert result is True
        assert bucket.available_tokens < 5.0

    def test_acquire_failure(self):
        """Test failed token acquisition when empty."""
        bucket = TokenBucket(rate=1.0, burst=1.0)

        bucket._tokens = 0
        result = asyncio.run(bucket.acquire(1.0))

        assert result is False

    def test_token_refill(self):
        """Test tokens refill over time."""
        bucket = TokenBucket(rate=10.0, burst=10.0)
        bucket._tokens = 0

        time.sleep(0.1)

        tokens = bucket.available_tokens
        assert tokens >= 0.9


class TestFairQueue:
    """Tests for FairQueue."""

    @pytest.fixture
    def queue(self):
        """Create a fresh fair queue."""
        return FairQueue()

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue):
        """Test enqueue and dequeue."""
        event = await queue.enqueue("key1")
        assert event is not None

        key = await queue.dequeue()
        assert key == "key1"

    @pytest.mark.asyncio
    async def test_multiple_keys_round_robin(self, queue):
        """Test round-robin ordering."""
        await queue.enqueue("key1")
        await queue.enqueue("key2")
        await queue.enqueue("key3")

        keys = []
        for _ in range(3):
            key = await queue.dequeue()
            if key:
                keys.append(key)

        assert len(keys) == 3

    @pytest.mark.asyncio
    async def test_remove(self, queue):
        """Test removing a key."""
        await queue.enqueue("key1")
        await queue.remove("key1")

        key = await queue.dequeue()
        assert key is None


class TestToolRateLimiter:
    """Tests for ToolRateLimiter."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh rate limiter."""
        config = RateLimitConfig(
            global_rate=100.0,
            global_burst=50.0,
            tool_rate=20.0,
            tool_burst=10.0,
        )
        return ToolRateLimiter(config)

    @pytest.mark.asyncio
    async def test_acquire_success(self, limiter):
        """Test successful acquire."""
        result = await limiter.acquire("tool1", "key1")
        assert result is True

    @pytest.mark.asyncio
    async def test_cooldown_key_rejected(self, limiter):
        """Test key in cooldown is rejected."""
        limiter.set_key_cooldown("key1", 10.0)

        result = await limiter.acquire("tool1", "key1")
        assert result is False

    @pytest.mark.asyncio
    async def test_different_keys_allowed(self, limiter):
        """Test different keys are independent."""
        assert await limiter.acquire("tool1", "key1") is True
        assert await limiter.acquire("tool1", "key2") is True
        assert await limiter.acquire("tool1", "key3") is True

    @pytest.mark.asyncio
    async def test_tool_weight(self, limiter):
        """Test tool weight adjustment."""
        await limiter.set_tool_weight("tool1", 2.0)

        stats = limiter.get_stats()
        assert stats["tools"]["tool1"]["rate"] == 40.0

    @pytest.mark.asyncio
    async def test_reset(self, limiter):
        """Test reset clears all state."""
        await limiter.acquire("tool1", "key1")
        await limiter.reset()

        stats = limiter.get_stats()
        assert len(stats["tools"]) == 0
