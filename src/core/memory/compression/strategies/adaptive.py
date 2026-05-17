"""Adaptive pruning strategy for soft delete.

Marks items for deletion based on age and access patterns.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .base import CompressionStrategy
from ..types import CompressionMetadata, MemoryItem, CacheItem

if TYPE_CHECKING:
    from ..config import AdaptivePruneConfig


class AdaptivePruner(CompressionStrategy):
    """Soft delete strategy based on age and access patterns.
    
    This strategy doesn't actually compress content.
    Instead, it marks items for soft deletion.
    
    Prune criteria:
    - Item is old enough (age >= prune_after_days)
    - Item hasn't been accessed enough (access_count < min_access_count)
    """
    
    def __init__(self, config: "AdaptivePruneConfig | None" = None):
        if config is None:
            from ..config import AdaptivePruneConfig
            config = AdaptivePruneConfig()
        
        self._prune_after_days = config.prune_after_days
        self._min_access_count = config.min_access_count
        self._soft_delete = config.soft_delete
    
    @property
    def name(self) -> str:
        return "adaptive_prune"
    
    def should_prune(self, item: MemoryItem | CacheItem) -> bool:
        """Check if an item should be soft deleted.
        
        Args:
            item: The item to check.
            
        Returns:
            True if item should be pruned.
        """
        if item.no_compress or item.deleted:
            return False
        
        age_seconds = time.time() - item.last_updated
        age_days = age_seconds / 86400
        
        if age_days < self._prune_after_days:
            return False
        
        if item.access_count >= self._min_access_count:
            return False
        
        return True
    
    def get_prune_metadata(
        self, item: MemoryItem | CacheItem
    ) -> dict | None:
        """Get metadata for soft deletion.
        
        Args:
            item: The item to prune.
            
        Returns:
            Dictionary with soft delete metadata, or None if not pruneable.
        """
        if not self.should_prune(item):
            return None
        
        return {
            "deleted": True,
            "deleted_at": int(time.time()),
            "cold_storage_ref": f"cold://{item.id}",
            "prune_reason": f"age>={self._prune_after_days}d_access<{self._min_access_count}",
        }
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        """This strategy doesn't compress content.
        
        Returns original content. Soft deletion is handled separately.
        """
        return content, CompressionMetadata(
            strategy=self.name,
            params={
                "prune_after_days": self._prune_after_days,
                "min_access_count": self._min_access_count,
            },
        )
    
    async def decompress(
        self, content: str, metadata: CompressionMetadata
    ) -> str:
        """Decompression for prune strategy is just returning content."""
        return content
