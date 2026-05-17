"""Unit tests for types module."""

import pytest
import json
import time
from src.core.memory.compression.types import (
    CompressionMetadata,
    CompressionResult,
    MemoryItem,
    CacheItem,
    CompressionStats,
    CompressionStrategyType,
)


class TestCompressionMetadata:
    """Test suite for CompressionMetadata."""
    
    def test_creation(self):
        """Test basic creation."""
        metadata = CompressionMetadata(
            strategy="truncation",
            params={"max_chars": 100},
            original_hash="abc123",
        )
        
        assert metadata.strategy == "truncation"
        assert metadata.params["max_chars"] == 100
        assert metadata.original_hash == "abc123"
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = CompressionMetadata(
            strategy="extractive",
            selected_indices=[0, 2, 4],
        )
        
        d = metadata.to_dict()
        
        assert d["strategy"] == "extractive"
        assert d["selected_indices"] == [0, 2, 4]
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "strategy": "kv_compact",
            "kept_fields": ["field1", "field2"],
            "semantic_similarity": 0.92,
        }
        
        metadata = CompressionMetadata.from_dict(data)
        
        assert metadata.strategy == "kv_compact"
        assert metadata.kept_fields == ["field1", "field2"]
        assert metadata.semantic_similarity == 0.92
    
    def test_to_json(self):
        """Test JSON serialization."""
        metadata = CompressionMetadata(
            strategy="truncation",
            params={"key": "value"},
        )
        
        json_str = metadata.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["strategy"] == "truncation"
        assert parsed["params"]["key"] == "value"


class TestCompressionResult:
    """Test suite for CompressionResult."""
    
    def test_success_result(self):
        """Test successful compression result."""
        result = CompressionResult(
            success=True,
            compressed_content="compressed",
            original_length=1000,
            compressed_length=200,
        )
        
        assert result.success
        assert result.compression_ratio == 5.0
        assert result.space_saved == 800
    
    def test_failed_result(self):
        """Test failed compression result."""
        result = CompressionResult(
            success=False,
            error="Compression failed",
        )
        
        assert not result.success
        assert result.error == "Compression failed"
        assert result.compression_ratio == 1.0
    
    def test_zero_compressed_length(self):
        """Test zero compressed length handling."""
        result = CompressionResult(
            success=True,
            compressed_content="",
            original_length=100,
            compressed_length=0,
        )
        
        assert result.compression_ratio == 1.0


class TestMemoryItem:
    """Test suite for MemoryItem."""
    
    def test_creation(self):
        """Test basic creation."""
        item = MemoryItem(
            id="test_1",
            type="conversation",
            content="Test content",
            session_id="session_1",
        )
        
        assert item.id == "test_1"
        assert item.type == "conversation"
        assert item.compressed is False
        assert item.deleted is False
        assert item.version == 1
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        item = MemoryItem(
            id="test_2",
            type="tool_result",
            content="Tool result",
            session_id="session_2",
        )
        
        d = item.to_dict()
        
        assert d["id"] == "test_2"
        assert d["type"] == "tool_result"
        assert "compressed" in d
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "id": "test_3",
            "type": "conversation",
            "content": "Content",
            "session_id": "session_3",
            "compressed": True,
            "compression_type": "truncation",
            "version": 2,
        }
        
        item = MemoryItem.from_dict(data)
        
        assert item.id == "test_3"
        assert item.compressed is True
        assert item.version == 2


class TestCacheItem:
    """Test suite for CacheItem."""
    
    def test_creation(self):
        """Test basic creation."""
        item = CacheItem(
            id="cache_1",
            cache_key="key_hash",
            content="Cached result",
            tool_name="search",
        )
        
        assert item.id == "cache_1"
        assert item.tool_name == "search"
        assert item.compressed is False


class TestCompressionStats:
    """Test suite for CompressionStats."""
    
    def test_creation(self):
        """Test basic creation."""
        stats = CompressionStats()
        
        assert stats.items_compressed == 0
        assert stats.items_failed == 0
        assert stats.avg_compression_ratio == 1.0
    
    def test_update_compression(self):
        """Test updating compression statistics."""
        stats = CompressionStats()
        
        stats.update_compression(2.5, 0.9)
        stats.update_compression(3.0, 0.95)
        
        assert stats.count == 2
        assert stats.avg_compression_ratio == pytest.approx(2.75)
        assert stats.avg_semantic_similarity == pytest.approx(0.925)
    
    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        stats = CompressionStats()
        
        stats.decompression_cache_hits = 80
        stats.decompression_cache_misses = 20
        
        assert stats.decompression_cache_hit_rate == pytest.approx(0.8)
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CompressionStats()
        stats.update_compression(2.0, 0.9)
        
        d = stats.to_dict()
        
        assert "items_compressed" in d
        assert "compression_ratio_avg" in d
        assert "decompression_cache_hit_rate" in d
