"""Soft delete pruner and permanent purge job."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .engine import CompressionEngine

logger = logging.getLogger(__name__)


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""
    
    async def execute(self, query: str, params: tuple) -> int: ...
    async def query(self, query: str, params: tuple) -> dict | None: ...


class SoftDeletePruner:
    """Soft delete pruner for old compressed items.
    
    Marks items for deletion instead of permanent removal.
    Optionally moves content to cold storage.
    """
    
    def __init__(self, engine: "CompressionEngine"):
        self._engine = engine
        self._config = engine._config
        self._pruned_count = 0
    
    async def prune(self) -> int:
        """Prune items based on age and access patterns.
        
        Returns:
            Number of items soft deleted.
        """
        if not self._config.cold_storage.enabled:
            return await self._prune_without_cold_storage()
        return await self._prune_with_cold_storage()
    
    async def _prune_without_cold_storage(self) -> int:
        """Prune without moving to cold storage."""
        prune_after = time.time() - (self._config.strategies.adaptive_prune.prune_after_days * 86400)
        
        items = await self._fetch_prune_candidates(prune_after)
        
        count = 0
        for item in items:
            success = await self._soft_delete(item)
            if success:
                count += 1
        
        self._pruned_count += count
        return count
    
    async def _prune_with_cold_storage(self) -> int:
        """Prune and move to cold storage."""
        prune_after = time.time() - (self._config.strategies.adaptive_prune.prune_after_days * 86400)
        
        items = await self._fetch_prune_candidates(prune_after)
        
        count = 0
        for item in items:
            try:
                await self._move_to_cold_storage(item)
                success = await self._soft_delete(item)
                if success:
                    count += 1
            except Exception as e:
                logger.error(f"Failed to move {item['id']} to cold storage: {e}")
        
        self._pruned_count += count
        return count
    
    async def _fetch_prune_candidates(self, prune_after: float) -> list[dict]:
        """Fetch items eligible for pruning."""
        min_access = self._config.strategies.adaptive_prune.min_access_count
        
        items = await self._engine._db.query_many(
            """
            SELECT * FROM memory
            WHERE compressed = true
              AND deleted = false
              AND no_compress = false
              AND last_accessed < ?
              AND access_count < ?
            LIMIT 100
            """,
            (prune_after, min_access),
        )
        
        return items
    
    async def _soft_delete(self, item: dict) -> bool:
        """Mark item as soft deleted.
        
        Args:
            item: Item dictionary.
            
        Returns:
            True if successful.
        """
        item_id = item["id"]
        deleted_at = int(time.time())
        
        result = await self._engine._db.execute(
            """
            UPDATE memory
            SET deleted = true,
                deleted_at = ?,
                version = version + 1
            WHERE id = ? AND version = ?
            """,
            (deleted_at, item_id, item["version"]),
        )
        
        if result > 0:
            logger.info(f"Soft deleted item: {item_id}")
            return True
        
        logger.warning(f"Failed to soft delete {item_id}: version mismatch")
        return False
    
    async def _move_to_cold_storage(self, item: dict) -> None:
        """Move item content to cold storage (original_blobs).
        
        Args:
            item: Item dictionary.
        """
        item_id = item["id"]
        content = item.get("content", "")
        content_hash = item.get("original_content_hash", "")
        
        if not content_hash and content:
            import hashlib
            content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        await self._engine._db.execute(
            """
            INSERT OR REPLACE INTO original_blobs
            (item_id, content, content_hash, item_type, compressed_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                content,
                content_hash,
                "memory",
                item.get("last_compressed_at"),
                int(time.time()),
            ),
        )
        
        await self._engine._db.execute(
            """
            UPDATE memory
            SET cold_storage_ref = ?
            WHERE id = ?
            """,
            (f"cold://{item_id}", item_id),
        )
        
        logger.debug(f"Moved {item_id} to cold storage")
    
    @property
    def pruned_count(self) -> int:
        """Get total items pruned."""
        return self._pruned_count


class PermanentPurgeJob:
    """Permanently delete soft-deleted items after retention period."""
    
    def __init__(self, engine: "CompressionEngine"):
        self._engine = engine
        self._config = engine._config
        self._purged_count = 0
    
    async def purge(self) -> int:
        """Permanently delete items past retention period.
        
        Returns:
            Number of items purged.
        """
        retention_days = self._config.strategies.adaptive_prune.permanent_delete_days
        purge_after = time.time() - (retention_days * 86400)
        
        memory_deleted = await self._engine._db.execute(
            """
            DELETE FROM memory
            WHERE deleted = true AND deleted_at < ?
            """,
            (purge_after,),
        )
        
        blobs_deleted = await self._engine._db.execute(
            """
            DELETE FROM original_blobs
            WHERE deleted_at < ?
            """,
            (purge_after,),
        )
        
        total = memory_deleted + blobs_deleted
        self._purged_count += total
        
        if total > 0:
            logger.info(f"Permanently purged {total} items")
        
        return total
    
    async def purge_old_blobs(self) -> int:
        """Purge old blobs beyond retention policy (Fix #1).
        
        Only keeps latest blob per item, removes old ones after retention.
        
        Returns:
            Number of blobs purged.
        """
        if not self._config.cold_storage.blob_retention_days:
            return 0
        
        retention_cutoff = time.time() - (self._config.cold_storage.blob_retention_days * 86400)
        
        deleted = await self._engine._db.execute(
            """
            DELETE FROM original_blobs
            WHERE created_at < ?
            AND id NOT IN (
                SELECT id FROM original_blobs o1
                WHERE created_at = (
                    SELECT MAX(created_at) FROM original_blobs o2
                    WHERE o2.item_id = o1.item_id
                )
            )
            """,
            (int(retention_cutoff),),
        )
        
        if deleted > 0:
            logger.info(f"Purged {deleted} old blobs beyond retention policy")
        
        return deleted
    
    @property
    def purged_count(self) -> int:
        """Get total items purged."""
        return self._purged_count
