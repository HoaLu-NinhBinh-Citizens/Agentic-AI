"""Unit tests for Vector Embeddings."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.memory.vector_embeddings import (
    EmbeddingModel,
    EmbeddingError,
    VectorEntry,
    VectorStore,
    SemanticMemory,
    get_semantic_memory,
)
import numpy as np


class TestVectorStore:
    """Tests for VectorStore."""

    def test_create_empty(self):
        """Test creating empty store."""
        store = VectorStore(dimension=384)
        
        assert store.dimension == 384
        assert len(store.entries) == 0

    def test_add_entry(self):
        """Test adding an entry."""
        store = VectorStore(dimension=3)
        entry = VectorEntry(
            id="test-1",
            content="Test content",
            embedding=np.array([0.1, 0.2, 0.3]),
        )
        
        store.add(entry)
        
        assert "test-1" in store.entries
        assert store.entries["test-1"].content == "Test content"

    def test_add_wrong_dimension(self):
        """Test adding entry with wrong dimension."""
        store = VectorStore(dimension=3)
        entry = VectorEntry(
            id="test-1",
            content="Test",
            embedding=np.array([0.1, 0.2]),  # Wrong dim
        )
        
        with pytest.raises(ValueError):
            store.add(entry)

    def test_search_basic(self):
        """Test basic vector search."""
        store = VectorStore(dimension=3)
        
        # Add entries with known vectors
        store.add(VectorEntry(
            id="a",
            content="Apple",
            embedding=np.array([1.0, 0.0, 0.0]),
        ))
        store.add(VectorEntry(
            id="b",
            content="Banana",
            embedding=np.array([0.0, 1.0, 0.0]),
        ))
        store.add(VectorEntry(
            id="c",
            content="Cherry",
            embedding=np.array([0.0, 0.0, 1.0]),
        ))
        
        # Search for "Apple" direction
        query = np.array([0.9, 0.1, 0.0])
        results = store.search(query, limit=2)
        
        assert len(results) > 0
        assert results[0][0] == "a"  # Should be most similar to Apple

    def test_search_with_filter(self):
        """Test search with ID filter."""
        store = VectorStore(dimension=2)
        
        store.add(VectorEntry(
            id="a",
            content="Alpha",
            embedding=np.array([1.0, 1.0]),
        ))
        store.add(VectorEntry(
            id="b",
            content="Beta",
            embedding=np.array([1.0, 1.0]),
        ))
        
        results = store.search(
            np.array([1.0, 1.0]),
            filter_ids={"a"},
        )
        
        assert len(results) == 1
        assert results[0][0] == "a"

    def test_search_min_score(self):
        """Test minimum score filtering."""
        store = VectorStore(dimension=2)
        
        store.add(VectorEntry(
            id="a",
            content="Similar",
            embedding=np.array([1.0, 0.0]),
        ))
        store.add(VectorEntry(
            id="b",
            content="Different",
            embedding=np.array([-0.5, -0.5]),
        ))
        
        # Search with high min_score
        results = store.search(
            np.array([1.0, 0.0]),
            min_score=0.9,
        )
        
        assert len(results) == 1
        assert results[0][0] == "a"


class TestEmbeddingModel:
    """Tests for EmbeddingModel."""

    def test_model_creation(self):
        """Test creating embedding model."""
        model = EmbeddingModel(
            model_name="test-model",
            backend="auto",
        )
        
        assert model.model_name == "test-model"
        assert model.backend == "auto"

    def test_normalize_embeddings(self):
        """Test embedding normalization."""
        model = EmbeddingModel(normalize=True)
        
        embeddings = np.array([
            [3.0, 4.0],  # Should normalize to [0.6, 0.8]
            [0.0, 5.0],  # Should normalize to [0.0, 1.0]
        ])
        
        normalized = model._normalize_embeddings(embeddings)
        
        # Check that norms are 1
        norms = np.linalg.norm(normalized, axis=1)
        assert np.allclose(norms, 1.0)


class TestSemanticMemory:
    """Tests for SemanticMemory."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create test memory."""
        return SemanticMemory(
            project_id="test-project",
            project_path=tmp_path,
        )

    @pytest.mark.asyncio
    async def test_add_memory(self, memory):
        """Test adding memory with embedding."""
        # Mock the embedding model - must match dimension
        memory.embedding_model.encode = MagicMock(
            return_value=np.array([[0.1, 0.2, 0.3, 0.4] + [0.0] * 380])  # 384 dim
        )
        
        entry_id = await memory.add(
            content="STM32 has SPI peripheral",
            metadata={"source": "manual"},
        )
        
        assert entry_id is not None
        assert entry_id in memory.vector_store.entries

    @pytest.mark.asyncio
    async def test_keyword_indexing(self, memory):
        """Test keyword indexing."""
        memory.embedding_model.encode = MagicMock(
            return_value=np.array([[0.1, 0.2, 0.3, 0.4] + [0.0] * 380])  # 384 dim
        )
        
        await memory.add("Test content for indexing")
        
        assert "test" in memory.keyword_index
        assert "content" in memory.keyword_index
        assert "indexing" in memory.keyword_index

    @pytest.mark.asyncio
    async def test_search_hybrid(self, memory):
        """Test hybrid search."""
        # Mock embedding - must be 384 dimensions
        def mock_encode(texts):
            return np.array([[0.5, 0.5] + [0.0] * 382])  # 384 dim
        
        memory.embedding_model.encode = mock_encode
        
        await memory.add("Python is a programming language")
        await memory.add("Rust is a systems language")
        
        results = await memory.search("programming", limit=5)
        
        assert isinstance(results, list)

    def test_singleton(self, tmp_path, monkeypatch):
        """Test singleton pattern."""
        # Reset global
        import src.infrastructure.memory.vector_embeddings as ve
        ve._semantic_memory = None
        
        mem1 = get_semantic_memory("project-a")
        mem2 = get_semantic_memory("project-a")
        
        assert mem1 is mem2


class TestIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_memory_workflow(self, tmp_path):
        """Test full memory workflow."""
        # Mock embedding generation - must be 384 dimensions
        def mock_encode(texts):
            # Simple deterministic embedding
            embedding = [0.0] * 384
            if "stm32" in str(texts).lower():
                embedding[0] = 1.0
            elif "python" in str(texts).lower():
                embedding[1] = 1.0
            return np.array([embedding])
        
        memory = SemanticMemory(
            project_id="integration-test",
            project_path=tmp_path,
        )
        memory.embedding_model.encode = mock_encode
        
        # Add memories
        await memory.add("STM32F4 has SPI peripheral")
        await memory.add("Python is a great language")
        await memory.add("Rust is fast")
        
        # Search
        results = await memory.search("STM32 hardware", limit=5)
        
        assert len(results) > 0
        assert results[0]["type"] == "hybrid"
