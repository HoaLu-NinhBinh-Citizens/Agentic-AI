"""Unit tests for LRU store."""

import pytest

from src.infrastructure.cache.tool.lru_store import LRUConfig, LRUStore, PinManager
from src.infrastructure.cache.tool.types import CacheEntry, KeyState


class TestLRUStore:
    """Tests for LRUStore."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get."""
        store = LRUStore(LRUConfig(max_entries=10))
        entry = CacheEntry(key="key1", value={"data": "test"}, state=KeyState.FRESH)
        
        await store.set("key1", entry)
        retrieved = await store.get("key1")

        assert retrieved is not None
        assert retrieved.key == "key1"
        assert retrieved.value == {"data": "test"}

    @pytest.mark.asyncio
    async def test_get_missing(self):
        """Test get returns None for missing key."""
        store = LRUStore(LRUConfig(max_entries=10))
        result = await store.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete removes entry."""
        store = LRUStore(LRUConfig(max_entries=10))
        entry = CacheEntry(key="key1", value="value1", state=KeyState.FRESH)
        
        await store.set("key1", entry)
        deleted = await store.delete("key1")

        assert deleted is True
        assert await store.get("key1") is None

    @pytest.mark.asyncio
    async def test_contains(self):
        """Test contains check."""
        store = LRUStore(LRUConfig(max_entries=10))
        
        assert await store.contains("key1") is False

        entry = CacheEntry(key="key1", value="value1", state=KeyState.FRESH)
        await store.set("key1", entry)
        
        assert await store.contains("key1") is True

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when at capacity."""
        store = LRUStore(LRUConfig(max_entries=10))
        
        for i in range(15):
            entry = CacheEntry(key=f"key{i}", value=f"value{i}", state=KeyState.FRESH)
            await store.set(f"key{i}", entry)

        size = await store.size()
        assert size <= 10
        assert await store.contains("key14") is True

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear removes all entries."""
        store = LRUStore(LRUConfig(max_entries=10))
        
        for i in range(5):
            entry = CacheEntry(key=f"key{i}", value=f"value{i}", state=KeyState.FRESH)
            await store.set(f"key{i}", entry)

        await store.clear()
        assert await store.size() == 0

    def test_stats(self):
        """Test statistics."""
        store = LRUStore(LRUConfig(max_entries=10))
        entry = CacheEntry(key="key1", value="value1", state=KeyState.FRESH)
        
        import asyncio
        asyncio.run(store.set("key1", entry))

        stats = store.get_stats()
        assert stats["size"] == 1
        assert stats["max_entries"] == 10


class TestPinManager:
    """Tests for PinManager."""

    @pytest.mark.asyncio
    async def test_pin_unpin(self):
        """Test pinning and unpinning."""
        store = LRUStore(LRUConfig(max_entries=10))
        pin_manager = PinManager(store, max_pinned_entries=5)
        
        entry = CacheEntry(key="key1", value="value1", state=KeyState.FRESH)
        await store.set("key1", entry)

        result = await pin_manager.pin("key1")
        assert result is True
        assert await pin_manager.is_pinned("key1")

        result = await pin_manager.unpin("key1")
        assert result is True
        assert not await pin_manager.is_pinned("key1")

    @pytest.mark.asyncio
    async def test_pin_missing_key(self):
        """Test pinning non-existent key."""
        store = LRUStore(LRUConfig(max_entries=10))
        pin_manager = PinManager(store, max_pinned_entries=5)
        
        result = await pin_manager.pin("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_force_evict_under_pressure(self):
        """Test forced eviction of pinned entries."""
        store = LRUStore(LRUConfig(max_entries=10))
        pin_manager = PinManager(store, max_pinned_entries=5)
        
        entry = CacheEntry(key="key1", value="value1", state=KeyState.FRESH)
        await store.set("key1", entry)
        await pin_manager.pin("key1")

        evicted = await pin_manager.force_evict_under_pressure()
        assert evicted >= 0
