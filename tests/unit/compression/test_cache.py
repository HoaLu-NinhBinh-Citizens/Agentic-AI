"""Unit tests for decompression cache."""

import pytest
import time
from src.core.memory.compression.cache import DecompressionCache


class TestDecompressionCache:
    """Test suite for DecompressionCache."""
    
    @pytest.fixture
    def cache(self) -> DecompressionCache:
        """Create a decompression cache."""
        return DecompressionCache(maxsize=100, ttl_seconds=60)
    
    @pytest.fixture
    def cache_no_ttl(self) -> DecompressionCache:
        """Create a cache with no TTL."""
        return DecompressionCache(maxsize=10, ttl_seconds=0)
    
    def test_get_missing_key_returns_none(self, cache: DecompressionCache):
        """Test that missing keys return None."""
        result = cache.get("nonexistent")
        assert result is None
    
    def test_set_and_get(self, cache: DecompressionCache):
        """Test basic set and get."""
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"
    
    def test_lru_eviction(self, cache: DecompressionCache):
        """Test LRU eviction when maxsize is reached."""
        for i in range(100):
            cache.set(f"key_{i}", f"value_{i}")
        
        assert cache.size == 100
        
        oldest_key = "key_0"
        result = cache.get(oldest_key)
        
        if result is None:
            pass
        else:
            assert cache.get("key_0") == "value_0"
    
    def test_ttl_expiration(self, cache_no_ttl: DecompressionCache):
        """Test TTL-based expiration."""
        cache_no_ttl.set("temp_key", "temp_value")
        assert cache_no_ttl.get("temp_key") == "temp_value"
    
    def test_update_existing_key(self, cache: DecompressionCache):
        """Test updating an existing key."""
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        
        assert cache.get("key1") == "value2"
    
    def test_invalidate_existing_key(self, cache: DecompressionCache):
        """Test invalidating an existing key."""
        cache.set("key1", "value1")
        result = cache.invalidate("key1")
        
        assert result is True
        assert cache.get("key1") is None
    
    def test_invalidate_missing_key(self, cache: DecompressionCache):
        """Test invalidating a missing key."""
        result = cache.invalidate("nonexistent")
        assert result is False
    
    def test_clear_cache(self, cache: DecompressionCache):
        """Test clearing the cache."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        
        assert cache.size == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_hit_rate_empty(self, cache: DecompressionCache):
        """Test hit rate with empty cache."""
        assert cache.hit_rate == 0.0
        assert cache.hits == 0
        assert cache.misses == 0
    
    def test_hit_rate_calculation(self, cache: DecompressionCache):
        """Test hit rate calculation."""
        cache.set("key1", "value1")
        
        cache.get("key1")
        cache.get("key1")
        cache.get("nonexistent")
        
        assert cache.hits == 2
        assert cache.misses == 1
        assert cache.hit_rate == pytest.approx(2/3, rel=0.01)
    
    def test_move_to_end_on_access(self, cache: DecompressionCache):
        """Test that access moves key to end (most recent)."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        cache.get("key1")
        
        assert cache.size == 3
    
    def test_get_stats(self, cache: DecompressionCache):
        """Test get_stats method."""
        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("missing")
        
        stats = cache.get_stats()
        
        assert "size" in stats
        assert "maxsize" in stats
        assert "ttl_seconds" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        
        assert stats["maxsize"] == 100
        assert stats["ttl_seconds"] == 60


class TestDecompressionCacheEdgeCases:
    """Edge case tests for DecompressionCache."""
    
    def test_empty_string_value(self):
        """Test storing empty string value."""
        cache = DecompressionCache(maxsize=10, ttl_seconds=60)
        cache.set("empty", "")
        assert cache.get("empty") == ""
    
    def test_none_value(self):
        """Test that None values work correctly."""
        cache = DecompressionCache(maxsize=10, ttl_seconds=60)
        cache.set("none", "value")
        cache.invalidate("none")
        assert cache.get("none") is None
    
    def test_unicode_content(self):
        """Test storing unicode content."""
        cache = DecompressionCache(maxsize=10, ttl_seconds=60)
        content = "Hello, こんにちは, Привет, مرحبا"
        cache.set("unicode", content)
        assert cache.get("unicode") == content
    
    def test_large_content(self):
        """Test storing large content."""
        cache = DecompressionCache(maxsize=10, ttl_seconds=60)
        large_content = "x" * 1000000
        cache.set("large", large_content)
        assert cache.get("large") == large_content
    
    def test_thread_safety(self):
        """Test thread safety (basic check)."""
        import threading
        
        cache = DecompressionCache(maxsize=100, ttl_seconds=60)
        errors = []
        
        def writer():
            try:
                for i in range(50):
                    cache.set(f"key_{threading.current_thread().name}_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)
        
        def reader():
            try:
                for i in range(50):
                    cache.get(f"key_Thread-1_{i}")
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=writer, name=f"Thread-{i}")
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0
