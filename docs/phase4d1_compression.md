# Phase 4E – Compression Production Fixes (v4.6.1)

**Status**: Implementation Complete
**Date**: 2026-05-17
**Version**: v4.6.1
**Supersedes**: Phase 4D (v4.5)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Issue #1: Atomicity Gap - Transaction Safety](#2-issue-1-atomicity-gap---transaction-safety)
3. [Issues #2-4: Redis Lock Security](#3-issues-2-4-redis-lock-security)
4. [Issue #5: Real LRU Implementation](#4-issue-5-real-lru-implementation)
5. [Issue #6: Cache Thread Safety](#5-issue-6-cache-thread-safety)
6. [Issue #7: Compression CPU/Resource Guards](#6-issue-7-compression-cpuresource-guards)
7. [Issue #8: ExtractiveSummarizer O(n²) Complexity](#7-issue-8-extractivesummarizer-on²-complexity)
8. [Issue #9: Similarity Validation Sampling](#8-issue-9-similarity-validation-sampling)
9. [Issue #10: SQLite Production Tuning](#9-issue-10-sqlite-production-tuning)
10. [Issues #11-13: Batch Processing & Recovery](#10-issues-11-13-batch-processing--recovery)
11. [Issue #14: Cold Storage Deduplication](#11-issue-14-cold-storage-deduplication)
12. [Issue #15: Compression Ratio Guard](#12-issue-15-compression-ratio-guard)
13. [Issue #16: Priority Scheduling](#13-issue-16-priority-scheduling)
14. [Issue #17: Integrity Scanner](#14-issue-17-integrity-scanner)
15. [Issue #18: Memory Pressure Handling](#15-issue-18-memory-pressure-handling)
16. [Issue #19: Correlation IDs & Observability](#16-issue-19-correlation-ids--observability)
17. [Issue #20: Strategy Migration Framework](#17-issue-20-strategy-migration-framework)
18. [SQLite PRAGMA Configuration](#18-sqlite-pragma-configuration)
19. [Post-Production Fixes (v4.6.1)](#19-post-production-fixes-v461)
20. [Files Modified](#20-files-modified)
21. [Implementation Checklist](#21-implementation-checklist)

---

## 1. Executive Summary

This document addresses 20 critical production issues identified in Phase 4D compression implementation, plus 6 additional post-production fixes (v4.6.1):

| Category | Issues | Priority |
|----------|--------|----------|
| Data Integrity | #1, #14 | **Critical** |
| Distributed Safety | #2, #3, #4, #4a | **Critical** |
| Performance | #5, #8, #10, #16 | High |
| Resource Management | #6, #7, #18 | High |
| Observability | #19, #6a | High |
| Recoverability | #11, #13, #17, #1a | Medium |
| Cold Storage | #12 | Medium |
| Validation | #9, #15 | Medium |
| Future-proofing | #20 | Medium |

---

## 2. Issue #1: Atomicity Gap - Transaction Safety

### Problem

Current flow has no atomicity between saving original blob and updating compressed item:

```
save_original_blob()     ← Success
update_compressed_item() ← FAIL

Result: blob exists but item not marked compressed → inconsistent state
```

Or worse:

```
save_original_blob()     ← FAIL
update_compressed_item() ← Success

Result: item compressed but no fallback → data loss on corruption
```

### Solution: Database Transaction Wrapper

```python
class AtomicCompression:
    """Ensures atomic save_blob + compress operations."""

    async def compress_atomic(
        self,
        item_id: str,
        item_type: str,
        compressed_content: str,
        metadata: CompressionMetadata,
        original_hash: str,
    ) -> bool:
        savepoint_name = f"compress_{item_id}_{int(time.time() * 1000)}"

        try:
            await self._db.execute(f"SAVEPOINT {savepoint_name}")

            # Step 1: Save original blob for fallback
            blob_id = await self._save_original_blob_atomic(...)

            if blob_id is None:
                await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False

            # Step 2: Update compressed item
            success = await self._update_compressed_item_atomic(...)

            if not success:
                await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False

            await self._db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            return True

        except Exception as e:
            await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            logger.error(f"Atomic compression failed for {item_id}: {e}")
            return False
```

---

## 3. Issues #2-4: Redis Lock Security

### Problem: Split Brain Worker

```
Worker A: acquire lock (key=worker_lock)
         ↓ GC pause / network lag (5s)
         ↓ lock expires after 10s
Worker B: acquire NEW lock (key=worker_lock)
Worker A: resume, release lock
         ↓ releases Worker B's lock!
Worker C: acquire lock (unlocked!) → MULTIPLE WORKERS RUNNING
```

### Solution: Token Ownership Lock + Heartbeat + Health Check

```python
class SafeRedisDistributedLock(DistributedLock):
    """
    Redis distributed lock with:
    - Token ownership (UUID) for safe release
    - Background heartbeat to renew locks
    - Health check for auto-recovery when Redis comes back
    """

    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        full_key = f"{self._prefix}{key}"
        token = str(uuid.uuid4())
        lock_timeout = int(max(timeout, self._default_timeout))

        try:
            redis = await self._get_redis()
            acquired = await redis.set(full_key, token, nx=True, ex=lock_timeout)

            if acquired:
                self._local_tokens[full_key] = token
                async with self._lock:
                    self._active_locks.add(full_key)
                return True

            return False

        except Exception as e:
            logger.warning(f"Redis lock acquire failed: {e}")
            return await self._acquire_fallback(key, token, lock_timeout)

    async def _acquire_fallback(self, key: str, token: str, timeout: int) -> bool:
        """Fallback to in-memory lock when Redis is unavailable."""
        if not self._fallback:
            return False

        self._fallback_count += 1
        if self._fallback_count == 1:
            logger.warning("Redis unavailable, falling back to in-memory lock")

        self._fallback_locks[full_key] = LockToken(value=token, ...)
        # Track for later transfer to Redis
        self._pending_transfer_locks[key] = token
        return True

    async def _health_check_loop(self) -> None:
        """Periodically check Redis connectivity and recover from fallback."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)

                if await self._check_redis_connection():
                    was_unavailable = not self._redis_available
                    self._redis_available = True

                    if was_unavailable:
                        logger.info("Redis connection restored")
                        await self._transfer_pending_locks()
                else:
                    self._redis_available = False

            except asyncio.CancelledError:
                break

    async def _transfer_pending_locks(self) -> None:
        """Transfer in-memory locks to Redis when it recovers."""
        for key, token in list(self._pending_transfer_locks.items()):
            full_key = f"{self._prefix}{key}"
            acquired = await redis.set(full_key, token, nx=True, ex=int(self._timeout))

            if acquired:
                self._tokens[full_key] = token
                del self._pending_transfer_locks[key]
```

---

## 4. Issue #5: Real LRU Implementation

### Problem

Current implementation uses `min(..., key=lambda k: self._cache[k][1])` which is O(n) and doesn't update access order.

### Solution: OrderedDict + RWLock

```python
from collections import OrderedDict

class RealLRUCache:
    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            content, timestamp, checksum = self._cache[key]

            # Check TTL
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return content
```

---

## 5. Issue #6: Cache Thread Safety

### Solution: asyncio.Lock for Async Context

```python
class AsyncSafeLRUCache:
    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            return self._get_unsafe(key)
```

---

## 6. Issue #7: Compression CPU/Resource Guards

### Solution: Per-Item Resource Limits

```python
class ResourceGuardedCompressor:
    def __init__(self, inner: CompressionStrategy, limits: ResourceLimits):
        self._inner = inner
        self._limits = limits

    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        if len(content) > self._limits.max_characters:
            content = content[:self._limits.max_characters]

        try:
            return await asyncio.wait_for(
                self._inner.compress(content),
                timeout=self._limits.max_cpu_time_ms / 1000
            )
        except asyncio.TimeoutError:
            return truncated_fallback, CompressionMetadata(error="timeout")
```

---

## 7. Issue #8: ExtractiveSummarizer O(n²) Complexity

### Solution: Sentence Cap + Approximate MMR

```python
class ExtractiveSummarizer(CompressionStrategy):
    def __init__(self, max_sentences: int = 200, use_approximate_mmr: bool = True):
        self._max_sentences = max_sentences
        self._use_approximate_mmr = use_approximate_mmr

    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        sentences = self._split_sentences(content)

        # HARD CAP: Never process more than max_sentences
        if len(sentences) > self._max_sentences:
            step = len(sentences) / self._max_sentences
            indices = [int(i * step) for i in range(self._max_sentences)]
            sentences = [sentences[i] for i in indices]

        if self._use_approximate_mmr:
            selected = await self._approximate_mmr_select(...)
```

---

## 8. Issue #9: Similarity Validation Sampling

### Solution: Configurable Sampling Rate

```python
@dataclass
class QualityConfig:
    validation_sampling_rate: float = 0.1  # Validate 10% only
    validate_always_if_ratio_below: float = 0.3  # Always check high compression
    validate_always_if_suspicious: bool = True

async def _validate_similarity_sampled(self, original, compressed, item_id, metadata):
    should_validate = (
        self._config.validation_sampling_rate >= 1.0 or
        len(compressed) < len(original) * self._config.validate_always_if_ratio_below or
        random.random() < self._config.validation_sampling_rate or
        metadata.error
    )

    if not should_validate:
        return metadata.semantic_similarity or 0.85

    return await self._validate_similarity(original, compressed)
```

---

## 9. Issue #10: SQLite Production Tuning

### Solution: WAL Mode + Optimized PRAGMAs

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;
PRAGMA cache_size=-64000;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;
```

---

## 10. Issues #11-13: Batch Processing & Recovery

### Solution: BatchCommitProcessor with Retry

```python
class BatchCommitProcessor:
    async def commit_batch(self) -> bool:
        for attempt in range(self._max_retries + 1):
            try:
                await self._db.execute("COMMIT")
                self._commit_successes += 1
                return True
            except Exception as e:
                self._commit_failures += 1
                if attempt < self._max_retries:
                    self._total_retries += 1
                    delay_ms = min(self._base_delay_ms * (2 ** attempt), self._max_delay_ms)
                    logger.warning(f"Commit failed, retrying in {delay_ms}ms...")
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    await self._db.execute("ROLLBACK")
                    return False
```

---

## 11. Issue #14: Cold Storage Deduplication

### Solution: Deduplicate by Content Hash + Reference Count

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_blobs_dedup
ON original_blobs(item_id, content_hash);

ALTER TABLE original_blobs ADD COLUMN reference_count INTEGER DEFAULT 1;
```

```python
async def save_original_blob_dedup(self, item_id, content, content_hash, item_type):
    existing = await self._db.fetchone(
        "SELECT id FROM original_blobs WHERE item_id = ? AND content_hash = ?",
        item_id, content_hash
    )

    if existing:
        await self._db.execute(
            "UPDATE original_blobs SET reference_count = reference_count + 1 WHERE id = ?",
            existing["id"]
        )
        return existing["id"]

    return await self._db.execute("""
        INSERT INTO original_blobs (...) VALUES (..., 1)
    """)
```

---

## 12. Issue #15: Compression Ratio Guard

### Solution: Reject if Not Worth It

```python
class CompressionRatioGuard:
    def should_accept(self, original_length: int, compressed_length: int) -> tuple[bool, str]:
        if original_length == 0:
            return False, "original_length is zero"

        ratio = compressed_length / original_length
        savings = original_length - compressed_length

        if ratio >= self._min_ratio:
            if savings < self._absolute_min_savings:
                return False, f"Ratio {ratio:.2%} >= {self._min_ratio:.0%}, savings {savings}B"

        if savings < self._absolute_min_savings:
            return False, f"Only saves {savings}B, minimum {self._absolute_min_savings}B"

        return True, "OK"
```

---

## 13. Issue #16: Priority Scheduling

### Solution: Multi-Dimensional Priority Queue with Normalized Weights

```sql
SELECT *,
    CAST(LENGTH(content) * 0.3 AS INTEGER) as estimated_savings,
    (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 as coldness_days,
    (
        -- Normalized scores: each factor capped at reasonable maximum
        0.4 * MIN(CAST(LENGTH(content) * 0.3 AS REAL) / 30720.0, 1.0) +
        0.3 * MIN((strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 / 90.0, 1.0) +
        0.3 * MIN(CAST(LENGTH(content) AS REAL) / 1048576.0, 1.0)
    ) as priority_score
FROM memory
WHERE compressed = false AND no_compress = false AND deleted = false
ORDER BY priority_score DESC
LIMIT ?
```

---

## 14. Issue #17: Integrity Scanner

### Solution: Periodic Integrity Scanner with Auto-Repair

```python
class IntegrityScanner:
    async def _repair_item(self, item: dict, result: ScanResult) -> bool:
        """Attempt to repair corrupted item with SAVEPOINT rollback."""
        savepoint = f"repair_{item_id}_{int(time.time() * 1000)}"

        try:
            await self._engine._db.execute(f"SAVEPOINT {savepoint}")

            success = await self._engine.report_compression_issue(...)

            if success:
                await self._engine._db.execute(f"RELEASE SAVEPOINT {savepoint}")
                return True
            else:
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                return False

        except Exception as e:
            await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            logger.error(f"Repair failed for {item_id}: {e}")
            return False
```

---

## 15. Issue #18: Memory Pressure Handling

### Solution: Memory-Based Eviction

```python
class MemoryAwareLRUCache:
    def __init__(self, max_memory_mb: int = 100, max_items: int = 10000):
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._max_items = max_items

    def _set_unsafe(self, key: str, content: str) -> None:
        content_size = len(content.encode())

        # Memory-based eviction
        while self._current_memory_bytes + content_size > self._max_memory_bytes:
            oldest_key = next(iter(self._cache))
            self._evict(oldest_key)

        # Size-based eviction
        while len(self._cache) >= self._max_items:
            oldest_key = next(iter(self._cache))
            self._evict(oldest_key)
```

---

## 16. Issue #19: Correlation IDs & Observability

### Solution: Structured Logging with Correlation IDs

```python
_worker_id: contextvars.ContextVar[str] = contextvars.ContextVar('worker_id', default='')
_batch_id: contextvars.ContextVar[str] = contextvars.ContextVar('batch_id', default='')
_job_id: contextvars.ContextVar[str] = contextvars.ContextVar('job_id', default='')

class CompressionWorker:
    async def _scan_and_compress(self) -> BatchResult:
        batch_id = str(uuid.uuid4())[:8]

        with CorrelationContext(worker_id=self._worker_id, batch_id=batch_id):
            logger.info(f"[{self._worker_id}][{batch_id}] Starting compression batch")

            for i, item in enumerate(items):
                job_id = str(uuid.uuid4())[:8]
                with CorrelationContext(job_id=job_id):
                    success = await self._compress_item_safe(item_id, item_type)
```

---

## 17. Issue #20: Strategy Migration Framework

### Solution: Migration with Version Tracking

```python
class StrategyMigration:
    async def migrate_item(self, item_id, item_type, new_strategy, new_version) -> bool:
        original = await self._engine._fallback_decompress(item_id, item_type)
        if not original:
            return False

        strategy_impl = self._registry.get(new_strategy)
        compressed, metadata = await strategy_impl.compress(original)
        metadata.strategy_version = new_version

        return await self._engine._atomic.compress_atomic(
            item_id=item_id, item_type=item_type,
            compressed_content=compressed, metadata=metadata, ...
        )
```

---

## 18. SQLite PRAGMA Configuration

```sql
-- WAL mode for concurrent reads/writes
PRAGMA journal_mode=WAL;

-- Good balance of safety and speed
PRAGMA synchronous=NORMAL;

-- Store temp tables in memory
PRAGMA temp_store=MEMORY;

-- Memory-mapped I/O: 256MB
PRAGMA mmap_size=268435456;

-- Cache size: 64MB
PRAGMA cache_size=-65536;

-- Enable foreign keys
PRAGMA foreign_keys=ON;

-- Busy timeout: 5 seconds
PRAGMA busy_timeout=5000;

-- WAL auto-checkpoint
PRAGMA wal_autocheckpoint=1000;
```

---

## 19. Post-Production Fixes (v4.6.1)

### Fix #1a: Integrity Scanner Repair - SAVEPOINT Transaction Rollback

**Problem**: In `_repair_item()`, if repair fails mid-way, no rollback mechanism.

**Solution**: Wrap repair in SAVEPOINT:

```python
async def _repair_item(self, item: dict, result: ScanResult) -> bool:
    item_id = item.get("id", "")
    item_type = "cache" if "tool_name" in item else "memory"

    if not self._engine._db:
        return False

    savepoint = f"repair_{item_id}_{int(time.time() * 1000)}"

    try:
        await self._engine._db.execute(f"SAVEPOINT {savepoint}")

        success = await self._engine.report_compression_issue(...)

        if success:
            await self._engine._db.execute(f"RELEASE SAVEPOINT {savepoint}")
            return True
        else:
            await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            return False

    except Exception as e:
        try:
            await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        except Exception:
            pass
        logger.error(f"Repair failed for {item_id}: {e}")
        return False
```

---

### Fix #2a: Priority Scheduling Query - Weight Normalization

**Problem**: Weights were applied incorrectly: `estimated_savings * 0.3 * 0.4 = 0.12 * original_length`

**Solution**: Normalize each factor to 0-1 range before applying weights:

```sql
(
    0.4 * MIN(CAST(LENGTH(content) * 0.3 AS REAL) / 30720.0, 1.0) +
    0.3 * MIN((strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 / 90.0, 1.0) +
    0.3 * MIN(CAST(LENGTH(content) AS REAL) / 1048576.0, 1.0)
) as priority_score
```

---

### Fix #3a: no_compress_until Field Missing in Schema

**Problem**: `no_compress_until` was mentioned but not in schema.

**Solution**:

```sql
ALTER TABLE memory ADD COLUMN no_compress_until INTEGER DEFAULT 0;
ALTER TABLE tool_cache ADD COLUMN no_compress_until INTEGER DEFAULT 0;
```

```python
async def report_compression_issue(self, item_id, item_type, reason, disable_hours=None):
    hours = disable_hours or self._config.no_compress.disable_hours
    no_compress_until = int(time.time() + hours * 3600) if hours > 0 else 0

    await self._db.execute(
        f"""UPDATE {table}
            SET content = ?, compressed = false, no_compress = true,
                no_compress_until = ?, version = version + 1, last_updated = ?
            WHERE id = ?""",
        (original, no_compress_until, int(time.time()), item_id)
    )
```

---

### Fix #4a: Redis Lock Fallback - Auto-Recovery

**Problem**: When Redis recovers, system still uses in-memory lock.

**Solution**: Add health check loop:

```python
async def _health_check_loop(self) -> None:
    while True:
        await asyncio.sleep(self._health_check_interval)

        if await self._check_redis_connection():
            if not self._redis_available:
                logger.info("Redis connection restored")
                await self._transfer_pending_locks()
            self._redis_available = True
        else:
            self._redis_available = False

async def _transfer_pending_locks(self) -> None:
    for key, token in list(self._pending_transfer_locks.items()):
        acquired = await redis.set(f"{self._prefix}{key}", token, nx=True, ex=int(self._timeout))
        if acquired:
            del self._pending_transfer_locks[key]
```

---

### Fix #5a: Batch Commit Retry with Exponential Backoff

**Problem**: If COMMIT fails, entire batch lost.

**Solution**:

```python
class BatchCommitProcessor:
    async def commit_batch(self) -> bool:
        for attempt in range(self._max_retries + 1):
            try:
                await self._db.execute("COMMIT")
                return True
            except Exception as e:
                if attempt < self._max_retries:
                    delay_ms = min(self._base_delay_ms * (2 ** attempt), self._max_delay_ms)
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    await self._db.execute("ROLLBACK")
                    return False
```

---

### Fix #6a: Metrics for Integrity Scanner and Migration

**Problem**: New features not integrated into metrics system.

**Solution**: Add metrics to `CompressionStats`:

```python
@dataclass
class CompressionStats:
    # Integrity scanner metrics
    integrity_scan_passed: int = 0
    integrity_scan_failed: int = 0
    integrity_scan_repaired: int = 0

    # Migration metrics
    migration_migrated: int = 0
    migration_failed: int = 0

    def update_integrity_scan(self, passed=0, failed=0, repaired=0):
        self.integrity_scan_passed += passed
        self.integrity_scan_failed += failed
        self.integrity_scan_repaired += repaired

    def update_migration(self, migrated=0, failed=0):
        self.migration_migrated += migrated
        self.migration_failed += failed
```

---

## 20. Files Modified

| File | Changes |
|------|---------|
| `compression/types.py` | `strategy_version`, `is_lossless`, `no_compress_until`, integrity/migration metrics |
| `compression/config.py` | `ResourceLimits`, `QualityConfig`, `LimitsConfig`, `NoCompressConfig.disable_hours` |
| `compression/engine.py` | Atomic transactions, ratio guard, Redis health check, `no_compress_until` in rollback |
| `compression/worker.py` | Batch processing, correlation IDs, priority scheduling, `BatchCommitProcessor` |
| `compression/cache.py` | Real LRU (OrderedDict), async-safe, memory pressure |
| `compression/integrity_scanner.py` | SAVEPOINT rollback in repair, metrics update |
| `compression/migration.py` | Metrics update |
| `compression_schema.sql` | UNIQUE constraint, indexes, `no_compress_until` field |

---

## 21. Implementation Checklist

### Critical

- [x] **#1**: Atomic transactions with SAVEPOINTs
- [x] **#2-4**: Redis lock token ownership + heartbeat + health check
- [x] **#10**: SQLite WAL mode + PRAGMAs
- [x] **#14**: Compression ratio guard
- [x] **#11**: Fix soft delete query (AND instead of OR)

### High Priority

- [x] **#5**: Real LRU (OrderedDict)
- [x] **#6**: Async-safe cache with asyncio.Lock
- [x] **#7**: CPU/resource guards
- [x] **#8**: Sentence cap for extractive summarizer
- [x] **#16**: Priority scheduling (normalized weights)
- [x] **#19**: Correlation IDs

### Medium Priority

- [x] **#9**: Similarity validation sampling
- [x] **#12**: Cold storage deduplication
- [x] **#13**: Batch commit with retry
- [x] **#17**: Integrity scanner
- [x] **#18**: Memory pressure handling
- [x] **#20**: Strategy migration framework

### Post-Production Fixes (v4.6.1)

- [x] **#1a**: Integrity scanner repair SAVEPOINT rollback
- [x] **#2a**: Priority scheduling weight normalization
- [x] **#3a**: `no_compress_until` field in schema
- [x] **#4a**: Redis lock auto-recovery health check
- [x] **#5a**: Batch commit retry with exponential backoff
- [x] **#6a**: Integrity scanner and migration metrics

---

## Appendix A: Complete Configuration Reference

```yaml
compression:
  enabled: true

  worker:
    interval_seconds: 3600
    batch_size: 50
    rate_limit_items_per_second: 10
    max_attempts: 3
    min_age_days: 7

  strategies:
    default: extractive
    extractive:
      top_k_ratio: 0.3
      max_sentences: 200
      use_approximate_mmr: true

  quality:
    min_similarity: 0.85
    validation_sampling_rate: 0.1
    min_compression_ratio: 0.95
    absolute_min_savings_bytes: 100

  decompression_cache:
    enabled: true
    maxsize: 1000
    ttl_seconds: 300
    max_memory_mb: 100

  distributed_lock:
    redis_url: "redis://localhost:6379"
    default_timeout: 30.0
    heartbeat_interval: 10.0
    fallback_to_inmemory: true
    health_check_interval: 30.0  # NEW

  no_compress:
    disable_hours: 24  # NEW
    retry_after_hours: 24

  integrity_scanner:
    enabled: true
    interval_hours: 24
    sample_rate: 0.01

  priority_scheduling:
    enabled: true
    savings_weight: 0.4
    coldness_weight: 0.3
    size_weight: 0.3
```

---

## Appendix B: Version History

| Version | Date | Changes |
|---------|------|---------|
| v4.5 | 2026-05-17 | Initial production fixes |
| v4.6 | 2026-05-17 | 20 production issues addressed |
| v4.6.1 | 2026-05-17 | 6 post-production fixes (SAVEPOINT, weights, TTL, Redis recovery, batch retry, metrics) |
