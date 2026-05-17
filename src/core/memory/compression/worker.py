"""Background worker for compression tasks with rate limiting and optimistic locking.

Phase 4E Updates:
- Issue #16: Priority scheduling
- Issue #19: Correlation IDs
- Issue #13: Batch processing with SAVEPOINTs
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import contextvars
from typing import TYPE_CHECKING, Literal, Optional
from dataclasses import dataclass, field

from .config import WorkerConfig, PrioritySchedulingConfig
from .engine import CompressionEngine, InMemoryDistributedLock, DistributedLock

if TYPE_CHECKING:
    from .pruner import SoftDeletePruner, PermanentPurgeJob

logger = logging.getLogger(__name__)

# Phase 4E: Issue #19 - Correlation IDs
_worker_id: contextvars.ContextVar[str] = contextvars.ContextVar('worker_id', default='')
_batch_id: contextvars.ContextVar[str] = contextvars.ContextVar('batch_id', default='')
_job_id: contextvars.ContextVar[str] = contextvars.ContextVar('job_id', default='')


@dataclass
class BatchResult:
    """Phase 4E: Issue #13 - Result of batch processing."""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    started_at: float = field(default_factory=time.time)
    
    @property
    def duration_ms(self) -> float:
        return (time.time() - self.started_at) * 1000
    
    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
        }


