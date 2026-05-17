"""Unit tests for adaptive pruning strategy."""

import pytest
import time
from src.core.memory.compression.strategies.adaptive import AdaptivePruner
from src.core.memory.compression.config import AdaptivePruneConfig
from src.core.memory.compression.types import MemoryItem


class TestAdaptivePruner:
    """Test suite for AdaptivePruner."""
    
    @pytest.fixture
    def pruner(self) -> AdaptivePruner:
        """Create an adaptive pruner."""
        config = AdaptivePruneConfig(
            prune_after_days=30,
            min_access_count=2,
            soft_delete=True
        )
        return AdaptivePruner(config)
    
    @pytest.fixture
    def short_pruner(self) -> AdaptivePruner:
        """Create a pruner with shorter thresholds."""
        config = AdaptivePruneConfig(
            prune_after_days=1,
            min_access_count=1,
            soft_delete=True
        )
        return AdaptivePruner(config)
    
    @pytest.mark.asyncio
    async def test_name(self, pruner: AdaptivePruner):
        """Test strategy name."""
        assert pruner.name == "adaptive_prune"
    
    def test_should_not_prune_young_item(self, pruner: AdaptivePruner):
        """Test that young items are not pruned."""
        item = MemoryItem(
            id="test_1",
            type="conversation",
            content="Recent content",
            session_id="session_1",
            last_updated=int(time.time()),
            access_count=5,
        )
        
        assert not pruner.should_prune(item)
    
    def test_should_not_prune_frequently_accessed(self, pruner: AdaptivePruner):
        """Test that frequently accessed items are not pruned."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_2",
            type="conversation",
            content="Popular content",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=10,
        )
        
        assert not pruner.should_prune(item)
    
    def test_should_prune_old_unaccessed(self, pruner: AdaptivePruner):
        """Test that old, unaccessed items are pruned."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_3",
            type="conversation",
            content="Old content",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=1,
        )
        
        assert pruner.should_prune(item)
    
    def test_should_not_prune_deleted(self, pruner: AdaptivePruner):
        """Test that already deleted items are not pruned."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_4",
            type="conversation",
            content="Deleted content",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=1,
            deleted=True,
        )
        
        assert not pruner.should_prune(item)
    
    def test_should_not_prune_no_compress(self, pruner: AdaptivePruner):
        """Test that no_compress items are not pruned."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_5",
            type="conversation",
            content="Protected content",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=1,
            no_compress=True,
        )
        
        assert not pruner.should_prune(item)
    
    def test_get_prune_metadata(self, pruner: AdaptivePruner):
        """Test prune metadata generation."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_6",
            type="conversation",
            content="Content to prune",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=1,
        )
        
        metadata = pruner.get_prune_metadata(item)
        
        assert metadata is not None
        assert metadata["deleted"] is True
        assert metadata["deleted_at"] is not None
        assert metadata["cold_storage_ref"] == "cold://test_6"
    
    def test_get_prune_metadata_returns_none_for_non_pruneable(
        self, pruner: AdaptivePruner
    ):
        """Test that non-pruneable items return None."""
        item = MemoryItem(
            id="test_7",
            type="conversation",
            content="Not pruneable",
            session_id="session_1",
            last_updated=int(time.time()),
            access_count=5,
        )
        
        metadata = pruner.get_prune_metadata(item)
        
        assert metadata is None
    
    def test_short_pruner_prunes_quicker(self, short_pruner: AdaptivePruner):
        """Test that shorter thresholds prune faster."""
        recent_time = time.time() - (2 * 86400)
        item = MemoryItem(
            id="test_8",
            type="conversation",
            content="Recent content",
            session_id="session_1",
            last_updated=int(recent_time),
            access_count=0,
        )
        
        assert short_pruner.should_prune(item)
    
    @pytest.mark.asyncio
    async def test_compress_returns_original(self, pruner: AdaptivePruner):
        """Test that compress returns original content."""
        content = "Original content"
        compressed, metadata = await pruner.compress(content)
        
        assert compressed == content
        assert metadata.strategy == "adaptive_prune"
    
    @pytest.mark.asyncio
    async def test_decompress_returns_content(self, pruner: AdaptivePruner):
        """Test that decompress returns original content."""
        content = "Original content"
        from src.core.memory.compression.types import CompressionMetadata
        
        metadata = CompressionMetadata(strategy="adaptive_prune")
        decompressed = await pruner.decompress(content, metadata)
        
        assert decompressed == content


class TestAdaptivePrunerEdgeCases:
    """Edge case tests for AdaptivePruner."""
    
    @pytest.fixture
    def pruner(self) -> AdaptivePruner:
        config = AdaptivePruneConfig(prune_after_days=30, min_access_count=2)
        return AdaptivePruner(config)
    
    def test_zero_access_count(self, pruner: AdaptivePruner):
        """Test item with zero access count."""
        old_time = time.time() - (60 * 86400)
        item = MemoryItem(
            id="test_zero",
            type="conversation",
            content="Zero access content",
            session_id="session_1",
            last_updated=int(old_time),
            access_count=0,
        )
        
        assert pruner.should_prune(item)
    
    def test_boundary_age(self, pruner: AdaptivePruner):
        """Test item at exact boundary age."""
        boundary_time = time.time() - (30 * 86400) - 100
        item = MemoryItem(
            id="test_boundary",
            type="conversation",
            content="Boundary content",
            session_id="session_1",
            last_updated=int(boundary_time),
            access_count=1,
        )
        
        assert pruner.should_prune(item)
