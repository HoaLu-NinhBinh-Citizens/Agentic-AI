"""Unit tests for extractive summarization strategy."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.memory.compression.strategies.extractive import ExtractiveSummarizer
from src.core.memory.compression.config import ExtractiveConfig


class TestExtractiveSummarizer:
    """Test suite for ExtractiveSummarizer."""
    
    @pytest.fixture
    def summarizer_no_embed(self) -> ExtractiveSummarizer:
        """Create summarizer without embedding service."""
        config = ExtractiveConfig(top_k_ratio=0.3, diversity_lambda=0.5)
        return ExtractiveSummarizer(config=config)
    
    @pytest.fixture
    def summarizer_mock(self) -> ExtractiveSummarizer:
        """Create summarizer with mock embedding service."""
        config = ExtractiveConfig(top_k_ratio=0.5, diversity_lambda=0.5)
        
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[0.1] * 10)
        mock_service.embed_batch = AsyncMock(return_value=[
            [0.1] * 10,
            [0.1] * 10,
            [0.1] * 10,
            [0.1] * 10,
        ])
        
        return ExtractiveSummarizer(
            embedding_service=mock_service,
            config=config
        )
    
    @pytest.mark.asyncio
    async def test_name(self, summarizer_no_embed: ExtractiveSummarizer):
        """Test strategy name."""
        assert summarizer_no_embed.name == "extractive"
    
    @pytest.mark.asyncio
    async def test_split_sentences(self, summarizer_no_embed: ExtractiveSummarizer):
        """Test sentence splitting."""
        content = "Hello. How are you? I'm fine!"
        sentences = summarizer_no_embed._split_sentences(content)
        
        assert len(sentences) == 3
        assert sentences[0] == "Hello."
        assert sentences[1] == "How are you?"
        assert sentences[2] == "I'm fine!"
    
    @pytest.mark.asyncio
    async def test_short_content_unchanged(
        self, summarizer_no_embed: ExtractiveSummarizer
    ):
        """Test that short content (2 sentences) is unchanged."""
        content = "Hello. How are you?"
        compressed, metadata = await summarizer_no_embed.compress(content)
        
        assert compressed == content
        assert metadata.selected_indices is not None
        assert len(metadata.selected_indices) == 2
    
    @pytest.mark.asyncio
    async def test_no_embedding_service_returns_unchanged(
        self, summarizer_no_embed: ExtractiveSummarizer
    ):
        """Test content with no embedding service."""
        content = "First sentence. Second sentence. Third sentence. Fourth sentence."
        compressed, metadata = await summarizer_no_embed.compress(content)
        
        assert compressed == content
        assert metadata.error == "embedding_service_not_available"
    
    @pytest.mark.asyncio
    async def test_compression_with_mock(
        self, summarizer_mock: ExtractiveSummarizer
    ):
        """Test compression with mock embedding service."""
        content = "First. Second. Third. Fourth."
        compressed, metadata = await summarizer_mock.compress(content)
        
        assert metadata.strategy == "extractive"
        assert metadata.selected_indices is not None
    
    @pytest.mark.asyncio
    async def test_mmr_selection(self, summarizer_no_embed: ExtractiveSummarizer):
        """Test MMR selection logic."""
        query = [0.5] * 10
        docs = [
            [0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
            [0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
            [0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
            [0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
            [0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
        ]
        
        selected = summarizer_no_embed._mmr_select(query, docs, k=3, lambda_=0.5)
        
        assert len(selected) == 3
        assert len(set(selected)) == 3
    
    @pytest.mark.asyncio
    async def test_cosine_similarity(self, summarizer_no_embed: ExtractiveSummarizer):
        """Test cosine similarity calculation."""
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        c = [0.0, 1.0, 0.0]
        
        assert summarizer_no_embed._cosine_similarity(a, b) == pytest.approx(1.0)
        assert summarizer_no_embed._cosine_similarity(a, c) == pytest.approx(0.0)
    
    @pytest.mark.asyncio
    async def test_metadata_params(self, summarizer_mock: ExtractiveSummarizer):
        """Test metadata parameters."""
        content = "First. Second. Third. Fourth."
        _, metadata = await summarizer_mock.compress(content)
        
        assert metadata.strategy == "extractive"
    
    @pytest.mark.asyncio
    async def test_decompression_returns_content(
        self, summarizer_no_embed: ExtractiveSummarizer
    ):
        """Test decompression returns content."""
        from src.core.memory.compression.types import CompressionMetadata
        
        content = "First. Second."
        metadata = CompressionMetadata(
            strategy="extractive",
        )
        
        decompressed = await summarizer_no_embed.decompress(content, metadata)
        assert decompressed == content


class TestExtractiveSummarizerEdgeCases:
    """Edge case tests for ExtractiveSummarizer."""
    
    @pytest.fixture
    def summarizer(self) -> ExtractiveSummarizer:
        config = ExtractiveConfig()
        return ExtractiveSummarizer(config=config)
    
    @pytest.mark.asyncio
    async def test_empty_content(self, summarizer: ExtractiveSummarizer):
        """Test empty content handling."""
        content = ""
        compressed, metadata = await summarizer.compress(content)
        
        assert compressed == ""
    
    @pytest.mark.asyncio
    async def test_single_sentence(self, summarizer: ExtractiveSummarizer):
        """Test single sentence content."""
        content = "Only one sentence here."
        compressed, metadata = await summarizer.compress(content)
        
        assert compressed == content
    
    @pytest.mark.asyncio
    async def test_special_characters(self, summarizer: ExtractiveSummarizer):
        """Test content with special characters."""
        content = "Hello! How are you? I'm fine. Let's test..."
        sentences = summarizer._split_sentences(content)
        
        assert len(sentences) > 0
