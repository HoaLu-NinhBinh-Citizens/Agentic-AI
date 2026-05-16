"""Unit tests for DeduplicationEngine."""

import pytest

from core.memory.deduplication import DeduplicationEngine, COSINE_THRESHOLD


class TestDeduplicationEngine:
    """Tests for DeduplicationEngine."""

    @pytest.fixture
    def dedup(self):
        """Create a deduplication engine."""
        return DeduplicationEngine(window_size=5, enable_bloom=False)

    def test_initialization(self, dedup):
        """Test engine initialization."""
        assert dedup._window_size == 5
        assert dedup._enable_bloom is False

    @pytest.mark.asyncio
    async def test_empty_window(self, dedup):
        """Test no duplicates when window is empty."""
        embedding = [0.1] * 10
        result = await dedup.check_semantic_duplicate(embedding)
        assert result is False

    @pytest.mark.asyncio
    async def test_add_embedding(self, dedup):
        """Test adding embedding to window."""
        embedding = [0.1] * 10
        await dedup.add_embedding(embedding, "test content")

        stats = await dedup.get_stats()
        assert stats["recent_count"] == 1

    @pytest.mark.asyncio
    async def test_semantic_duplicate_detected(self, dedup):
        """Test semantic duplicate detection."""
        embedding = [0.1] * 10
        await dedup.add_embedding(embedding, "original content")

        similar = [0.1] * 10
        result = await dedup.check_semantic_duplicate(similar)
        assert result is True

    @pytest.mark.asyncio
    async def test_different_embeddings_not_duplicate(self, dedup):
        """Test different embeddings are not duplicates."""
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0]

        await dedup.add_embedding(embedding1, "content 1")
        result = await dedup.check_semantic_duplicate(embedding2)

        assert result is False

    @pytest.mark.asyncio
    async def test_exact_duplicate_check(self, dedup):
        """Test exact duplicate check with Bloom disabled."""
        result = await dedup.check_exact_duplicate("test content")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_and_add(self, dedup):
        """Test check_and_add method."""
        embedding = [0.1] * 10

        is_dup, reason = await dedup.check_and_add("new content", embedding)

        assert is_dup is False
        assert reason == ""

    @pytest.mark.asyncio
    async def test_reset(self, dedup):
        """Test resetting the engine."""
        embedding = [0.1] * 10
        await dedup.add_embedding(embedding, "content")

        await dedup.reset()

        stats = await dedup.get_stats()
        assert stats["recent_count"] == 0

    @pytest.mark.asyncio
    async def test_vector_normalization(self, dedup):
        """Test vector normalization."""
        vector = [3.0, 4.0]
        normalized = dedup._normalize_vector(vector)

        magnitude = sum(x * x for x in normalized) ** 0.5
        assert abs(magnitude - 1.0) < 0.0001

    @pytest.mark.asyncio
    async def test_cosine_similarity(self, dedup):
        """Test cosine similarity calculation."""
        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0]

        sim = dedup._cosine_similarity(vec1, vec2)
        assert abs(sim - 1.0) < 0.0001

    @pytest.mark.asyncio
    async def test_get_recent_content(self, dedup):
        """Test getting recent content."""
        await dedup.add_embedding([0.1] * 10, "content 1")
        await dedup.add_embedding([0.2] * 10, "content 2")

        recent = await dedup.get_recent_content(limit=10)

        assert len(recent) == 2
        assert "content 1" in recent
        assert "content 2" in recent


class TestBloomFilterDisabled:
    """Tests for when Bloom filter is disabled."""

    @pytest.fixture
    def dedup_no_bloom(self):
        """Create engine without Bloom filter."""
        return DeduplicationEngine(enable_bloom=False)

    @pytest.mark.asyncio
    async def test_bloom_disabled(self, dedup_no_bloom):
        """Test Bloom filter is disabled."""
        result = await dedup_no_bloom.check_exact_duplicate("content")
        assert result is False

    @pytest.mark.asyncio
    async def test_bloom_add_noop(self, dedup_no_bloom):
        """Test adding to disabled Bloom."""
        await dedup_no_bloom.add_exact("content")
