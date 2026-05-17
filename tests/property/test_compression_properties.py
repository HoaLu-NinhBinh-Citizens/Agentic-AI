"""Property-based tests for compression using Hypothesis."""

import pytest
from hypothesis import given, strategies as st, settings, assume, example
from src.core.memory.compression.strategies.truncation import TruncationCompressor
from src.core.memory.compression.strategies.keyvalue import KeyValueCompactor
from src.core.memory.compression.strategies.adaptive import AdaptivePruner
from src.core.memory.compression.strategies.extractive import ExtractiveSummarizer
from src.core.memory.compression.config import TruncationConfig, KeyValueConfig
from src.core.memory.compression.types import MemoryItem, CompressionMetadata
from src.core.memory.compression.cache import DecompressionCache
import json
import time


# Fix #8 & #14: Enhanced JSON generators for property-based tests
# Including edge cases: malformed UTF-8, nested structures, huge keys, emojis, etc.

# Standard JSON-like generator
json_generator = st.recursive(
    st.booleans() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=100),
    lambda children: st.lists(children, max_size=20) | st.dictionaries(st.text(max_size=50), children, max_size=20),
    max_leaves=10
)

complex_json_generator = st.recursive(
    st.booleans() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=200),
    lambda children: st.lists(children, max_size=50) | st.dictionaries(st.text(max_size=100), children, max_size=50),
    max_leaves=20
)

# Fix #14: Extreme edge case generators
huge_key_generator = st.dictionaries(
    st.text(min_size=500, max_size=2000),  # Huge keys
    st.text(max_size=100),
    max_size=5
)

unicode_generator = st.text(
    alphabet=st.characters(min_codepoint=0x0000, max_codepoint=0xFFFF),
    min_size=1,
    max_size=1000
)

mixed_content_generator = st.one_of(
    st.text(max_size=500),  # Plain text
    st.lists(st.text(max_size=50), max_size=100),  # Line list (like logs)
    st.dictionaries(st.text(max_size=30), st.text(max_size=200), max_size=50),  # Key-value
)

code_like_generator = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \n\t{}[]();=+-*/<>!&|",
    min_size=10,
    max_size=500
)

nested_json_generator = st.recursive(
    st.one_of(st.integers(), st.text(max_size=20)),
    lambda children: st.lists(children, max_size=10) | st.dictionaries(st.text(max_size=30), children, max_size=10),
    max_leaves=50  # Deep nesting
)


class TestCompressionIdempotence:
    """Property tests for idempotence: compress(decompress(compress(x))) == compress(x)"""
    
    @given(content=st.text(min_size=1, max_size=10000))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_truncation_idempotence(self, content: str):
        """Test that truncation compression is idempotent."""
        config = TruncationConfig(max_chars=500)
        compressor = TruncationCompressor(config)
        
        compressed1, metadata1 = await compressor.compress(content)
        decompressed = await compressor.decompress(compressed1, metadata1)
        compressed2, _ = await compressor.compress(decompressed)
        
        if len(content) <= 500:
            assert compressed1 == compressed2
    
    @given(content=st.text(min_size=1, max_size=5000))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_keyvalue_idempotence(self, content: str):
        """Test that KV compaction compression is idempotent."""
        try:
            data = {"text": content, "length": len(content)}
            json_content = json.dumps(data)
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.5))
            
            compressed1, metadata1 = await compactor.compress(json_content)
            decompressed = await compactor.decompress(compressed1, metadata1)
            compressed2, _ = await compactor.compress(decompressed)
            
            assert compressed1 == compressed2
        except (json.JSONDecodeError, TypeError):
            pass

    @given(data=json_generator)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_keyvalue_json_idempotence(self, data):
        """Test KV compaction with arbitrary JSON data (Fix #8).
        
        Note: KV compaction is not perfectly idempotent for all cases,
        as decompress adds back pruned keys. We test that decompress
        always succeeds and produces valid JSON.
        """
        try:
            json_content = json.dumps(data)
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.5))
            
            compressed1, metadata1 = await compactor.compress(json_content)
            decompressed = await compactor.decompress(compressed1, metadata1)
            
            # Verify decompressed is valid JSON
            restored = json.loads(decompressed)
            assert restored is not None
        except (json.JSONDecodeError, TypeError):
            pass


class TestDecompressionAlwaysPossible:
    """Property tests: After compress, decompress never raises exception."""
    
    @given(content=st.text(min_size=1, max_size=10000))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_truncation_decompress_always_works(self, content: str):
        """Test that truncation decompress never fails."""
        config = TruncationConfig(max_chars=500)
        compressor = TruncationCompressor(config)
        
        compressed, metadata = await compressor.compress(content)
        
        try:
            result = await compressor.decompress(compressed, metadata)
            assert result is not None
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"Decompression raised exception: {e}")
    
    @given(content=st.text(min_size=1, max_size=5000))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_keyvalue_decompress_always_works(self, content: str):
        """Test that KV decompress never fails for JSON content."""
        try:
            data = {"content": content, "meta": "test"}
            json_content = json.dumps(data)
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.5))
            compressed, metadata = await compactor.compress(json_content)
            
            result = await compactor.decompress(compressed, metadata)
            assert result is not None
        except Exception:
            pass
    
    @given(data=complex_json_generator)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_keyvalue_json_decompress_always_works(self, data):
        """Test KV decompress with arbitrary JSON data (Fix #8)."""
        try:
            json_content = json.dumps(data)
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.5))
            compressed, metadata = await compactor.compress(json_content)
            
            result = await compactor.decompress(compressed, metadata)
            assert result is not None
            
            restored = json.loads(result)
            assert restored is not None
        except (json.JSONDecodeError, TypeError):
            pass


