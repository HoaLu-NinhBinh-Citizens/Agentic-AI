"""Unit tests for EmbeddingService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.embeddings.embedding_service import EmbeddingService, EmbeddingCache


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        return EmbeddingCache(maxsize=3)

    @pytest.mark.asyncio
    async def test_cache_put_and_get(self, cache):
        """Test putting and getting from cache."""
        await cache.put("key1", [0.1, 0.2, 0.3])
        result = await cache.get("key1")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        """Test cache miss."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self, cache):
        """Test LRU eviction when cache is full."""
        await cache.put("key1", [0.1])
        await cache.put("key2", [0.2])
        await cache.put("key3", [0.3])
        await cache.put("key4", [0.4])

        result = await cache.get("key1")
        assert result is None

        result = await cache.get("key4")
        assert result == [0.4]

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache):
        """Test clearing cache."""
        await cache.put("key1", [0.1])
        await cache.clear()

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_size(self, cache):
        """Test cache size tracking."""
        await cache.put("key1", [0.1])
        await cache.put("key2", [0.2])

        assert cache.size == 2


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.fixture
    def service(self):
        """Create an embedding service."""
        return EmbeddingService(cache_maxsize=100)

    def test_initialization(self, service):
        """Test service initialization."""
        assert service._url == "http://localhost:11434/api/embeddings"
        assert service._model == "bge-m3:latest"
        assert service._dimension is None

    @pytest.mark.asyncio
    async def test_embed_empty_text(self, service):
        """Test embedding empty text returns empty list."""
        result = await service.embed("")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_whitespace_only(self, service):
        """Test embedding whitespace-only text returns empty list."""
        result = await service.embed("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_caches_result(self, service):
        """Test that embed caches results for same text."""
        text = "test text for caching"

        cached_embedding = [0.1, 0.2, 0.3]
        cache_key = service._make_cache_key(text)
        await service._cache.put(cache_key, cached_embedding)

        result = await service.embed(text)

        assert result == cached_embedding

    def test_make_cache_key(self, service):
        """Test cache key generation."""
        key1 = service._make_cache_key("test")
        key2 = service._make_cache_key("test")
        key3 = service._make_cache_key("different")

        assert key1 == key2
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_get_stats(self, service):
        """Test getting service statistics."""
        stats = await service.get_stats()

        assert "cache_size" in stats
        assert "cache_maxsize" in stats
        assert "dimension" in stats
        assert "model" in stats

    @pytest.mark.asyncio
    async def test_health_check_failure(self, service):
        """Test health check when service is down."""
        with patch.object(service, 'embed', return_value=[]):
            result = await service.health_check()
            assert result is False

    def test_dimension_property(self, service):
        """Test dimension property."""
        assert service.dimension is None

        service._dimension = 1024
        assert service.dimension == 1024
