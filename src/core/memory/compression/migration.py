"""Strategy migration framework - Phase 4E: Issue #20.

Allows migrating compressed items when compression strategy changes:
- extractive v1 → v2
- Strategy parameter changes
- Recompression with new strategy
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .types import CompressionMetadata

if TYPE_CHECKING:
    from .engine import CompressionEngine
    from .strategies.base import CompressionStrategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyVersion:
    """Version identifier for compression strategy."""
    name: str          # "extractive", "truncation", etc.
    version: str      # "1.0", "2.0", etc.
    
    def __str__(self) -> str:
        return f"{self.name}@{self.version}"
    
    def __hash__(self) -> int:
        return hash((self.name, self.version))
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, StrategyVersion):
            return False
        return self.name == other.name and self.version == other.version


@dataclass
class MigrationReport:
    """Report of a migration run."""
    target_version: StrategyVersion
    started_at: float
    finished_at: Optional[float] = None
    migrated: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (item_id, reason)
    
    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000 if self.finished_at else 0
    
    @property
    def success_rate(self) -> float:
        total = self.migrated + self.failed
        return self.migrated / total if total > 0 else 0


class StrategyMigration:
    """Framework for migrating compressed items when strategy changes.
    
    Phase 4E: Issue #20
    
    Handles:
    - Detecting items needing recompression
    - Recompressing with new strategy
    - Tracking migration history
    """
    
    def __init__(
        self,
        engine: "CompressionEngine",
        strategy_registry: dict[str, "CompressionStrategy"],
    ):
        self._engine = engine
        self._registry = strategy_registry
    
    def parse_strategy_version(
        self,
        metadata: CompressionMetadata | dict | None,
    ) -> Optional[StrategyVersion]:
        """Parse strategy version from metadata."""
        if not metadata:
            return None
        
        if isinstance(metadata, CompressionMetadata):
            name = metadata.strategy
            version = getattr(metadata, 'strategy_version', '1.0')
        elif isinstance(metadata, dict):
            name = metadata.get("strategy", "")
            version = metadata.get("strategy_version", "1.0")
        else:
            return None
        
        if not name:
            return None
        
        return StrategyVersion(name=name, version=version)
    
    def needs_recompression(
        self,
        item: dict,
        current_version: StrategyVersion,
    ) -> tuple[bool, str]:
        """Check if item needs recompression.
        
        Args:
            item: Item dictionary with compression metadata.
            current_version: Current strategy version.
            
        Returns:
            (needs_recompression, reason)
        """
        if not item.get("compressed"):
            return False, "not_compressed"
        
        if item.get("no_compress"):
            return False, "marked_no_compress"
        
        if not item.get("compression_type"):
            return False, "no_strategy"
        
        # Parse stored version
        metadata = item.get("compression_metadata")
        if isinstance(metadata, str):
            import json
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = None
        
        stored = self.parse_strategy_version(metadata)
        
        if not stored:
            return True, "missing_version"
        
        if stored.name != current_version.name:
            return True, f"strategy_changed:{stored}->{current_version}"
        
        if stored.version != current_version.version:
            return True, f"version_changed:{stored}->{current_version}"
        
        return False, "current"
    
    async def migrate_item(
        self,
        item_id: str,
        item_type: str,
        new_strategy: str,
        new_version: str,
    ) -> bool:
        """Recompress item with new strategy.
        
        Args:
            item_id: Item ID.
            item_type: Item type ('memory' or 'cache').
            new_strategy: New strategy name.
            new_version: New strategy version.
            
        Returns:
            True if migration successful.
        """
        # Get original content from blob
        original = await self._engine._fallback_decompress(item_id, item_type)
        if not original:
            logger.error(f"Cannot migrate {item_id}: no original found")
            return False
        
        # Get new strategy
        strategy_impl = self._registry.get(new_strategy)
        if not strategy_impl:
            logger.error(f"Unknown strategy: {new_strategy}")
            return False
        
        try:
            # Apply new strategy
            compressed, metadata = await strategy_impl.compress(original)
            
            # Update version info
            metadata.strategy_version = new_version
            
            # Atomic update with new strategy
            original_hash = hashlib.sha256(original.encode()).hexdigest()
            
            success = await self._engine._atomic.compress_atomic(
                item=None,  # We need to get fresh item
                item_id=item_id,
                item_type=item_type,
                compressed_content=compressed,
                metadata=metadata,
                original_hash=original_hash,
            )
            
            return success
        except Exception as e:
            logger.error(f"Migration failed for {item_id}: {e}")
            return False
    
    async def find_items_needing_migration(
        self,
        target_version: StrategyVersion,
        limit: int = 100,
    ) -> list[dict]:
        """Find compressed items that need recompression.
        
        Args:
            target_version: Target strategy version.
            limit: Maximum items to return.
            
        Returns:
            List of items needing migration.
        """
        if not self._engine._db:
            return []
        
        table = "memory" if target_version.name in ["truncation", "extractive", "kv_compact"] else "tool_cache"
        
        items = await self._engine._db.query_many(
            f"""
            SELECT * FROM {table}
            WHERE compressed = TRUE
              AND no_compress = FALSE
              AND deleted = FALSE
              AND (
                  compression_type != ?
                  OR json_extract(compression_metadata, '$.strategy_version') != ?
              )
            LIMIT ?
            """,
            (target_version.name, target_version.version, limit),
        )
        
        return items
    
    async def run_migration(
        self,
        target_version: StrategyVersion,
        batch_size: int = 50,
        dry_run: bool = False,
    ) -> MigrationReport:
        """Run migration for all items needing recompression.
        
        Args:
            target_version: Target strategy version.
            batch_size: Items per batch.
            dry_run: If True, only report without migrating.
            
        Returns:
            MigrationReport with results.
        """
        report = MigrationReport(
            target_version=target_version,
            started_at=time.time(),
        )
        
        logger.info(f"Starting migration to {target_version}")
        
        while True:
            items = await self.find_items_needing_migration(
                target_version,
                limit=batch_size,
            )
            
            if not items:
                break
            
            for item in items:
                needs, reason = self.needs_recompression(item, target_version)
                
                if not needs:
                    report.skipped += 1
                    continue
                
                if dry_run:
                    logger.info(
                        f"[DRY-RUN] Would migrate {item['id']}: {reason}"
                    )
                    report.migrated += 1
                    continue
                
                item_type = "memory" if "session_id" in item else "cache"
                success = await self.migrate_item(
                    item_id=item["id"],
                    item_type=item_type,
                    new_strategy=target_version.name,
                    new_version=target_version.version,
                )
                
                if success:
                    report.migrated += 1
                else:
                    report.failed += 1
                    report.failures.append((item["id"], reason))
        
        report.finished_at = time.time()
        
        # Update engine stats
        self._engine._stats.update_migration(
            migrated=report.migrated,
            failed=report.failed,
        )
        
        logger.info(
            f"Migration complete: {report.migrated} migrated, "
            f"{report.failed} failed, {report.skipped} skipped "
            f"({report.duration_ms:.0f}ms)"
        )
        
        return report
