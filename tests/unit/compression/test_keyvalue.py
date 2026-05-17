"""Unit tests for key-value compaction compression strategy."""

import pytest
import json
from src.core.memory.compression.strategies.keyvalue import KeyValueCompactor
from src.core.memory.compression.config import KeyValueConfig
from src.core.memory.compression.types import CompressionMetadata


class TestKeyValueCompactor:
    """Test suite for KeyValueCompactor."""
    
    @pytest.fixture
    def compactor(self) -> KeyValueCompactor:
        """Create a key-value compactor."""
        config = KeyValueConfig(keep_fields_ratio=0.5)
        return KeyValueCompactor(config)
    
    @pytest.fixture
    def strict_compactor(self) -> KeyValueCompactor:
        """Create a stricter compactor (keep fewer fields)."""
        config = KeyValueConfig(keep_fields_ratio=0.3)
        return KeyValueCompactor(config)
    
    @pytest.mark.asyncio
    async def test_name(self, compactor: KeyValueCompactor):
        """Test strategy name."""
        assert compactor.name == "kv_compact"
    
    @pytest.mark.asyncio
    async def test_json_object_compression(self, compactor: KeyValueCompactor):
        """Test compression of JSON object."""
        data = {
            "short": "a",
            "medium_description": "This is a medium length string",
            "long_content": "This is a much longer string that should be scored higher based on length",
            "number": 12345,
            "nested": {"key": "value"},
            "list": [1, 2, 3, 4, 5],
        }
        
        content = json.dumps(data)
        compressed, metadata = await compactor.compress(content)
        
        assert metadata.strategy == "kv_compact"
        assert metadata.kept_fields is not None
        assert len(metadata.kept_fields) <= len(data)
        
        parsed = json.loads(compressed)
        assert isinstance(parsed, dict)
    
    @pytest.mark.asyncio
    async def test_field_scoring(self, compactor: KeyValueCompactor):
        """Test that fields are scored correctly."""
        scores = compactor._calculate_field_scores({
            "short": "a",
            "long": "This is a much longer string that should score higher",
            "large_number": 1000000,
            "nested": {"key": "value"},
            "list": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        })
        
        assert scores["long"] > scores["short"]
        assert scores["large_number"] > scores["short"]
        assert scores["nested"] > scores["short"]
        assert scores["list"] > scores["short"]
    
    @pytest.mark.asyncio
    async def test_non_json_returns_unchanged(self, compactor: KeyValueCompactor):
        """Test that non-JSON content is returned unchanged."""
        content = "This is plain text, not JSON"
        compressed, metadata = await compactor.compress(content)
        
        assert compressed == content
        assert metadata.error == "content_is_not_json_object"
    
    @pytest.mark.asyncio
    async def test_json_array_returns_unchanged(self, compactor: KeyValueCompactor):
        """Test that JSON arrays are returned unchanged."""
        content = json.dumps([1, 2, 3, 4, 5])
        compressed, metadata = await compactor.compress(content)
        
        assert compressed == content
    
    @pytest.mark.asyncio
    async def test_empty_object_returns_unchanged(self, compactor: KeyValueCompactor):
        """Test that empty objects are returned unchanged."""
        content = "{}"
        compressed, metadata = await compactor.compress(content)
        
        assert compressed == content
    
    @pytest.mark.asyncio
    async def test_metadata_params(self, compactor: KeyValueCompactor):
        """Test metadata contains correct parameters."""
        data = {"a": 1, "b": 2, "c": 3, "d": 4}
        _, metadata = await compactor.compress(json.dumps(data))
        
        assert metadata.params["keep_fields_ratio"] == 0.5
        assert metadata.params["original_keys"] == 4
        assert metadata.kept_fields is not None
    
    @pytest.mark.asyncio
    async def test_strict_compactor_keeps_less(self, strict_compactor: KeyValueCompactor):
        """Test that stricter compactor keeps fewer fields."""
        data = {f"key_{i}": f"value_{i}" for i in range(10)}
        content = json.dumps(data)
        
        _, metadata_normal = await strict_compactor.compress(content)
        
        assert len(metadata_normal.kept_fields) <= 3
    
    @pytest.mark.asyncio
    async def test_decompression_returns_content(self, compactor: KeyValueCompactor):
        """Test decompression returns the compressed content."""
        data = {"a": 1, "b": "longer string for testing"}
        content = json.dumps(data)
        
        compressed, metadata = await compactor.compress(content)
        decompressed = await compactor.decompress(compressed, metadata)
        
        assert decompressed == compressed
    
    @pytest.mark.asyncio
    async def test_hash_preserved(self, compactor: KeyValueCompactor):
        """Test that original hash is preserved."""
        data = {"test": "data"}
        _, metadata = await compactor.compress(json.dumps(data))
        
        assert metadata.original_hash is not None
        assert len(metadata.original_hash) == 64
    
    @pytest.mark.asyncio
    async def test_nested_object_scoring(self, compactor: KeyValueCompactor):
        """Test scoring of nested objects."""
        scores = compactor._calculate_field_scores({
            "flat": "value",
            "deep": {"nested": {"structure": "with many keys"}},
            "flat2": "value2",
        })
        
        assert scores["deep"] > scores["flat"]
        assert scores["deep"] > scores["flat2"]
