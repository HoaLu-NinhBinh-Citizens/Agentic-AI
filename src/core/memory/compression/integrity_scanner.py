"""Integrity scanner for compressed items - Phase 4E: Issue #17.

Periodically verifies compressed items for:
- Successful decompression
- Checksum validation
- Similarity preservation
- Metadata consistency
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .types import CompressionMetadata

if TYPE_CHECKING:
    from .engine import CompressionEngine

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of scanning a single item."""
    item_id: str
    item_type: str
    is_valid: bool = False
    issues: list[str] = field(default_factory=list)
    can_repair: bool = False


@dataclass
class IntegrityReport:
    """Report of an integrity scan."""
    job_id: str
    started_at: float
    finished_at: Optional[float] = None
    total_checked: int = 0
    passed: int = 0
    failed: int = 0
    repaired: int = 0
    errors: int = 0
    failures: list[ScanResult] = field(default_factory=list)
    error_items: list[tuple[str, str]] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000 if self.finished_at else 0
    
    @property
    def failure_rate(self) -> float:
        return self.failed / self.total_checked if self.total_checked > 0 else 0


class IntegrityScanner:
    """Periodic integrity scanner for compressed items.
    
    Phase 4E: Issue #17
    
    Scans random sample of compressed items to verify:
    1. Decompression succeeds
    2. Checksum matches (for lossless strategies)
    3. Similarity preserved (for lossy strategies)
    4. Metadata consistent
    
    Auto-repairs items where possible.
    """
    
    def __init__(
        self,
        engine: "CompressionEngine",
        sample_rate: float = 0.01,
        min_samples: int = 10,
        max_samples: int = 100,
    ):
        self._engine = engine
        self._sample_rate = sample_rate
        self._min_samples = min_samples
        self._max_samples = max_samples
        self._scan_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def run_scan(
        self,
        job_id: str,
        item_type: str | None = None,
    ) -> IntegrityReport:
        """Run integrity scan on sampled items.
        
        Args:
            job_id: Unique identifier for this scan.
            item_type: Optional filter ('memory' or 'cache'). None = all types.
            
        Returns:
            IntegrityReport with scan results.
        """
        report = IntegrityReport(job_id=job_id, started_at=time.time())
        
        logger.info(f"[{job_id}] Starting integrity scan")
        
        # Get sample of compressed items
        items = await self._get_sample_items(item_type)
        report.total_checked = len(items)
        
        logger.info(f"[{job_id}] Checking {len(items)} items")
        
        for item in items:
            try:
                result = await self._scan_item(item)
                
                if result.is_valid:
                    report.passed += 1
                else:
                    report.failed += 1
                    report.failures.append(result)
                    
                    # Auto-repair if possible
                    if result.can_repair:
                        await self._repair_item(item, result)
                        report.repaired += 1
                        
            except Exception as e:
                report.errors += 1
                report.error_items.append((item.get("id", "unknown"), str(e)))
                logger.error(f"[{job_id}] Error scanning {item.get('id')}: {e}")
        
        report.finished_at = time.time()
        
        # Update engine stats
        self._engine._stats.update_integrity_scan(
            passed=report.passed,
            failed=report.failed,
            repaired=report.repaired,
        )
        
        # Log summary
        logger.info(
            f"[{job_id}] Scan complete: {report.passed}/{report.total_checked} passed, "
            f"{report.failed} failed, {report.repaired} repaired "
            f"({report.duration_ms:.0f}ms)"
        )
        
        # Alert if high failure rate
        if report.failure_rate > 0.05:  # >5%
            logger.error(
                f"[{job_id}] HIGH FAILURE RATE: {report.failure_rate:.1%} "
                f"({report.failed}/{report.total_checked} items)"
            )
        
        return report
    
    async def _get_sample_items(
        self,
        item_type: str | None,
    ) -> list[dict]:
        """Get random sample of compressed items."""
        if not self._engine._db:
            return []
        
        # Determine sample size
        total = await self._engine._db.query(
            f"""
            SELECT COUNT(*) as cnt 
            FROM {item_type or 'memory'}
            WHERE compressed = TRUE
            """
        )
        
        total_count = total.get("cnt", 0) if total else 0
        if total_count == 0:
            return []
        
        sample_size = min(
            max(self._min_samples, int(total_count * self._sample_rate)),
            self._max_samples,
        )
        
        # Random sample
        items = await self._engine._db.query_many(
            f"""
            SELECT * FROM {item_type or 'memory'}
            WHERE compressed = TRUE
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (sample_size,),
        )
        
        # Also check tool_cache if item_type is None
        if item_type is None:
            cache_items = await self._engine._db.query_many(
                """
                SELECT * FROM tool_cache
                WHERE compressed = TRUE
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (sample_size // 2,),
            )
            items.extend(cache_items)
        
        return items
    
    async def _scan_item(self, item: dict) -> ScanResult:
        """Scan single item for integrity issues."""
        item_id = item.get("id", "")
        item_type = "cache" if "tool_name" in item else "memory"
        
        result = ScanResult(item_id=item_id, item_type=item_type)
        
        # 1. Check if compressed flag is set
        if not item.get("compressed"):
            result.issues.append("not_marked_compressed")
            result.is_valid = False
            return result
        
        # 2. Try decompression
        try:
            decompressed = await self._engine.decompress_item(item_id, item_type)
            if decompressed is None:
                result.issues.append("decompression_returned_none")
                result.can_repair = True  # Can restore from blob
                result.is_valid = False
                return result
        except Exception as e:
            result.issues.append(f"decompression_failed: {e}")
            result.can_repair = True
            result.is_valid = False
            return result
        
        # 3. Verify checksum if lossless compression
        compression_type = item.get("compression_type", "")
        if compression_type == "kv_compact":  # Lossless strategies
            original_hash = item.get("original_content_hash")
            if original_hash:
                decompressed_hash = hashlib.sha256(
                    decompressed.encode()
                ).hexdigest()
                if original_hash != decompressed_hash:
                    result.issues.append("checksum_mismatch")
                    result.can_repair = True
                    result.is_valid = False
                    return result
        
        # 4. Verify similarity for lossy compression
        if compression_type in ["truncation", "extractive"]:
            similarity = await self._validate_similarity(
                item.get("content", ""),
                decompressed,
            )
            if similarity < 0.80:  # Below acceptable threshold
                result.issues.append(f"similarity_too_low: {similarity:.2f}")
                result.can_repair = True
        
        # 5. Verify metadata consistency
        metadata = item.get("compression_metadata")
        if not metadata:
            result.issues.append("missing_metadata")
        
        # 6. Verify ratio guard still satisfied
        original_length = item.get("original_length", 0)
        compressed_length = item.get("compressed_length", 0)
        if original_length and compressed_length:
            ratio = compressed_length / original_length
            if ratio >= 0.95:  # Ratio guard threshold
                result.issues.append(f"ratio_guard_violated: {ratio:.2%}")
                result.can_repair = True
        
        result.is_valid = len(result.issues) == 0
        return result
    
    async def _validate_similarity(self, original: str, compressed: str) -> float:
        """Validate semantic similarity between original and compressed."""
        if not original or not compressed:
            return 0.0
        
        # Use overlap as proxy
        original_set = set(original.lower())
        compressed_set = set(compressed.lower())
        
        if not original_set:
            return 0.0
        
        overlap = len(original_set & compressed_set) / len(original_set)
        return max(0.0, min(1.0, overlap))
    
    async def _repair_item(self, item: dict, result: ScanResult) -> bool:
        """Attempt to repair corrupted item from original blob.
        
        Uses SAVEPOINT for transaction safety - if any step fails,
        the entire repair is rolled back.
        """
        item_id = item.get("id", "")
        item_type = "cache" if "tool_name" in item else "memory"
        
        logger.warning(
            f"Attempting repair for {item_id}: {result.issues}"
        )
        
        if not self._engine._db:
            logger.error(f"Cannot repair {item_id}: no database connection")
            return False
        
        savepoint = f"repair_{item_id}_{int(time.time() * 1000)}"
        
        try:
            # Begin transaction with SAVEPOINT
            await self._engine._db.execute(f"SAVEPOINT {savepoint}")
            
            # Restore from original blob
            success = await self._engine.report_compression_issue(
                item_id=item_id,
                item_type=item_type,
                reason=f"Integrity scan failed: {result.issues}",
            )
            
            if success:
                # Release SAVEPOINT on success
                await self._engine._db.execute(f"RELEASE SAVEPOINT {savepoint}")
                logger.info(f"Successfully repaired {item_id}")
                return True
            else:
                # Rollback on failure
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                logger.error(f"Failed to repair {item_id}: report_compression_issue returned False")
                return False
                
        except Exception as e:
            # Rollback on exception
            try:
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            except Exception:
                pass
            logger.error(f"Repair failed for {item_id}: {e}")
            return False
    
    async def start_periodic(self, interval_hours: int = 24) -> None:
        """Start periodic integrity scans.
        
        Args:
            interval_hours: Hours between scans.
        """
        if self._running:
            logger.warning("Integrity scanner already running")
            return
        
        self._running = True
        self._scan_task = asyncio.create_task(
            self._periodic_scan_loop(interval_hours)
        )
        logger.info(f"Started periodic integrity scanner (interval: {interval_hours}h)")
    
    async def stop_periodic(self) -> None:
        """Stop periodic integrity scans."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped periodic integrity scanner")
    
    async def _periodic_scan_loop(self, interval_hours: int) -> None:
        """Periodically run integrity scans."""
        while self._running:
            try:
                await asyncio.sleep(interval_hours * 3600)
                
                if self._running:
                    job_id = f"scan_{int(time.time())}"
                    await self.run_scan(job_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic scan error: {e}")
