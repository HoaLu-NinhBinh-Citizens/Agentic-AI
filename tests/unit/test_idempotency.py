"""Tests for the idempotency store."""

import pytest
from core.execution.idempotency import (
    IdempotencyRecord,
    IdempotencyStore,
    InMemoryIdempotencyStore,
)


class TestInMemoryIdempotencyStore:
    """Tests for InMemoryIdempotencyStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryIdempotencyStore(ttl_seconds=5.0)

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(self, store):
        """Test that get returns None for non-existent key."""
        result = await store.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, store):
        """Test storing and retrieving a result."""
        result_data = {"success": True, "content": ["hello"]}
        await store.set("key1", result_data)

        cached = await store.get("key1")
        assert cached == result_data

    @pytest.mark.asyncio
    async def test_delete_removes_entry(self, store):
        """Test that delete removes the cached entry."""
        await store.set("key1", {"success": True})
        assert await store.get("key1") is not None

        await store.delete("key1")
        assert await store.get("key1") is None

    @pytest.mark.asyncio
    async def test_clear_expired_removes_old_entries(self, store):
        """Test that clear_expired removes entries past TTL."""
        store._ttl = 0.1  # Very short TTL for testing

        await store.set("key1", {"success": True})

        import asyncio
        await asyncio.sleep(0.2)  # Wait for TTL to expire

        count = await store.clear_expired()
        assert count == 1
        assert await store.get("key1") is None

    @pytest.mark.asyncio
    async def test_get_returns_none_for_expired_entry(self, store):
        """Test that get returns None for expired entry."""
        store._ttl = 0.1  # Very short TTL

        await store.set("key1", {"success": True})

        import asyncio
        await asyncio.sleep(0.2)  # Wait for TTL to expire

        result = await store.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_size(self, store):
        """Test the size method."""
        assert await store.size() == 0

        await store.set("key1", {"success": True})
        assert await store.size() == 1

        await store.set("key2", {"success": True})
        assert await store.size() == 2

        await store.delete("key1")
        assert await store.size() == 1

    @pytest.mark.asyncio
    async def test_clear(self, store):
        """Test clearing all entries."""
        await store.set("key1", {"success": True})
        await store.set("key2", {"success": True})
        assert await store.size() == 2

        await store.clear()
        assert await store.size() == 0

    @pytest.mark.asyncio
    async def test_multiple_keys_independent(self, store):
        """Test that multiple keys are tracked independently."""
        await store.set("key1", {"data": "one"})
        await store.set("key2", {"data": "two"})
        await store.set("key3", {"data": "three"})

        assert await store.get("key1") == {"data": "one"}
        assert await store.get("key2") == {"data": "two"}
        assert await store.get("key3") == {"data": "three"}

        await store.delete("key2")
        assert await store.get("key1") == {"data": "one"}
        assert await store.get("key2") is None
        assert await store.get("key3") == {"data": "three"}
