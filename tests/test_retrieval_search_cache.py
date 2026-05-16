"""
Tests for retrieval search cache with TTL-based eviction.
"""

import time

import pytest

from src.retrieval.search_cache import SearchCache, get_search_cache, clear_search_cache


class TestSearchCache:
    """Tests for SearchCache class."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache with short TTL for testing."""
        return SearchCache(ttl_seconds=1, max_entries=10)

    def test_cache_set_and_get(self, cache):
        """Should store and retrieve values."""
        cache.set("query1", ["result1", "result2"])
        result = cache.get("query1")

        assert result == ["result1", "result2"]

    def test_cache_miss(self, cache):
        """Should return None for missing keys."""
        assert cache.get("nonexistent") is None

    def test_cache_expiration(self, cache):
        """Should expire entries after TTL."""
        cache.set("query1", ["result"])

        # Should be available immediately
        assert cache.get("query1") == ["result"]

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert cache.get("query1") is None

    def test_cache_eviction_on_capacity(self):
        """Should evict oldest entries when at capacity."""
        cache = SearchCache(ttl_seconds=60, max_entries=3)

        cache.set("query1", ["result1"])
        time.sleep(0.01)
        cache.set("query2", ["result2"])
        time.sleep(0.01)
        cache.set("query3", ["result3"])

        # Should be full
        assert cache.size == 3

        # Adding new entry should evict oldest
        cache.set("query4", ["result4"])

        # Oldest (query1) should be evicted
        assert cache.size == 3
        assert cache.get("query1") is None
        assert cache.get("query2") == ["result2"]
        assert cache.get("query3") == ["result3"]
        assert cache.get("query4") == ["result4"]

    def test_cache_invalidate(self, cache):
        """Should remove specific entry."""
        cache.set("query1", ["result1"])
        cache.set("query2", ["result2"])

        assert cache.invalidate("query1") is True
        assert cache.get("query1") is None
        assert cache.get("query2") == ["result2"]

        # Invalidate non-existent
        assert cache.invalidate("nonexistent") is False

    def test_cache_clear(self, cache):
        """Should clear all entries."""
        cache.set("query1", ["result1"])
        cache.set("query2", ["result2"])

        cache.clear()

        assert cache.size == 0
        assert cache.get("query1") is None
        assert cache.get("query2") is None

    def test_cache_stats(self, cache):
        """Should return correct statistics."""
        cache.set("query1", ["result1"])
        time.sleep(0.01)
        cache.set("query2", ["result2"])

        stats = cache.stats

        assert stats["size"] == 2
        assert stats["max_entries"] == 10
        assert stats["ttl_seconds"] == 1
        assert stats["avg_age_seconds"] >= 0
        assert stats["oldest_age_seconds"] >= 0

    def test_cache_size_property(self, cache):
        """Size should reflect actual entry count."""
        assert cache.size == 0

        cache.set("query1", ["result1"])
        assert cache.size == 1

        cache.set("query2", ["result2"])
        assert cache.size == 2

        # Evict expired
        time.sleep(1.1)
        assert cache.size == 0

    def test_cache_empty_result(self, cache):
        """Should handle empty results."""
        cache.set("query1", [])
        result = cache.get("query1")

        assert result == []


class TestGlobalCache:
    """Tests for global cache instance."""

    def test_get_search_cache_returns_singleton(self):
        """Should return same instance on multiple calls."""
        clear_search_cache()
        cache1 = get_search_cache()
        cache2 = get_search_cache()

        assert cache1 is cache2

    def test_clear_search_cache(self):
        """Should clear global cache."""
        cache = get_search_cache()
        cache.set("query1", ["result1"])

        clear_search_cache()

        assert cache.size == 0

    def test_global_cache_shares_state(self):
        """Global cache should be shared across instances."""
        clear_search_cache()

        cache1 = get_search_cache()
        cache1.set("shared_key", ["shared_result"])

        cache2 = get_search_cache()
        assert cache2.get("shared_key") == ["shared_result"]
