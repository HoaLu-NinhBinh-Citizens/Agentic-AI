"""Decompression module with LRU cache and fallback support.

Phase 4E: Issue #17 - Integrity scanner integration.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Optional

from .cache import DecompressionCache
from .strategies.base import DecompressionError, StrategyNotFoundError
from .types import CompressionMetadata, OriginalBlob

if TYPE_CHECKING:
    from .engine import CompressionEngine

logger = logging.getLogger(__name__)


class Decompressor:
    """Decompression handler with cache and fallback.
    
    Handles decompression of compressed content with:
    - LRU cache for frequently accessed items
    - Fallback to original_blobs table
    - Metadata-based reconstruction
    - Checksum validation after decompression
    """
    
    def __init__(
        self,
        engine: "CompressionEngine",
        cache: DecompressionCache | None = None,
    ):
        self._engine = engine
        self._cache = cache or DecompressionCache()
        self._strategies: dict[str, object] = {}
    
    def register_strategy(self, name: str, strategy: object) -> None:
        """Register a decompression strategy.
        
        Args:
            name: Strategy name.
            strategy: Strategy instance with decompress method.
        """
        self._strategies[name] = strategy
    
    async def decompress(
        self,
        item_id: str,
        item_type: str,
        content: str,
        metadata: CompressionMetadata,
    ) -> str:
        """Decompress content using appropriate strategy.
        
        Args:
            item_id: Item ID for cache key.
            item_type: Item type (memory or cache).
            content: Compressed content.
            metadata: Compression metadata.
            
        Returns:
            Decompressed content.
            
        Raises:
            DecompressionError: If decompression fails.
        """
        cache_key = f"{item_type}:{item_id}"
        
        cached = self._cache.get(cache_key)
        if cached is not None:
            # Verify cached content against hash if available
            if metadata.original_hash:
                result_hash = hashlib.sha256(cached.encode()).hexdigest()
                if result_hash == metadata.original_hash:
                    return cached
                else:
                    logger.warning(f"Cache hash mismatch for {item_id}, invalidating")
                    self._cache.invalidate(cache_key)
        
        try:
            if metadata.strategy == "truncation":
                strategy = self._strategies.get("truncation")
                if strategy:
                    result = await strategy.decompress(content, metadata)
                else:
                    result = content
            
            elif metadata.strategy == "extractive":
                strategy = self._strategies.get("extractive")
                if strategy:
                    result = await strategy.decompress(content, metadata)
                else:
                    result = content
            
            elif metadata.strategy == "kv_compact":
                strategy = self._strategies.get("kv_compact")
                if strategy:
                    result = await strategy.decompress(content, metadata)
                else:
                    result = content
            
            elif metadata.strategy == "adaptive_prune":
                result = content
            
            else:
                logger.warning(f"Unknown compression strategy: {metadata.strategy}")
                result = content
            
            # Fix #3: Only verify checksum for lossless strategies
            # Lossy strategies (truncation, extractive, kv_compact) cannot match original hash
            if metadata.original_hash and metadata.is_lossless:
                result_hash = hashlib.sha256(result.encode()).hexdigest()
                if result_hash != metadata.original_hash:
                    logger.error(f"Checksum mismatch for {item_id}: expected {metadata.original_hash}, got {result_hash}")
                    raise DecompressionError(
                        f"Checksum mismatch after decompression for {item_id}",
                        metadata.strategy
                    )
            
            self._cache.set(cache_key, result)
            return result
            
        except DecompressionError:
            raise
        except Exception as e:
            logger.error(f"Decompression failed for {item_id}: {e}")
            raise DecompressionError(str(e), metadata.strategy)
    
    async def decompress_with_fallback(
        self,
        item_id: str,
        item_type: str,
        content: str,
        metadata: CompressionMetadata,
    ) -> str | None:
        """Decompress with automatic fallback on failure.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
            content: Compressed content.
            metadata: Compression metadata.
            
        Returns:
            Decompressed content, or None if all methods fail.
        """
        try:
            return await self.decompress(item_id, item_type, content, metadata)
        except DecompressionError:
            pass
        
        try:
            original_blob = await self._get_original_blob(item_id)
            if original_blob:
                self._cache.set(f"{item_type}:{item_id}", original_blob.content)
                return original_blob.content
        except Exception as e:
            logger.error(f"Fallback decompression failed for {item_id}: {e}")
        
        return None
    
    async def _get_original_blob(self, item_id: str) -> OriginalBlob | None:
        """Get original blob from storage.
        
        Args:
            item_id: Item ID.
            
        Returns:
            OriginalBlob if found, None otherwise.
        """
        if not hasattr(self._engine, "_db"):
            return None
        
        try:
            row = await self._engine._db.query(
                "SELECT * FROM original_blobs WHERE item_id = ?",
                (item_id,),
            )
            if row:
                return OriginalBlob(**row)
        except Exception as e:
            logger.debug(f"Original blob lookup failed: {e}")
        
        return None
    
    def invalidate_cache(self, item_id: str, item_type: str) -> None:
        """Invalidate cache entry.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
        """
        cache_key = f"{item_type}:{item_id}"
        self._cache.invalidate(cache_key)
    
    def clear_cache(self) -> None:
        """Clear the decompression cache."""
        self._cache.clear()
    
    @property
    def cache_stats(self) -> dict:
        """Get cache statistics."""
        return self._cache.get_stats()