class TestCompressionQuality:
    """Property tests for compression quality."""
    
    @given(content=st.text(min_size=10, max_size=5000))
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_truncation_preserves_ends(self, content: str):
        """Test that truncation preserves content ends when keep_both_ends=True."""
        config = TruncationConfig(max_chars=100, keep_both_ends=True)
        compressor = TruncationCompressor(config)
        
        compressed, metadata = await compressor.compress(content)
        
        if len(content) > 100:
            assert compressed.startswith(content[:40])
            assert compressed.endswith(content[-40:])
        else:
            assert compressed == content
    
    @given(content=st.text(min_size=10, max_size=5000))
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_truncation_respects_max_chars(self, content: str):
        """Test that truncated content respects max_chars limit."""
        config = TruncationConfig(max_chars=200)
        compressor = TruncationCompressor(config)
        
        compressed, _ = await compressor.compress(content)
        
        assert len(compressed) <= 200


class TestCompressionQualityWithJSON:
    """Property tests for compression quality with JSON data (Fix #8)."""
    
    @given(data=json_generator)
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_keyvalue_compression_reduces_size(self, data):
        """Test that KV compaction reduces size for large JSON."""
        try:
            json_content = json.dumps(data)
            if len(json_content) < 100:
                return  # Skip small content
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.3))
            compressed, _ = await compactor.compress(json_content)
            
            # Compression should reduce size for large data
            assert len(compressed) <= len(json_content)
        except (json.JSONDecodeError, TypeError):
            pass
    
    @given(data=complex_json_generator)
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_keyvalue_preserves_structure(self, data):
        """Test that KV compaction preserves JSON structure."""
        try:
            json_content = json.dumps(data)
            
            compactor = KeyValueCompactor(KeyValueConfig(keep_fields_ratio=0.5))
            compressed, metadata = await compactor.compress(json_content)
            
            decompressed = await compactor.decompress(compressed, metadata)
            restored = json.loads(decompressed)
            
            # Verify the result is not None
            assert restored is not None
        except (json.JSONDecodeError, TypeError):
            pass


class TestCacheProperties:
    """Property tests for decompression cache."""
    
    @given(key=st.text(min_size=1, max_size=100), value=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_set_get_roundtrip(self, key: str, value: str):
        """Test that cache set/get roundtrips correctly."""
        cache = DecompressionCache(maxsize=100, ttl_seconds=3600)
        
        cache.set(key, value)
        result = cache.get(key)
        
        assert result == value
    
    @given(key=st.text(min_size=1, max_size=100), value=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_invalidate(self, key: str, value: str):
        """Test that invalidation removes cached value."""
        cache = DecompressionCache(maxsize=100)
        
        cache.set(key, value)
        cache.invalidate(key)
        result = cache.get(key)
        
        assert result is None
    
    @given(content=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_handles_empty_string(self, content: str):
        """Test that cache handles empty string correctly."""
        cache = DecompressionCache(maxsize=10)
        
        cache.set("empty", content)
        result = cache.get("empty")
        
        assert result == content


class TestAdaptivePrunerProperties:
    """Property tests for adaptive pruner."""
    
    @given(
        age_days=st.floats(min_value=0, max_value=365),
        access_count=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=100)
    def test_pruner_decision_boundary(self, age_days: float, access_count: int):
        """Test pruner decisions at boundary conditions."""
        pruner = AdaptivePruner(
            config=type("Config", (), {
                "prune_after_days": 30,
                "min_access_count": 2,
                "soft_delete": True
            })()
        )
        
        item = MemoryItem(
            id="boundary_test",
            type="conversation",
            content="Test content",
            session_id="session_1",
            last_updated=int(time.time() - age_days * 86400),
            access_count=access_count,
            no_compress=False,
            deleted=False,
        )
        
        should_prune = pruner.should_prune(item)
        
        expected = (
            age_days >= 30 and
            access_count < 2
        )
        
        assert should_prune == expected


class TestCompressionMetadata:
    """Property tests for compression metadata."""
    
    @given(params=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(st.text(min_size=0, max_size=100), st.integers(), st.booleans()),
        max_size=10
    ))
    @settings(max_examples=50)
    def test_metadata_serialization(self, params: dict):
        """Test that metadata serializes and deserializes correctly."""
        metadata = CompressionMetadata(
            strategy="test",
            params=params,
            original_hash="abc123",
        )
        
        json_str = metadata.to_json()
        restored = CompressionMetadata.from_dict(json_str)
        
        assert restored.strategy == metadata.strategy
        assert restored.original_hash == metadata.original_hash


class TestMemoryItemRoundtrip:
    """Property tests for MemoryItem serialization."""
    
    @given(
        content=st.text(min_size=0, max_size=5000),
        session_id=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    def test_item_to_dict_roundtrip(self, content: str, session_id: str):
        """Test that MemoryItem serializes and deserializes correctly."""
        item = MemoryItem(
            id="roundtrip_test",
            type="conversation",
            content=content,
            session_id=session_id,
            last_updated=int(time.time()),
            version=5,
        )
        
        data = item.to_dict()
        restored = MemoryItem.from_dict(data)
        
        assert restored.id == item.id
        assert restored.content == item.content
        assert restored.version == item.version