class BatchCommitProcessor:
    """Phase 4E: Issue #5 - Batch commit with retry and exponential backoff.
    
    Handles batch database commits with automatic retry on failure.
    Uses exponential backoff to handle transient errors.
    """
    
    def __init__(
        self,
        db: "DatabaseAdapter | None" = None,
        max_retries: int = 3,
        base_delay_ms: float = 100.0,
        max_delay_ms: float = 5000.0,
    ):
        self._db = db
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        
        self._commit_successes = 0
        self._commit_failures = 0
        self._total_retries = 0
    
    def set_db(self, db: "DatabaseAdapter") -> None:
        """Set the database adapter."""
        self._db = db
    
    async def commit_batch(self) -> bool:
        """Execute COMMIT with retry and exponential backoff.
        
        Returns:
            True if commit successful.
        """
        if not self._db:
            logger.warning("No database configured for batch commit")
            return False
        
        for attempt in range(self._max_retries + 1):
            try:
                await self._db.execute("COMMIT")
                self._commit_successes += 1
                return True
                
            except Exception as e:
                self._commit_failures += 1
                
                if attempt < self._max_retries:
                    self._total_retries += 1
                    delay_ms = min(
                        self._base_delay_ms * (2 ** attempt),
                        self._max_delay_ms
                    )
                    logger.warning(
                        f"Commit failed (attempt {attempt + 1}/{self._max_retries + 1}): {e}. "
                        f"Retrying in {delay_ms}ms..."
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    logger.error(f"Commit failed after {self._max_retries + 1} attempts: {e}")
                    try:
                        await self._db.execute("ROLLBACK")
                    except Exception:
                        pass
                    return False
        
        return False
    
    def get_stats(self) -> dict:
        """Get commit statistics."""
        return {
            "commit_successes": self._commit_successes,
            "commit_failures": self._commit_failures,
            "total_retries": self._total_retries,
        }


class CorrelationContext:
    """Phase 4E: Issue #19 - Context manager for correlation IDs."""
    
    def __init__(
        self,
        worker_id: str | None = None,
        batch_id: str | None = None,
        job_id: str | None = None,
    ):
        self._worker_id = worker_id or str(uuid.uuid4())[:8]
        self._batch_id = batch_id
        self._job_id = job_id
    
    def __enter__(self):
        if self._worker_id:
            _worker_id.set(self._worker_id)
        if self._batch_id:
            _batch_id.set(self._batch_id)
        if self._job_id:
            _job_id.set(self._job_id)
        return self
    
    def __exit__(self, *args):
        pass


class PriorityScheduler:
    """Phase 4E: Issue #16 - Multi-dimensional priority scheduling."""
    
    def __init__(
        self,
        config: PrioritySchedulingConfig,
        now: float | None = None,
    ):
        self._config = config
        self._now = now or time.time()
        self._savings_weight = config.savings_weight
        self._coldness_weight = config.coldness_weight
        self._size_weight = config.size_weight
    
    def calculate_priority(self, item: dict) -> float:
        """Calculate priority score for an item."""
        content_length = len(item.get("content", "") or "")
        
        # Estimated savings (assuming 30% compression)
        estimated_savings = content_length * 0.3
        
        # Coldness (days since last access)
        last_accessed = item.get("last_accessed") or item.get("last_updated", 0)
        coldness_days = (self._now - last_accessed) / 86400
        
        # Normalize factors to 0-1 range
        savings_score = min(estimated_savings / (100 * 1024), 1.0)  # Cap at 100KB
        coldness_score = min(coldness_days / 90, 1.0)  # Cap at 90 days
        size_score = min(content_length / (1024 * 1024), 1.0)  # Cap at 1MB
        
        return (
            self._savings_weight * savings_score +
            self._coldness_weight * coldness_score +
            self._size_weight * size_score
        )
    
    def sort_by_priority(self, items: list[dict]) -> list[dict]:
        """Sort items by priority score descending."""
        scored = [(item, self.calculate_priority(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored]


class RateLimiter:
    """Token bucket rate limiter for compression worker.
    
    Features:
    - Configurable rate (items per second)
    - Burst handling
    - Async acquire with cooldown
    """
    
    def __init__(
        self,
        items_per_second: float = 10.0,
        burst_size: int = 10,
    ):
        self._rate = items_per_second
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def try_acquire(self) -> bool:
        """Try to acquire a token.
        
        Returns:
            True if token acquired, False otherwise.
        """
        async with self._lock:
            await self._refill()
            
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            
            return False
    
    async def acquire(self, timeout: float = 1.0) -> bool:
        """Acquire a token with optional waiting.
        
        Args:
            timeout: Maximum time to wait.
            
        Returns:
            True if acquired, False on timeout.
        """
        start = time.monotonic()
        
        while time.monotonic() - start < timeout:
            if await self.try_acquire():
                return True
            await asyncio.sleep(0.01)
        
        return False
    
    async def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        
        self._tokens = min(
            self._burst_size,
            self._tokens + elapsed * self._rate
        )
        self._last_refill = now


class CompressionWorker:
    """Background worker for compression tasks.
    
    Phase 4E Updates:
    - Issue #16: Priority scheduling
    - Issue #19: Correlation IDs
    - Issue #13: Batch processing with partial failure recovery
    """
    
    def __init__(
        self,
        engine: CompressionEngine,
        config: WorkerConfig | None = None,
        pruner: "SoftDeletePruner | None" = None,
        purge_job: "PermanentPurgeJob | None" = None,
        distributed_lock: "DistributedLock | None" = None,
        priority_config: PrioritySchedulingConfig | None = None,
        worker_id: str | None = None,
    ):
        self._engine = engine
        self._config = config or WorkerConfig()
        self._pruner = pruner
        self._purge_job = purge_job
        self._distributed_lock = distributed_lock or InMemoryDistributedLock()
        self._worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        
        # Phase 4E: Issue #16 - Priority scheduler
        self._priority_scheduler = PriorityScheduler(
            priority_config or PrioritySchedulingConfig()
        )
        
        self._rate_limiter = RateLimiter(
            items_per_second=self._config.rate_limit_items_per_second,
            burst_size=self._config.batch_size,
        )
        
        self._worker_task: asyncio.Task | None = None
        self._purge_task: asyncio.Task | None = None
        self._shutdown = False
        self._running = False
        
        self._items_processed = 0
        self._last_run_time: float = 0
        
        self._dry_run_reports: list[dict] = []
        
        # Set worker ID context
        _worker_id.set(self._worker_id)
    
    @property
    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._running
    
    @property
    def items_processed(self) -> int:
        """Get number of items processed."""
        return self._items_processed
    
    async def start(self, interval_seconds: int | None = None) -> None:
        """Start the background worker.
        
        Args:
            interval_seconds: Override for scan interval.
        """
        if self._running:
            logger.warning("Worker already running")
            return
        
        self._shutdown = False
        self._running = True
        
        interval = interval_seconds or self._config.interval_seconds
        
        self._worker_task = asyncio.create_task(
            self._run_loop(interval)
        )
        
        if self._purge_job:
            self._purge_task = asyncio.create_task(
                self._run_purge_loop()
            )
        
        logger.info(f"Compression worker started with interval {interval}s")
    
    async def stop(self) -> None:
        """Stop the background worker."""
        self._shutdown = True
        self._running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        if self._purge_task:
            self._purge_task.cancel()
            try:
                await self._purge_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Compression worker stopped")
    
    async def _run_loop(self, interval_seconds: int) -> None:
        """Main worker loop.
        
        Args:
            interval_seconds: Scan interval.
        """
        while not self._shutdown:
            try:
                await self._scan_and_compress()
                self._last_run_time = time.time()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Worker error: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    async def _run_purge_loop(self) -> None:
        """Purge loop - runs daily."""
        while not self._shutdown:
            try:
                await asyncio.sleep(86400)
                
                if self._pruner:
                    pruned = await self._pruner.prune()
                    logger.info(f"Soft deleted {pruned} items")
                
                if self._purge_job:
                    purged = await self._purge_job.purge()
                    logger.info(f"Permanently purged {purged} items")
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Purge error: {e}")
    
    async def _scan_and_compress(self) -> BatchResult:
        """Scan for compressible items and process them.
        
        Phase 4E:
        - Issue #19: Correlation IDs
        - Issue #13: Batch processing with partial failure recovery
        
        Returns:
            BatchResult with processing statistics.
        """
        if not self._engine._db:
            logger.warning("No database configured, skipping scan")
            return BatchResult()
        
        batch_id = str(uuid.uuid4())[:8]
        result = BatchResult(batch_id=batch_id)
        
        # Issue #19: Correlation context
        with CorrelationContext(worker_id=self._worker_id, batch_id=batch_id):
            logger.info(f"[{self._worker_id}][{batch_id}] Starting compression batch")
            
            # Acquire distributed lock
            lock_key = "compression_worker_lock"
            if not await self._distributed_lock.acquire(lock_key, timeout=30.0):
                logger.info(f"[{self._worker_id}][{batch_id}] Another worker running, skipping")
                return result
            
            try:
                cutoff_time = time.time() - (self._config.min_age_days * 86400)
                
                items = await self._get_compressible_items(cutoff_time)
                
                # Issue #16: Sort by priority
                if self._priority_scheduler._config.enabled:
                    items = self._priority_scheduler.sort_by_priority(items)
                
                logger.info(f"[{self._worker_id}][{batch_id}] Found {len(items)} items, processing...")
                
                # Dry-run mode
                if self._config.dry_run:
                    await self._dry_run_report(items, batch_id)
                    return result
                
                # Process items
                for i, item in enumerate(items):
                    if self._shutdown:
                        break
                    
                    if not await self._rate_limiter.try_acquire():
                        await asyncio.sleep(self._config.cooldown_seconds)
                        continue
                    
                    item_id = item["id"]
                    item_type = "memory" if "session_id" in item else "cache"
                    
                    # Issue #19: Per-item job correlation
                    job_id = str(uuid.uuid4())[:8]
                    with CorrelationContext(job_id=job_id):
                        success = await self._compress_item_safe(item_id, item_type)
                        
                        if success:
                            result.succeeded += 1
                            self._items_processed += 1
                        elif self._engine.last_error == "VERSION_MISMATCH":
                            result.skipped += 1
                            self._engine._stats.items_skipped_version_mismatch += 1
                        else:
                            result.failed += 1
            finally:
                await self._distributed_lock.release(lock_key)
            
            logger.info(
                f"[{self._worker_id}][{batch_id}] Batch complete: "
                f"succeeded={result.succeeded}, failed={result.failed}, "
                f"skipped={result.skipped}, duration={result.duration_ms:.0f}ms"
            )
        
        return result
    
    async def _get_compressible_items(
        self, cutoff_time: float
    ) -> list[dict]:
        """Get items eligible for compression.
        
        Phase 4E: Issue #16 - Priority scheduling with composite score.
        
        Args:
            cutoff_time: Items older than this time are eligible.
            
        Returns:
            List of item dictionaries ordered by priority.
        """
        db = self._engine._db
        batch_size = self._config.batch_size
        
        # Priority query with normalized composite score
        # Each factor is normalized to 0-1 range before applying weights
        priority_query = """
            SELECT *,
                CAST(LENGTH(content) * 0.3 AS INTEGER) as estimated_savings,
                (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 as coldness_days,
                LENGTH(content) as size_bytes,
                (
                    -- Normalized scores: each factor capped at reasonable maximum
                    -- savings_score: cap estimated_savings at 100KB equivalent (30KB savings)
                    0.4 * MIN(CAST(LENGTH(content) * 0.3 AS REAL) / 30720.0, 1.0) +
                    -- coldness_score: cap at 90 days
                    0.3 * MIN((strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 / 90.0, 1.0) +
                    -- size_score: cap at 1MB
                    0.3 * MIN(CAST(LENGTH(content) AS REAL) / 1048576.0, 1.0)
                ) as priority_score
            FROM memory
            WHERE compressed = false
              AND no_compress = false
              AND deleted = false
              AND last_updated < ?
            ORDER BY priority_score DESC
            LIMIT ?
        """
        
        memory_items = await db.query_many(
            priority_query if self._priority_scheduler._config.enabled else """
                SELECT * FROM memory
                WHERE compressed = false
                  AND no_compress = false
                  AND deleted = false
                  AND last_updated < ?
                ORDER BY last_updated ASC
                LIMIT ?
            """,
            (cutoff_time, batch_size),
        )
        
        cache_items = await db.query_many(
            """
            SELECT * FROM tool_cache
            WHERE compressed = false
              AND no_compress = false
              AND deleted = false
              AND last_updated < ?
            ORDER BY last_updated ASC
            LIMIT ?
            """,
            (cutoff_time, batch_size // 2),
        )
        
        return memory_items + cache_items
    
    async def _compress_item_safe(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> bool:
        """Compress item with error handling.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
            
        Returns:
            True if successful.
        """
        try:
            return await self._engine.compress_item(item_id, item_type)
        except Exception as e:
            logger.error(f"Compression failed for {item_id}: {e}")
            self._engine._stats.items_failed += 1
            return False
    
    async def run_once(self) -> int:
        """Run one compression cycle.
        
        Returns:
            Number of items compressed.
        """
        initial_count = self._items_processed
        await self._scan_and_compress()
        return self._items_processed - initial_count
    
    async def _dry_run_report(self, items: list[dict]) -> None:
        """Generate dry-run report without actual compression (Fix #9).
        
        Args:
            items: List of items that would be compressed.
        """
        logger.info(f"[DRY-RUN] Would compress {len(items)} items:")
        
        for item in items[:10]:  # Log first 10 for brevity
            item_type = "memory" if "session_id" in item else "cache"
            content_len = len(item.get("content", ""))
            last_updated = item.get("last_updated", 0)
            age_days = (time.time() - last_updated) / 86400
            
            report = {
                "item_id": item.get("id"),
                "item_type": item_type,
                "content_length": content_len,
                "age_days": round(age_days, 1),
                "last_updated": last_updated,
            }
            
            self._dry_run_reports.append(report)
            logger.info(f"[DRY-RUN] {item_type}:{item.get('id')} - "
                       f"len={content_len}, age={age_days:.1f} days")
        
        if len(items) > 10:
            logger.info(f"[DRY-RUN] ... and {len(items) - 10} more items")
    
    def get_dry_run_reports(self) -> list[dict]:
        """Get accumulated dry-run reports."""
        return self._dry_run_reports.copy()
    
    def clear_dry_run_reports(self) -> None:
        """Clear accumulated dry-run reports."""
        self._dry_run_reports.clear()
    
    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "running": self._running,
            "items_processed": self._items_processed,
            "last_run_time": self._last_run_time,
            "dry_run_count": len(self._dry_run_reports),
            "config": {
                "interval_seconds": self._config.interval_seconds,
                "batch_size": self._config.batch_size,
                "rate_limit": self._config.rate_limit_items_per_second,
                "min_age_days": self._config.min_age_days,
                "dry_run": self._config.dry_run,
            },
            "engine_stats": self._engine._stats.to_dict(),
        }
