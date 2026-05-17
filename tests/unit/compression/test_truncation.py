"""Unit tests for truncation compression strategy."""

import pytest
from src.core.memory.compression.strategies.truncation import TruncationCompressor
from src.core.memory.compression.config import TruncationConfig
from src.core.memory.compression.types import CompressionMetadata


class TestTruncationCompressor:
    """Test suite for TruncationCompressor."""
    
    @pytest.fixture
    def compressor(self) -> TruncationCompressor:
        """Create a truncation compressor."""
        config = TruncationConfig(max_chars=200, keep_both_ends=True)
        return TruncationCompressor(config)
    
    @pytest.fixture
    def no_end_compressor(self) -> TruncationCompressor:
        """Create a compressor without keeping ends."""
        config = TruncationConfig(max_chars=100, keep_both_ends=False)
        return TruncationCompressor(config)
    
    @pytest.mark.asyncio
    async def test_name(self, compressor: TruncationCompressor):
        """Test strategy name."""
        assert compressor.name == "truncation"
    
    @pytest.mark.asyncio
    async def test_short_content_unchanged(self, compressor: TruncationCompressor):
        """Test that short content is returned unchanged."""
        short_content = "Hello, world!"
        compressed, metadata = await compressor.compress(short_content)
        
        assert compressed == short_content
        assert metadata.strategy == "truncation"
        assert metadata.original_hash is not None
    
    @pytest.mark.asyncio
    async def test_long_content_truncated(self, compressor: TruncationCompressor):
        """Test that long content is truncated."""
        long_content = "A" * 500
        compressed, metadata = await compressor.compress(long_content)
        
        assert len(compressed) <= 200
        assert "..." in compressed
        assert metadata.params["keep_both_ends"] is True
    
    @pytest.mark.asyncio
    async def test_truncation_keeps_ends(self, compressor: TruncationCompressor):
        """Test that both ends are kept."""
        content = "BEGIN" + "X" * 500 + "END"
        compressed, metadata = await compressor.compress(content)
        
        assert compressed.startswith("BEGIN")
        assert compressed.endswith("END")
        assert "..." in compressed
    
    @pytest.mark.asyncio
    async def test_truncation_no_keep_ends(self, no_end_compressor: TruncationCompressor):
        """Test truncation without keeping ends."""
        content = "BEGIN" + "X" * 500 + "END"
        compressed, metadata = await no_end_compressor.compress(content)
        
        assert compressed.startswith("BEGIN")
        assert not compressed.endswith("END")
        assert "..." not in compressed
        assert len(compressed) == 100
    
    @pytest.mark.asyncio
    async def test_metadata_params(self, compressor: TruncationCompressor):
        """Test metadata contains correct parameters."""
        long_content = "A" * 500
        _, metadata = await compressor.compress(long_content)
        
        assert metadata.params["max_chars"] == 200
        assert metadata.params["keep_both_ends"] is True
        assert metadata.original_hash is not None
    
    @pytest.mark.asyncio
    async def test_decompression_returns_content(self, compressor: TruncationCompressor):
        """Test decompression returns the (truncated) content."""
        content = "A" * 500
        compressed, metadata = await compressor.compress(content)
        
        decompressed = await compressor.decompress(compressed, metadata)
        
        assert decompressed == compressed
    
    @pytest.mark.asyncio
    async def test_hash_verification(self, compressor: TruncationCompressor):
        """Test that hash is preserved in metadata."""
        content = "Test content for hashing"
        _, metadata = await compressor.compress(content)
        
        assert metadata.original_hash is not None
        assert len(metadata.original_hash) == 64
    
    @pytest.mark.asyncio
    async def test_empty_content(self, compressor: TruncationCompressor):
        """Test handling of empty content."""
        compressed, metadata = await compressor.compress("")
        
        assert compressed == ""
        assert metadata.original_hash is not None
    
    @pytest.mark.asyncio
    async def test_exact_max_chars(self, compressor: TruncationCompressor):
        """Test content exactly at max_chars."""
        exact_content = "A" * 200
        compressed, metadata = await compressor.compress(exact_content)
        
        assert compressed == exact_content
        assert metadata.original_hash is not None
