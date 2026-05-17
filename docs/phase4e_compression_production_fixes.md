# Phase 4E – Compression Production Fixes (v4.6)

**Status**: Implementation In Progress
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
19. [Post-Production Fixes (v4.6.1)](#19-post-production-fixes-v461) ⭐ NEW
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
    
    def __init__(self, db: "AsyncSQLiteDB"):
        self._db = db
    
    async def compress_atomic(
        self,
        item_id: str,
        item_type: str,
        compressed_content: str,
        metadata: CompressionMetadata,
        original_hash: str,
    ) -> bool:
        """
        Atomically:
        1. INSERT original_blob
        2. UPDATE memory/cache item
        
        If either fails, ROLLBACK both.
        """
        savepoint_name = f"compress_{item_id}_{int(time.time() * 1000)}"
        
        try:
            await self._db.execute(f"SAVEPOINT {savepoint_name}")
            
            # Step 1: Save original blob for fallback
            blob_id = await self._save_original_blob_atomic(
                item_id=item_id,
                item_type=item_type,
                content_hash=original_hash,
            )
            
            if blob_id is None:
                await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False
            
            # Step 2: Update compressed item
            success = await self._update_compressed_item_atomic(
                item_id=item_id,
                item_type=item_type,
                compressed_content=compressed_content,
                metadata=metadata,
                blob_id=blob_id,
            )
            
            if not success:
                await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False
            
            # Commit the savepoint
            await self._db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            return True
            
        except Exception as e:
            await self._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            logger.error(f"Atomic compression failed for {item_id}: {e}")
            return False
    
    async def _save_original_blob_atomic(
        self,
        item_id: str,
        item_type: str,
        content_hash: str,
    ) -> int | None:
        """Insert original blob with dedup check."""
        # Check if blob already exists
        existing = await self._db.fetchone("""
            SELECT id FROM original_blobs 
            WHERE item_id = ? AND content_hash = ?
        """, item_id, content_hash)
        
        if existing:
            return existing["id"]
        
        result = await self._db.execute("""
            INSERT INTO original_blobs (
                item_id, content, content_hash, item_type, compressed_at
            ) VALUES (?, ?, ?, ?, ?)
        """, item_id, None, content_hash, item_type, int(time.time()))
        
        return result.lastrowid
    
    async def _update_compressed_item_atomic(
        self,
        item_id: str,
        item_type: str,
        compressed_content: str,
        metadata: CompressionMetadata,
        blob_id: int,
    ) -> bool:
        """Update item with compressed content."""
        table = "memory" if item_type == "memory" else "tool_cache"
        
        result = await self._db.execute(f"""
            UPDATE {table}
            SET content = ?,
                compressed = TRUE,
                compression_type = ?,
                compression_metadata = ?,
                original_length = COALESCE(original_length, LENGTH(content)),
                compressed_length = LENGTH(?),
                semantic_similarity = ?,
                last_compressed_at = ?,
                compression_attempt_count = 0,
                version = version + 1,
                original_blob_id = ?
            WHERE id = ? AND compressed = FALSE
        """, 
            compressed_content,
            metadata.strategy,
            json.dumps(metadata.to_dict()),
            compressed_content,
            metadata.semantic_similarity or 0.85,
            int(time.time()),
            blob_id,
            item_id,
        )
        
        return result.rowcount > 0
```

### Updated Engine Integration

```python
class CompressionEngine:
    def __init__(self, ...):
        self._atomic = AtomicCompression(self._db)
    
    async def compress_item(self, item_id: str, item_type: str, ...) -> bool:
        # ... existing checks ...
        
        compressed, metadata = await strategy.compress(item.content)
        
        # Atomic save_blob + compress
        original_hash = hashlib.sha256(item.content.encode()).hexdigest()
        
        success = await self._atomic.compress_atomic(
            item_id=item_id,
            item_type=item_type,
            compressed_content=compressed,
            metadata=metadata,
            original_hash=original_hash,
        )
        
        if success:
            self._invalidate_decompression_cache(item_id, item_type)
        
        return success
```

### UNIQUE Constraint for Original Blobs

```sql
-- Ensure no duplicate blobs for same item+hash combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_blobs_item_hash 
ON original_blobs(item_id, content_hash);

-- Reference count for deduplication tracking
ALTER TABLE original_blobs ADD COLUMN reference_count INTEGER DEFAULT 1;
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

### Solution: Token Ownership Lock

```python
import uuid
import asyncio
from typing import Optional
from dataclasses import dataclass

@dataclass
class LockToken:
    """Token that proves lock ownership."""
    value: str
    acquired_at: float
    expires_at: float

class SafeRedisDistributedLock(DistributedLock):
    """
    Redis distributed lock with token ownership.
    
    Prevents split-brain by:
    1. Storing unique token (UUID) on acquire
    2. Only releasing if token matches (compare-and-delete)
    3. Background heartbeat to renew locks
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "compression_lock:",
        default_timeout: float = 30.0,
        heartbeat_interval: float = 10.0,  # timeout / 3
        fallback_to_inmemory: bool = True,
    ):
        self._redis_url = redis_url
        self._prefix = prefix
        self._default_timeout = default_timeout
        self._heartbeat_interval = heartbeat_interval
        self._fallback = fallback_to_inmemory
        
        # Local token storage for release validation
        self._local_tokens: dict[str, LockToken] = {}
        self._fallback_locks: dict[str, LockToken] = {}
        self._fallback_count = 0
        
        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._active_locks: set[str] = set()
        self._lock = asyncio.Lock()
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        """Acquire lock with token ownership."""
        full_key = f"{self._prefix}{key}"
        token = str(uuid.uuid4())
        lock_timeout = int(max(timeout, self._default_timeout))
        
        try:
            redis = await self._get_redis()
            if redis is None:
                return await self._acquire_fallback(key, token, lock_timeout)
            
            # SET key token NX EX timeout
            acquired = await redis.set(
                full_key, 
                token, 
                nx=True, 
                ex=lock_timeout
            )
            
            if acquired:
                lock_token = LockToken(
                    value=token,
                    acquired_at=time.time(),
                    expires_at=time.time() + lock_timeout,
                )
                self._local_tokens[full_key] = lock_token
                
                # Start heartbeat for this lock
                async with self._lock:
                    self._active_locks.add(full_key)
                
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Redis lock acquire failed: {e}")
            return await self._acquire_fallback(key, token, lock_timeout)
    
    async def release(self, key: str) -> bool:
        """Release lock only if we own it (token match)."""
        full_key = f"{self._prefix}{key}"
        
        # Check local fallback first
        if full_key in self._fallback_locks:
            del self._fallback_locks[full_key]
            async with self._lock:
                self._active_locks.discard(full_key)
            return True
        
        # Check Redis
        try:
            redis = await self._get_redis()
            if redis is None:
                return True  # Already released
            
            # Compare-and-delete: only delete if value matches
            stored_token = await redis.get(full_key)
            local_token = self._local_tokens.get(full_key)
            
            if stored_token and local_token and stored_token == local_token.value:
                # Lua script for atomic compare-and-delete
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                result = await redis.eval(lua_script, 1, full_key, local_token.value)
                
                if result:
                    self._local_tokens.pop(full_key, None)
                    async with self._lock:
                        self._active_locks.discard(full_key)
                    return True
            
            return False  # Not owner or already expired
            
        except Exception as e:
            logger.warning(f"Redis lock release failed: {e}")
            return False
    
    async def _acquire_fallback(self, key: str, token: str, timeout: int) -> bool:
        """Fallback to in-memory lock."""
        if not self._fallback:
            return False
        
        self._fallback_count += 1
        if self._fallback_count == 1:
            logger.warning(
                "Redis unavailable, falling back to in-memory lock. "
                "Multi-instance safety NOT guaranteed."
            )
        
        full_key = f"{self._prefix}{key}"
        now = time.time()
        
        # Check if existing lock is valid
        if full_key in self._fallback_locks:
            existing = self._fallback_locks[full_key]
            if now < existing.expires_at:
                return False  # Already locked
        
        self._fallback_locks[full_key] = LockToken(
            value=token,
            acquired_at=now,
            expires_at=now + timeout,
        )
        return True
    
    async def _get_redis(self):
        """Get Redis connection."""
        try:
            import redis.asyncio as redis
            return await redis.from_url(self._redis_url)
        except:
            return None
    
    # === Heartbeat / Lock Renewal ===
    
    async def start_heartbeat(self) -> None:
        """Start background task to renew active locks."""
        if self._heartbeat_task is not None:
            return
        
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def stop_heartbeat(self) -> None:
        """Stop heartbeat task."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
    
    async def _heartbeat_loop(self) -> None:
        """Renew locks before they expire."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                async with self._lock:
                    locks_to_renew = list(self._active_locks)
                
                for full_key in locks_to_renew:
                    token = self._local_tokens.get(full_key)
                    if token:
                        await self._renew_lock(full_key, token)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _renew_lock(self, full_key: str, token: LockToken) -> None:
        """Renew lock expiration using PEXPIRE."""
        try:
            redis = await self._get_redis()
            if redis is None:
                return
            
            # Only renew if we still own it
            stored = await redis.get(full_key)
            if stored == token.value:
                new_expiry = int(self._default_timeout * 1000)  # ms
                await redis.pexpire(full_key, new_expiry)
                token.expires_at = time.time() + self._default_timeout
                
        except Exception as e:
            logger.warning(f"Lock renewal failed for {full_key}: {e}")
```

### Usage in Worker

```python
class CompressionWorker:
    async def run(self, interval_seconds: int = 3600) -> None:
        # Start lock heartbeat
        await self._distributed_lock.start_heartbeat()
        
        try:
            while not self._shutdown:
                await self._scan_and_compress_batch()
                await asyncio.sleep(interval_seconds)
        finally:
            await self._distributed_lock.stop_heartbeat()
    
    async def _scan_and_compress_batch(self) -> None:
        lock_key = "compression_worker_batch"
        
        if not await self._distributed_lock.acquire(lock_key, timeout=30.0):
            logger.info("Another worker instance is running this batch")
            return
        
        try:
            await self._process_batch()
        finally:
            await self._distributed_lock.release(lock_key)
```

---

## 4. Issue #5: Real LRU Implementation

### Problem

Current implementation uses `min(..., key=lambda k: self._cache[k][1])` which:
- Is O(n) for eviction
- Does NOT update access order on read
- Is not true LRU

### Solution: OrderedDict + RWLock

```python
from collections import OrderedDict
from typing import Optional
import threading

class RealLRUCache:
    """
    True LRU cache using OrderedDict.
    
    Features:
    - O(1) access, insert, evict
    - Automatic LRU ordering on access
    - Thread-safe with RWLock
    - TTL support
    """
    
    def __init__(
        self,
        maxsize: int = 1000,
        ttl_seconds: int = 300,
    ):
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._lock = threading.RLock()  # Reentrant for nested operations
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[str]:
        """Get item, updating LRU order."""
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
            
            # Verify checksum
            if checksum != self._compute_checksum(content):
                del self._cache[key]
                self._misses += 1
                self._corruption_detected += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return content
    
    def set(self, key: str, content: str) -> None:
        """Set item, evicting LRU if needed."""
        with self._lock:
            # Compute checksum
            checksum = self._compute_checksum(content)
            
            # If key exists, update and move to end
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (content, time.time(), checksum)
                return
            
            # Evict LRU items if at capacity
            while len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)  # Remove oldest (first)
            
            self._cache[key] = (content, time.time(), checksum)
    
    def _compute_checksum(self, content: str) -> str:
        """Compute fast checksum for corruption detection."""
        return hashlib.md5(content.encode()).hexdigest()
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
    
    def invalidate(self, key: str) -> None:
        """Remove specific item from cache."""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
```

---

## 5. Issue #6: Cache Thread Safety

### Problem

Dict-based cache has race conditions:
- Read while writing → KeyError
- Concurrent eviction → Lost updates
- Concurrent get+set → Inconsistent state

### Solution: asyncio.Lock for Async Context

```python
import asyncio
from collections import OrderedDict
from typing import Optional, Any

class AsyncSafeLRUCache:
    """
    Async-safe LRU cache with asyncio.Lock.
    
    Supports:
    - Concurrent reads/writes without corruption
    - True LRU ordering
    - TTL expiration
    - Memory-based eviction
    """
    
    def __init__(
        self,
        maxsize: int = 1000,
        ttl_seconds: int = 300,
        max_memory_mb: Optional[int] = None,
    ):
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._max_memory_mb = max_memory_mb
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._current_memory_bytes = 0
    
    async def get(self, key: str) -> Optional[str]:
        """Thread-safe get with LRU update."""
        async with self._lock:
            return self._get_unsafe(key)
    
    def _get_unsafe(self, key: str) -> Optional[str]:
        """Internal get without lock (caller must hold lock)."""
        if key not in self._cache:
            self._misses += 1
            return None
        
        content, timestamp, checksum = self._cache[key]
        
        if time.time() - timestamp > self._ttl:
            self._evict(key)
            self._misses += 1
            return None
        
        if checksum != self._compute_checksum(content):
            self._evict(key)
            self._misses += 1
            self._corruption_detected += 1
            return None
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return content
    
    async def set(self, key: str, content: str) -> None:
        """Thread-safe set with LRU eviction."""
        async with self._lock:
            self._set_unsafe(key, content)
    
    def _set_unsafe(self, key: str, content: str) -> None:
        """Internal set without lock (caller must hold lock)."""
        content_size = len(content.encode())
        checksum = self._compute_checksum(content)
        
        # Update existing
        if key in self._cache:
            old_content, _, _ = self._cache[key]
            self._current_memory_bytes -= len(old_content.encode())
            self._cache.move_to_end(key)
            self._cache[key] = (content, time.time(), checksum)
            self._current_memory_bytes += content_size
            return
        
        # Memory-based eviction
        if self._max_memory_mb:
            max_bytes = self._max_memory_mb * 1024 * 1024
            while self._current_memory_bytes + content_size > max_bytes and self._cache:
                oldest_key = next(iter(self._cache))
                self._evict(oldest_key)
        
        # Size-based eviction
        while len(self._cache) >= self._maxsize and self._cache:
            oldest_key = next(iter(self._cache))
            self._evict(oldest_key)
        
        self._cache[key] = (content, time.time(), checksum)
        self._current_memory_bytes += content_size
    
    def _evict(self, key: str) -> None:
        """Evict item and update memory counter."""
        if key in self._cache:
            content, _, _ = self._cache.pop(key)
            self._current_memory_bytes -= len(content.encode())
    
    def _compute_checksum(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()
    
    async def invalidate(self, key: str) -> None:
        """Remove specific item."""
        async with self._lock:
            self._evict(key)
    
    @property
    async def stats(self) -> dict:
        async with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / (self._hits + self._misses) if self._hits + self._misses > 0 else 0,
                "memory_bytes": self._current_memory_bytes,
                "memory_mb": self._current_memory_bytes / (1024 * 1024),
            }
```

---

## 6. Issue #7: Compression CPU/Resource Guards

### Problem

Single huge item can cause:
- CPU spike
- Memory exhaustion
- Worker stall

### Solution: Per-Item Resource Limits

```python
from dataclasses import dataclass
from typing import Optional
import signal

@dataclass
class ResourceLimits:
    """Per-item resource limits for compression."""
    max_cpu_time_ms: int = 5000  # 5 seconds max
    max_sentences: int = 500     # Cap for extractive summarizer
    max_json_fields: int = 100   # Max fields for KV compaction
    max_embedding_batch_size: int = 100  # Max sentences per embedding batch
    max_characters: int = 100_000  # 100K chars input limit

class ResourceGuardedCompressor:
    """Wraps compression with CPU/time guards."""
    
    def __init__(self, inner: CompressionStrategy, limits: ResourceLimits):
        self._inner = inner
        self._limits = limits
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        # Pre-check: content size
        if len(content) > self._limits.max_characters:
            logger.warning(f"Content exceeds max_characters, truncating")
            content = content[:self._limits.max_characters]
        
        # Run with timeout
        try:
            return await asyncio.wait_for(
                self._inner.compress(content),
                timeout=self._limits.max_cpu_time_ms / 1000
            )
        except asyncio.TimeoutError:
            logger.error(f"Compression timed out after {self._limits.max_cpu_time_ms}ms")
            # Return truncated content as fallback
            truncated = content[:self._limits.max_sentences * 100]
            return truncated, CompressionMetadata(
                strategy="timeout_fallback",
                params={"original_length": len(content)},
                error="timeout",
            )

# Process-level timeout using signal (Unix only)
class SignalTimeout:
    """Timeout using signal.alarm (Unix)."""
    
    @staticmethod
    def with_timeout(seconds: int, func, *args, **kwargs):
        def handler(signum, frame):
            raise TimeoutError(f"Function timed out after {seconds}s")
        
        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)
        
        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
```

### Configuration

```yaml
compression:
  limits:
    max_cpu_time_ms: 5000
    max_sentences: 500
    max_json_fields: 100
    max_embedding_batch_size: 100
    max_characters: 100000
```

---

## 7. Issue #8: ExtractiveSummarizer O(n²) Complexity

### Problem

MMR algorithm has nested loop:
```python
for idx in remaining:          # O(n)
    diversity = min(           # O(k) per iteration
        cosine_sim(sent_embs[idx], sent_embs[j])
        for j in selected
    )
```

For 1000 sentences: ~500K similarity computations per item.

### Solution: Sentence Cap + Approximate MMR

```python
class ExtractiveSummarizer(CompressionStrategy):
    def __init__(
        self,
        embedding_service: EmbeddingService,
        top_k_ratio: float = 0.3,
        diversity_lambda: float = 0.5,
        max_sentences: int = 200,        # NEW: Hard cap
        use_approximate_mmr: bool = True,  # NEW: Fast mode
    ):
        self._embedding_service = embedding_service
        self._top_k_ratio = top_k_ratio
        self._diversity_lambda = diversity_lambda
        self._max_sentences = max_sentences
        self._use_approximate_mmr = use_approximate_mmr
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        sentences = self._split_sentences(content)
        original_count = len(sentences)
        
        # HARD CAP: Never process more than max_sentences
        if len(sentences) > self._max_sentences:
            # Select evenly distributed subset
            step = len(sentences) / self._max_sentences
            indices = [int(i * step) for i in range(self._max_sentences)]
            sentences = [sentences[i] for i in indices]
        
        if len(sentences) <= 2:
            return content, CompressionMetadata(...)
        
        top_k = max(1, int(len(sentences) * self._top_k_ratio))
        
        # ... embedding and selection ...
        
        if self._use_approximate_mmr:
            selected = await self._approximate_mmr_select(...)
        else:
            selected = self._mmr_select(...)
        
        # ... return summary ...
    
    async def _approximate_mmr_select(
        self,
        query_emb: list[float],
        sent_embs: list[list[float]],
        k: int,
        lambda_: float,
    ) -> list[int]:
        """
        Approximate MMR using pre-computed similarity matrix.
        
        Reduces O(n²) to O(n) for similarity + O(k²) for selection.
        """
        n = len(sent_embs)
        selected = []
        remaining = list(range(n))
        
        # Compute relevance scores once: O(n)
        relevance_scores = [
            cosine_sim(query_emb, emb) 
            for emb in sent_embs
        ]
        
        # Pre-compute top-10 most similar for diversity (approximation)
        diversity_cache = self._precompute_local_diversity(sent_embs, top_k=10)
        
        for _ in range(min(k, n)):
            if not remaining:
                break
            
            best_score = float("-inf")
            best_idx = None
            
            for idx in remaining:
                relevance = relevance_scores[idx]
                
                # Use cached local diversity instead of min over all selected
                diversity = diversity_cache[idx].get(
                    min(selected, key=lambda j: diversity_cache[idx].get(j, 0))
                ) if selected else 0
                
                mmr_score = lambda_ * relevance - (1 - lambda_) * diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
            
            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)
        
        return selected
    
    def _precompute_local_diversity(
        self, 
        sent_embs: list[list[float]], 
        top_k: int
    ) -> list[dict[int, float]]:
        """
        Pre-compute top-k most similar for each sentence.
        
        Returns list where diversity_cache[i][j] = similarity(i, j) for j in top-k similar to i.
        """
        n = len(sent_embs)
        cache = [{} for _ in range(n)]
        
        for i in range(n):
            # Compute similarities only for next `top_k` items (sliding window approximation)
            for j in range(i + 1, min(i + top_k + 1, n)):
                sim = cosine_sim(sent_embs[i], sent_embs[j])
                cache[i][j] = sim
                cache[j][i] = sim
        
        return cache
```

---

## 8. Issue #9: Similarity Validation Sampling

### Problem

`_validate_similarity()` calls embedding service for every item:
- Compression cost = 2x embeddings (before + after)
- Slow for large batches

### Solution: Configurable Sampling Rate

```python
@dataclass
class QualityConfig:
    min_similarity: float = 0.85
    validate_before_commit: bool = True
    validation_sampling_rate: float = 0.1  # NEW: Validate 10% only
    
    # High-priority validation triggers
    validate_always_if_ratio_below: float = 0.3  # Always validate if ratio < 30%
    validate_always_if_suspicious: bool = True    # Suspicious metadata

class CompressionEngine:
    def __init__(self, config: CompressionConfig, ...):
        self._quality_config = config.quality
    
    async def _validate_similarity(
        self,
        original: str,
        compressed: str,
        item_id: str,
        metadata: CompressionMetadata,
    ) -> float:
        """Validate with sampling rate."""
        should_validate = (
            # Always validate if forced
            self._quality_config.validation_sampling_rate >= 1.0 or
            # Always validate if high compression ratio (suspicious)
            len(compressed) < len(original) * self._quality_config.validate_always_if_ratio_below or
            # Random sampling
            random.random() < self._quality_config.validation_sampling_rate or
            # Suspicious metadata
            (self._quality_config.validate_always_if_suspicious and metadata.error)
        )
        
        if not should_validate:
            # Skip embedding, use estimated similarity
            return metadata.semantic_similarity or 0.85
        
        # Do full embedding validation
        original_emb = await self._embedding_service.embed(original)
        compressed_emb = await self._embedding_service.embed(compressed)
        return cosine_sim(original_emb, compressed_emb)
```

### Configuration

```yaml
compression:
  quality:
    min_similarity: 0.85
    validate_before_commit: true
    validation_sampling_rate: 0.1      # Validate 10% only
    validate_always_if_ratio_below: 0.3  # Always check high compression
    validate_always_if_suspicious: true
```

---

## 9. Issue #10: SQLite Production Tuning

### Problem

Default SQLite settings cause:
- Write contention
- DB locked errors
- fsync stalls

### Solution: WAL Mode + Optimized PRAGMAs

```python
class OptimizedSQLiteDB:
    """SQLite with production-ready PRAGMAs."""
    
    PRAGMAS = {
        # WAL mode for concurrent reads/writes
        "journal_mode": "WAL",
        
        # NORMAL = good balance of safety and speed
        "synchronous": "NORMAL",
        
        # Memory for temp storage
        "temp_store": "MEMORY",
        
        # Memory-mapped I/O (256MB)
        "mmap_size": 268435456,
        
        # Cache size (negative = KB)
        "cache_size": -64000,  # 64MB
        
        # Foreign keys enforcement
        "foreign_keys": "ON",
        
        # Busy timeout
        "busy_timeout": 5000,  # 5 seconds
        
        # WAL auto-checkpoint
        "wal_autocheckpoint": 1000,  # Checkpoint every 1000 pages
        
        # Read uncommitted for isolation level
        "isolation_level": "read uncommitted",
    }
    
    async def execute_pragmas(self) -> None:
        """Execute all PRAGMAs on connection."""
        for pragma, value in self.PRAGMAS.items():
            await self.execute(f"PRAGMA {pragma} = {value}")
    
    async def execute(self, sql: str, *args) -> Result:
        """Execute with automatic retry on locked."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                return await self._conn.execute(sql, *args)
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                    continue
                raise
```

### In Database Setup

```python
async def setup_compression_database(db_path: str) -> None:
    """Initialize compression database with production settings."""
    db = await aiosqlite.connect(db_path)
    
    # Apply PRAGMAs
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA temp_store=MEMORY")
    await db.execute("PRAGMA mmap_size=268435456")
    await db.execute("PRAGMA cache_size=-64000")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA wal_autocheckpoint=1000")
    
    # Create schema...
```

---

## 10. Issues #11-13: Batch Processing & Recovery

### Issue #11: Batch Commit

### Solution

```python
class BatchCommitProcessor:
    """Process items in batches with single transaction."""
    
    def __init__(self, db: "AsyncSQLiteDB", batch_size: int = 50):
        self._db = db
        self._batch_size = batch_size
    
    async def process_batch(
        self,
        items: list[MemoryItem],
        compressor: Callable,
    ) -> BatchResult:
        """Process items in batch with transaction."""
        savepoint = f"batch_{int(time.time() * 1000)}"
        results = BatchResult()
        
        try:
            await self._db.execute(f"BEGIN TRANSACTION")
            
            for i, item in enumerate enumerate(items):
                try:
                    await self._db.execute(f"SAVEPOINT item_{i}")
                    
                    success = await self._process_single(
                        item, 
                        compressor,
                        correlation_id=f"{results.batch_id}_{i}",
                    )
                    
                    if success:
                        results.succeeded += 1
                    else:
                        results.failed += 1
                    
                    await self._db.execute(f"RELEASE SAVEPOINT item_{i}")
                    
                except Exception as e:
                    await self._db.execute(f"ROLLBACK TO SAVEPOINT item_{i}")
                    results.failed += 1
                    results.errors.append((item.id, str(e)))
                    logger.warning(f"Item {item.id} failed, continuing batch: {e}")
            
            await self._db.execute("COMMIT")
            
        except Exception as e:
            await self._db.execute("ROLLBACK")
            logger.error(f"Batch failed, rolled back: {e}")
            results.failed = len(items)
            results.rolled_back = True
        
        return results
```

### Issue #12: Per-Item Isolation (SAVEPOINT)

Already implemented above in `BatchCommitProcessor`.

### Issue #13: Partial Failure Recovery

```python
@dataclass
class BatchResult:
    """Result of batch processing."""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    succeeded: int = 0
    failed: int = 0
    rolled_back: bool = False
    errors: list[tuple[str, str]] = field(default_factory=list)  # (item_id, error)
    started_at: float = field(default_factory=time.time)
    
    @property
    def finished_at(self) -> float:
        return time.time()
    
    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000
    
    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "rolled_back": self.rolled_back,
            "errors": [{"item_id": item_id, "error": error} for item_id, error in self.errors],
            "duration_ms": self.duration_ms,
        }

class BatchRecoveryHandler:
    """Handle partial failure recovery."""
    
    async def recover(
        self,
        batch_result: BatchResult,
        engine: CompressionEngine,
    ) -> RecoveryReport:
        """Analyze batch result and trigger recovery actions."""
        report = RecoveryReport()
        
        # Check if total failure (rolled back)
        if batch_result.rolled_back:
            report.action = "NONE"  # Nothing to recover, all rolled back
            return report
        
        # Check for individual failures
        for item_id, error in batch_result.errors:
            # Log for manual review
            logger.warning(f"Failed item {item_id}: {error}")
            report.failed_items.append(item_id)
            
            # Auto-disable if repeated failures
            failure_count = await self._get_failure_count(item_id, engine)
            if failure_count >= 3:
                await engine.mark_no_compress(item_id)
                report.auto_disabled.append(item_id)
        
        return report
```

---

## 11. Issue #14: Cold Storage Deduplication

### Problem

Every compression saves full blob:
- 100 updates to same item = 100 duplicate blobs
- Storage explosion

### Solution: Deduplicate by Content Hash + Reference Count

```sql
-- UNIQUE constraint on item_id + content_hash
CREATE UNIQUE INDEX IF NOT EXISTS idx_blobs_dedup 
ON original_blobs(item_id, content_hash);

-- Reference count tracking
ALTER TABLE original_blobs ADD COLUMN reference_count INTEGER DEFAULT 1;

-- Index for blob cleanup
CREATE INDEX IF NOT EXISTS idx_blobs_refcount 
ON original_blobs(reference_count) WHERE reference_count <= 1;
```

```python
async def save_original_blob_dedup(
    self,
    item_id: str,
    content: str,
    content_hash: str,
    item_type: str,
) -> int:
    """
    Save blob with deduplication.
    
    If same content_hash already exists for this item:
    - Increment reference_count
    - Return existing blob_id
    
    Otherwise:
    - Insert new blob
    - Return new blob_id
    """
    existing = await self._db.fetchone("""
        SELECT id, reference_count FROM original_blobs
        WHERE item_id = ? AND content_hash = ?
    """, item_id, content_hash)
    
    if existing:
        # Increment reference count
        await self._db.execute("""
            UPDATE original_blobs 
            SET reference_count = reference_count + 1
            WHERE id = ?
        """, existing["id"])
        return existing["id"]
    
    # Insert new blob
    result = await self._db.execute("""
        INSERT INTO original_blobs (
            item_id, content, content_hash, item_type, 
            compressed_at, reference_count
        ) VALUES (?, ?, ?, ?, ?, 1)
    """, item_id, content, content_hash, item_type, int(time.time()))
    
    return result.lastrowid

async def cleanup_orphaned_blobs(self, retention_days: int = 30) -> int:
    """
    Clean up blobs with reference_count = 1 that haven't been accessed.
    
    Only removes blobs that:
    1. Have reference_count = 1 (not referenced)
    2. Are older than retention_days
    3. Are not the latest blob for any item
    """
    cutoff = time.time() - (retention_days * 86400)
    
    result = await self._db.execute("""
        DELETE FROM original_blobs
        WHERE reference_count <= 1
          AND compressed_at < ?
          AND id NOT IN (
              SELECT MAX(id) FROM original_blobs GROUP BY item_id
          )
    """, cutoff)
    
    return result.rowcount
```

---

## 12. Issue #15: Compression Ratio Guard

### Problem

Compression might produce larger output than input:
- Metadata overhead
- Tiny items
- Lossy compression on already-compressed data

### Solution: Reject if Not Worth It

```python
class CompressionRatioGuard:
    """Reject compression if ratio is not beneficial."""
    
    def __init__(
        self,
        min_ratio: float = 0.95,  # compressed must be < 95% of original
        absolute_min_savings: int = 100,  # But at least save 100 bytes
    ):
        self._min_ratio = min_ratio
        self._absolute_min_savings = absolute_min_savings
    
    def should_accept(
        self,
        original_length: int,
        compressed_length: int,
    ) -> tuple[bool, str]:
        """Check if compression result is acceptable."""
        
        # Ratio check
        if original_length > 0:
            ratio = compressed_length / original_length
            if ratio >= self._min_ratio:
                savings = original_length - compressed_length
                if savings < self._absolute_min_savings:
                    return False, f"Ratio {ratio:.2%} >= {self._min_ratio:.0%}, savings {savings}B < {self._absolute_min_savings}B"
        
        # Absolute savings check
        savings = original_length - compressed_length
        if savings < self._absolute_min_savings:
            return False, f"Only saves {savings}B, minimum {self._absolute_min_savings}B required"
        
        return True, "OK"

class CompressionEngine:
    def __init__(self, config: CompressionConfig, ...):
        self._ratio_guard = CompressionRatioGuard(
            min_ratio=config.quality.min_compression_ratio,
            absolute_min_savings=config.quality.absolute_min_savings_bytes,
        )
    
    async def compress_item(self, item_id: str, item_type: str, ...) -> bool:
        # ... existing checks ...
        
        compressed, metadata = await strategy.compress(item.content)
        
        # Ratio guard
        should_accept, reason = self._ratio_guard.should_accept(
            original_length=len(item.content),
            compressed_length=len(compressed),
        )
        
        if not should_accept:
            logger.info(f"Skipping {item_id}: {reason}")
            return False
        
        # ... continue with atomic save ...
```

### Configuration

```yaml
compression:
  quality:
    min_compression_ratio: 0.95      # compressed must be < 95% of original
    absolute_min_savings_bytes: 100  # But save at least 100 bytes
```

---

## 13. Issue #16: Priority Scheduling

### Problem

Current FIFO ordering by `last_updated`:
- Doesn't prioritize high-value compression
- Doesn't prioritize coldest items
- Doesn't prioritize largest savings

### Solution: Multi-Dimensional Priority Queue

```python
from enum import IntEnum

class CompressionPriority(IntEnum):
    """Priority levels for compression scheduling."""
    LOW = 1      # Recently accessed, small savings
    NORMAL = 2   # Standard items
    HIGH = 3     # Large items, cold, high savings potential
    CRITICAL = 4 # Overflow items, must compress

@dataclass
class CompressionDebt:
    """Debt metrics for priority calculation."""
    estimated_savings_bytes: int
    last_accessed: float
    access_count: int
    original_length: int

class PriorityScheduler:
    """
    Multi-dimensional priority scheduling.
    
    Priority = f(estimated_savings, coldness, size)
    """
    
    def __init__(
        self,
        savings_weight: float = 0.4,
        coldness_weight: float = 0.3,
        size_weight: float = 0.3,
        now: float = None,
    ):
        self._savings_weight = savings_weight
        self._coldness_weight = coldness_weight
        self._size_weight = size_weight
        self._now = now or time.time()
    
    def calculate_priority(self, debt: CompressionDebt) -> float:
        """
        Calculate priority score (higher = more urgent).
        
        Range: 0.0 to 1.0
        """
        # Normalize factors
        savings_score = self._normalize_savings(debt.estimated_savings_bytes)
        coldness_score = self._normalize_coldness(debt.last_accessed)
        size_score = self._normalize_size(debt.original_length)
        
        return (
            self._savings_weight * savings_score +
            self._coldness_weight * coldness_score +
            self._size_weight * size_score
        )
    
    def _normalize_savings(self, bytes_saved: int) -> float:
        """Higher savings = higher priority. Cap at 100KB."""
        return min(bytes_saved / (100 * 1024), 1.0)
    
    def _normalize_coldness(self, last_accessed: float) -> float:
        """Older items = higher priority. Cap at 90 days."""
        age_days = (self._now - last_accessed) / 86400
        return min(age_days / 90, 1.0)
    
    def _normalize_size(self, original_length: int) -> float:
        """Larger items = higher priority. Cap at 1MB."""
        return min(original_length / (1024 * 1024), 1.0)
    
    def get_priority_order(self, items: list[MemoryItem]) -> list[str]:
        """Return item IDs ordered by priority."""
        scored = []
        for item in items:
            debt = self._estimate_debt(item)
            priority = self.calculate_priority(debt)
            scored.append((item.id, priority))
        
        # Sort by priority descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item_id for item_id, _ in scored]
    
    def _estimate_debt(self, item: MemoryItem) -> CompressionDebt:
        """Estimate compression debt for an item."""
        # Assume 30% compression ratio for estimation
        estimated_savings = int(item.original_length * 0.3)
        
        return CompressionDebt(
            estimated_savings_bytes=estimated_savings,
            last_accessed=item.last_accessed or item.last_updated,
            access_count=item.access_count,
            original_length=item.original_length or len(item.content),
        )
```

### Updated Query with Priority

```python
async def _get_compressible_items(
    self,
    cutoff_time: float,
    batch_size: int,
) -> list[MemoryItem]:
    """
    Get items ordered by priority score.
    
    This replaces simple ORDER BY last_updated ASC
    """
    return await self._db.fetchall("""
        SELECT *,
            -- Estimated savings (assuming 30% compression)
            COALESCE(original_length, LENGTH(content)) * 0.3 AS estimated_savings,
            -- Coldness score (days since access)
            (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 AS coldness_days,
            -- Priority score (composite)
            (
                COALESCE(original_length, LENGTH(content)) * 0.3 * 0.4 +  -- savings weight
                (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 * 0.3 +  -- coldness weight  
                COALESCE(original_length, LENGTH(content)) * 0.3  -- size weight
            ) AS priority_score
        FROM memory
        WHERE compressed = FALSE
          AND no_compress = FALSE
          AND deleted = FALSE
          AND last_updated < ?
          AND (last_compressed_at IS NULL
               OR last_compressed_at < last_updated)
        ORDER BY priority_score DESC
        LIMIT ?
    """, cutoff_time, batch_size)
```

---

## 14. Issue #17: Integrity Scanner

### Problem

No verification that compressed items can be decompressed correctly:
- Silent corruption possible
- No early warning system

### Solution: Periodic Integrity Scanner

```python
import random

class IntegrityScanner:
    """
    Periodic integrity scanner for compressed items.
    
    Validates:
    1. Decompression succeeds
    2. Checksum matches
    3. Similarity preserved
    4. Metadata consistent
    """
    
    def __init__(
        self,
        engine: CompressionEngine,
        sample_rate: float = 0.01,  # 1% of items per scan
        min_samples: int = 10,
        max_samples: int = 100,
    ):
        self._engine = engine
        self._sample_rate = sample_rate
        self._min_samples = min_samples
        self._max_samples = max_samples
    
    async def run_scan(
        self,
        job_id: str,
        item_type: str = "memory",
    ) -> IntegrityReport:
        """
        Run integrity scan on sampled items.
        """
        report = IntegrityReport(
            job_id=job_id,
            started_at=time.time(),
        )
        
        # Get sample of compressed items
        items = await self._get_sample_items(item_type)
        report.total_checked = len(items)
        
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
                report.error_items.append((item.id, str(e)))
        
        report.finished_at = time.time()
        return report
    
    async def _get_sample_items(
        self,
        item_type: str,
    ) -> list[MemoryItem]:
        """Get random sample of compressed items."""
        # Count total
        total = await self._engine._db.fetchone(f"""
            SELECT COUNT(*) as cnt FROM {item_type}
            WHERE compressed = TRUE
        """)
        
        if not total or total["cnt"] == 0:
            return []
        
        sample_size = min(
            max(self._min_samples, int(total["cnt"] * self._sample_rate)),
            self._max_samples,
        )
        
        # Random sample using ORDER BY RANDOM() LIMIT (for small tables)
        # For large tables, use TABLESAMPLE SYSTEM
        return await self._engine._db.fetchall(f"""
            SELECT * FROM {item_type}
            WHERE compressed = TRUE
            ORDER BY RANDOM()
            LIMIT ?
        """, sample_size)
    
    async def _scan_item(self, item: MemoryItem) -> ScanResult:
        """Scan single item for integrity issues."""
        result = ScanResult(item_id=item.id)
        
        # 1. Try decompression
        try:
            decompressed = await self._engine.decompress_item(item.id, item.item_type)
            if decompressed is None:
                result.issues.append("decompression_returned_none")
                result.can_repair = False
                return result
        except Exception as e:
            result.issues.append(f"decompression_failed: {e}")
            result.can_repair = False
            return result
        
        # 2. Verify checksum if lossless
        if item.compression_type in ["kv_compact"]:
            original_hash = hashlib.sha256(item.content.encode()).hexdigest()
            decompressed_hash = hashlib.sha256(decompressed.encode()).hexdigest()
            if original_hash != decompressed_hash:
                result.issues.append("checksum_mismatch")
                result.can_repair = True  # Can restore from blob
                return result
        
        # 3. Verify similarity for lossy compression
        if item.compression_type in ["truncation", "extractive"]:
            similarity = await self._validate_similarity(item.content, decompressed)
            if similarity < 0.80:  # Below acceptable threshold
                result.issues.append(f"similarity_too_low: {similarity:.2f}")
                result.can_repair = True
        
        # 4. Verify metadata consistency
        if not item.compression_metadata:
            result.issues.append("missing_metadata")
        
        # 5. Verify ratio guard still satisfied
        if item.original_length and item.compressed_length:
            ratio = item.compressed_length / item.original_length
            if ratio >= 0.95:
                result.issues.append(f"ratio_guard_violated: {ratio:.2%}")
                result.can_repair = True
        
        result.is_valid = len(result.issues) == 0
        return result
    
    async def _repair_item(
        self,
        item: MemoryItem,
        result: ScanResult,
    ) -> None:
        """Attempt to repair corrupted item from original blob."""
        logger.warning(f"Attempting repair for {item.id}: {result.issues}")
        
        # Restore from original blob
        await self._engine.report_compression_issue(
            item_id=item.id,
            item_type=item.item_type,
            reason=f"Integrity scan failed: {result.issues}",
        )

@dataclass
class ScanResult:
    item_id: str
    is_valid: bool = False
    issues: list[str] = field(default_factory=list)
    can_repair: bool = False

@dataclass
class IntegrityReport:
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
```

### Scheduler Integration

```python
class IntegrityScanJob:
    """Scheduled integrity scanner."""
    
    def __init__(
        self,
        scanner: IntegrityScanner,
        interval_hours: int = 24,
    ):
        self._scanner = scanner
        self._interval_hours = interval_hours
    
    async def run(self) -> IntegrityReport:
        """Run scheduled scan."""
        job_id = f"scan_{int(time.time())}"
        logger.info(f"Starting integrity scan job {job_id}")
        
        report = await self._scanner.run_scan(job_id)
        
        logger.info(
            f"Scan {job_id} complete: {report.passed}/{report.total_checked} passed, "
            f"{report.failed} failed, {report.repaired} repaired"
        )
        
        # Alert if high failure rate
        if report.total_checked > 0:
            failure_rate = report.failed / report.total_checked
            if failure_rate > 0.05:  # >5% failure
                logger.error(
                    f"HIGH FAILURE RATE: {failure_rate:.1%} "
                    f"({report.failed}/{report.total_checked} items)"
                )
                # Could trigger alert here
        
        return report
```

---

## 15. Issue #18: Memory Pressure Handling

### Problem

Fixed size cache (1000 items) doesn't account for:
- Variable item sizes
- System memory pressure
- Other application memory usage

### Solution: Memory-Based Eviction

```python
import psutil

class MemoryAwareLRUCache:
    """
    LRU cache with memory-based eviction.
    
    Instead of max item count, limits by:
    - max_memory_mb: Maximum memory usage
    - max_items: Hard cap (safety)
    """
    
    def __init__(
        self,
        max_memory_mb: int = 100,
        max_items: int = 10000,
        ttl_seconds: int = 300,
        check_interval_seconds: int = 10,
    ):
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._max_items = max_items
        self._ttl = ttl_seconds
        self._check_interval = check_interval_seconds
        
        self._cache: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._current_memory = 0
        self._lock = asyncio.Lock()
        
        # Start memory monitor
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start_memory_monitor(self) -> None:
        """Start background task to check memory pressure."""
        self._monitor_task = asyncio.create_task(self._memory_monitor_loop())
    
    async def stop_memory_monitor(self) -> None:
        """Stop memory monitor."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _memory_monitor_loop(self) -> None:
        """Monitor system memory and evict if needed."""
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                
                # Check system memory pressure
                memory = psutil.virtual_memory()
                if memory.percent > 90:  # System under pressure
                    logger.warning(
                        f"System memory pressure high: {memory.percent:.0f}%, "
                        f"evicting cache"
                    )
                    await self._emergency_eviction()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory monitor error: {e}")
    
    async def _emergency_eviction(self) -> None:
        """Evict 50% of cache under memory pressure."""
        async with self._lock:
            evict_count = len(self._cache) // 2
            for _ in range(evict_count):
                if self._cache:
                    oldest_key = next(iter(self._cache))
                    self._evict(oldest_key)
    
    def get_memory_usage(self) -> dict:
        """Get current memory usage stats."""
        return {
            "current_bytes": self._current_memory,
            "current_mb": self._current_memory / (1024 * 1024),
            "max_bytes": self._max_memory_bytes,
            "max_mb": self._max_memory_bytes / (1024 * 1024),
            "usage_percent": (
                self._current_memory / self._max_memory_bytes * 100
                if self._max_memory_bytes > 0 else 0
            ),
            "item_count": len(self._cache),
            "max_items": self._max_items,
        }
```

---

## 16. Issue #19: Correlation IDs & Observability

### Problem

Logs lack correlation IDs:
- `worker_id`
- `batch_id`
- `compression_job_id`

Hard to debug distributed issues.

### Solution: Structured Logging with Correlation IDs

```python
import uuid
import contextvars
from typing import Optional

# Context variables for correlation
_worker_id: contextvars.ContextVar[str] = contextvars.ContextVar('worker_id', default='')
_batch_id: contextvars.ContextVar[str] = contextvars.ContextVar('batch_id', default='')
_job_id: contextvars.ContextVar[str] = contextvars.ContextVar('job_id', default='')

class CorrelationContext:
    """Context manager for correlation IDs."""
    
    def __init__(
        self,
        worker_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ):
        self._worker_id = worker_id or str(uuid.uuid4())[:8]
        self._batch_id = batch_id
        self._job_id = job_id
        self._tokens = []
    
    def __enter__(self):
        self._tokens.append(_worker_id.set(self._worker_id))
        if self._batch_id:
            self._tokens.append(_batch_id.set(self._batch_id))
        if self._job_id:
            self._tokens.append(_job_id.set(self._job_id))
        return self
    
    def __exit__(self, *args):
        for token in reversed(self._tokens):
            pass  # Context vars restore automatically

class StructuredLogger:
    """Logger with structured output and correlation IDs."""
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    
    def _format_message(self, msg: str, **kwargs) -> str:
        """Format message with correlation IDs."""
        parts = [
            f"[{_worker_id.get()[:8]}]",
            f"[{_batch_id.get()[:8]}]" if _batch_id.get() else "",
            f"[{_job_id.get()[:8]}]" if _job_id.get() else "",
            msg,
        ]
        
        if kwargs:
            extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return " ".join(parts) + " " + extra
        
        return " ".join(parts)
    
    def info(self, msg: str, **kwargs):
        self._logger.info(self._format_message(msg, **kwargs))
    
    def warning(self, msg: str, **kwargs):
        self._logger.warning(self._format_message(msg, **kwargs))
    
    def error(self, msg: str, **kwargs):
        self._logger.error(self._format_message(msg, **kwargs))
    
    def debug(self, msg: str, **kwargs):
        self._logger.debug(self._format_message(msg, **kwargs))

# Usage in Worker
class CompressionWorker:
    def __init__(self, worker_id: str, ...):
        self._worker_id = worker_id
        self._logger = StructuredLogger("compression_worker")
    
    async def run(self, interval_seconds: int = 3600) -> None:
        while not self._shutdown:
            batch_id = str(uuid.uuid4())[:8]
            
            with CorrelationContext(worker_id=self._worker_id, batch_id=batch_id):
                self._logger.info("Starting batch compression", batch_size=50)
                await self._scan_and_compress_batch()
                self._logger.info("Batch compression complete")
            
            await asyncio.sleep(interval_seconds)
    
    async def _scan_and_compress_batch(self) -> None:
        for i, item in enumerate(items):
            job_id = str(uuid.uuid4())[:8]
            
            with CorrelationContext(job_id=job_id):
                self._logger.info(
                    "Compressing item",
                    item_id=item.id,
                    position=f"{i}/{len(items)}",
                )
                
                success = await self._engine.compress_item(item.id, item.type)
                
                if success:
                    self._logger.info("Compression successful", 
                                     compression_ratio=0.7)
                else:
                    self._logger.warning("Compression failed",
                                        error_code="VERSION_MISMATCH")
```

---

## 17. Issue #20: Strategy Migration Framework

### Problem

When strategy changes (extractive v1 → v2):
- No way to recompress with new strategy
- Old items stuck with old strategy

### Solution: Strategy Migration Framework

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class StrategyVersion:
    """Version identifier for compression strategy."""
    name: str          # "extractive", "truncation", etc.
    version: str       # "1.0", "2.0", etc.
    
    def __str__(self) -> str:
        return f"{self.name}@{self.version}"

class StrategyMigration:
    """
    Framework for migrating compressed items when strategy changes.
    """
    
    def __init__(
        self,
        engine: CompressionEngine,
        strategy_registry: dict[str, CompressionStrategy],
    ):
        self._engine = engine
        self._registry = strategy_registry
    
    async def needs_recompression(
        self,
        item: MemoryItem,
        current_version: StrategyVersion,
    ) -> tuple[bool, str]:
        """
        Check if item needs recompression.
        
        Returns (needs_recompression, reason)
        """
        if not item.compressed:
            return False, "not_compressed"
        
        if item.no_compress:
            return False, "marked_no_compress"
        
        if not item.compression_type:
            return False, "no_strategy"
        
        # Parse stored strategy version
        stored = self._parse_strategy_version(item.compression_metadata)
        
        if not stored:
            return True, "missing_version"
        
        if stored.name != current_version.name:
            return True, f"strategy_changed: {stored} -> {current_version}"
        
        if stored.version != current_version.version:
            return True, f"version_changed: {stored} -> {current_version}"
        
        return False, "current"
    
    def _parse_strategy_version(
        self, 
        metadata: dict
    ) -> Optional[StrategyVersion]:
        """Parse strategy version from metadata."""
        if not metadata:
            return None
        
        return StrategyVersion(
            name=metadata.get("strategy", ""),
            version=metadata.get("strategy_version", "1.0"),
        )
    
    async def migrate_item(
        self,
        item: MemoryItem,
        new_strategy: str,
        new_version: str,
    ) -> bool:
        """Recompress item with new strategy."""
        # Get original content
        original = await self._engine._fallback_decompress(item.id, item.item_type)
        if not original:
            logger.error(f"Cannot migrate {item.id}: no original found")
            return False
        
        # Apply new strategy
        strategy_impl = self._registry.get(new_strategy)
        if not strategy_impl:
            logger.error(f"Unknown strategy: {new_strategy}")
            return False
        
        compressed, metadata = await strategy_impl.compress(original)
        
        # Update version info
        metadata.strategy_version = new_version
        
        # Atomic update with new strategy
        success = await self._engine._atomic.compress_atomic(
            item_id=item.id,
            item_type=item.item_type,
            compressed_content=compressed,
            metadata=metadata,
            original_hash=hashlib.sha256(original.encode()).hexdigest(),
        )
        
        return success
    
    async def find_items_needing_migration(
        self,
        target_version: StrategyVersion,
        limit: int = 100,
    ) -> list[str]:
        """Find compressed items that need recompression."""
        items = await self._engine._db.fetchall("""
            SELECT id FROM memory
            WHERE compressed = TRUE
              AND no_compress = FALSE
              AND deleted = FALSE
              AND (
                  compression_type != ?
                  OR json_extract(compression_metadata, '$.strategy_version') != ?
              )
            LIMIT ?
        """, target_version.name, target_version.version, limit)
        
        return [item["id"] for item in items]
    
    async def run_migration(
        self,
        target_version: StrategyVersion,
        batch_size: int = 50,
    ) -> MigrationReport:
        """Run migration for all items needing recompression."""
        report = MigrationReport(
            target_version=str(target_version),
            started_at=time.time(),
        )
        
        while True:
            items = await self.find_items_needing_migration(
                target_version,
                limit=batch_size,
            )
            
            if not items:
                break
            
            for item_id in items:
                item = await self._engine._get_item(item_id, "memory")
                if not item:
                    continue
                
                success = await self.migrate_item(item, target_version.name, target_version.version)
                
                if success:
                    report.migrated += 1
                else:
                    report.failed += 1
                    report.failures.append(item_id)
        
        report.finished_at = time.time()
        return report

@dataclass
class MigrationReport:
    target_version: str
    started_at: float
    finished_at: Optional[float] = None
    migrated: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
```

---

## 18. SQLite PRAGMA Configuration

### Summary of All PRAGMAs

```sql
-- === Production SQLite PRAGMAs ===

-- WAL mode for concurrent reads/writes (NOT rollback journal)
PRAGMA journal_mode=WAL;

-- NORMAL = good balance of safety and speed (not FULL, not OFF)
PRAGMA synchronous=NORMAL;

-- Store temp tables in memory
PRAGMA temp_store=MEMORY;

-- Memory-mapped I/O: 256MB
PRAGMA mmap_size=268435456;

-- Cache size: 64MB (negative = KB)
PRAGMA cache_size=-65536;

-- Enable foreign key enforcement
PRAGMA foreign_keys=ON;

-- Busy timeout: 5 seconds before returning SQLITE_BUSY
PRAGMA busy_timeout=5000;

-- WAL auto-checkpoint: checkpoint every 1000 pages
PRAGMA wal_autocheckpoint=1000;

-- Enable extended result codes
PRAGMA extended_result_codes=ON;

-- Enable memory-mapped stat (for ANALYZE)
PRAGMA query_only=OFF;

-- Read uncommitted for isolation level
PRAGMA read_uncommitted=1;
```

---

## 19. Files Modified

| File | Changes |
|------|---------|
| `compression/types.py` | Add `strategy_version`, `is_lossless` fields |
| `compression/config.py` | Add `ResourceLimits`, `QualityConfig`, `LimitsConfig` |
| `compression/engine.py` | Atomic transactions, ratio guard, CPU guards |
| `compression/worker.py` | Batch processing, correlation IDs, priority scheduling |
| `compression/cache.py` | Real LRU (OrderedDict), async-safe, memory pressure |
| `compression/decompression.py` | Integrity scanner, checksum validation |
| `compression/strategies/extractive.py` | Sentence cap, approximate MMR |
| `compression/strategies/base.py` | Resource limits support |
| `compression/distributed_lock.py` | Token ownership, heartbeat renewal |
| `compression/pruner.py` | Fix soft delete query (AND instead of OR) |
| `compression/batch_processor.py` | New: Batch commit, SAVEPOINTs, partial failure |
| `compression/integrity_scanner.py` | New: Periodic integrity verification |
| `compression/migration.py` | New: Strategy migration framework |
| `compression/priority_scheduler.py` | New: Multi-dimensional priority |
| `compression/correlation.py` | New: Correlation IDs for observability |
| `compression_schema.sql` | UNIQUE constraint, indexes, reference_count |
| `db_setup.py` | Apply PRAGMAs |

---

## 20. Implementation Checklist

### Critical (Must Implement)

- [ ] **#1**: Atomic transactions with SAVEPOINTs
- [ ] **#2-4**: Redis lock token ownership + heartbeat
- [ ] **#10**: SQLite WAL mode + PRAGMAs
- [ ] **#14**: Compression ratio guard
- [ ] **#11**: Fix soft delete query (AND instead of OR)

### High Priority

- [ ] **#5**: Real LRU (OrderedDict)
- [ ] **#6**: Async-safe cache with asyncio.Lock
- [ ] **#7**: CPU/resource guards
- [ ] **#8**: Sentence cap for extractive summarizer
- [ ] **#16**: Priority scheduling
- [ ] **#19**: Correlation IDs

### Medium Priority

- [ ] **#9**: Similarity validation sampling
- [ ] **#12**: Cold storage deduplication
- [ ] **#13**: Batch commit with partial failure recovery
- [ ] **#17**: Integrity scanner
- [ ] **#18**: Memory pressure handling
- [ ] **#20**: Strategy migration framework

### Testing

- [ ] Unit tests for atomic transactions
- [ ] Unit tests for token ownership lock
- [ ] Unit tests for real LRU cache
- [ ] Integration test for batch processing
- [ ] Chaos test for integrity scanner
- [ ] Property test for ratio guard

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
    optimistic_lock: true
    dry_run: false
    worker_id: "worker_1"  # For correlation
  
  strategies:
    default: extractive
    extractive:
      top_k_ratio: 0.3
      diversity_lambda: 0.5
      max_sentences: 200        # NEW
      use_approximate_mmr: true  # NEW
  
  limits:
    max_item_size_mb: 10
    max_embedding_chars: 50000
    max_cpu_time_ms: 5000       # NEW
    max_sentences: 500          # NEW
    max_json_fields: 100        # NEW
    max_embedding_batch_size: 100
  
  quality:
    min_similarity: 0.85
    validate_before_commit: true
    validation_sampling_rate: 0.1     # NEW: Validate 10% only
    validate_always_if_ratio_below: 0.3
    validate_always_if_suspicious: true
    min_compression_ratio: 0.95       # NEW: Reject if not beneficial
    absolute_min_savings_bytes: 100    # NEW
  
  decompression_cache:
    enabled: true
    maxsize: 1000
    ttl_seconds: 300
    max_memory_mb: 100  # NEW: Memory-based limit
  
  distributed_lock:
    redis_url: "redis://localhost:6379"
    prefix: "compression_lock:"
    default_timeout: 30.0
    heartbeat_interval: 10.0  # NEW: timeout / 3
    fallback_to_inmemory: true
  
  integrity_scanner:
    enabled: true
    interval_hours: 24
    sample_rate: 0.01
    min_samples: 10
    max_samples: 100
  
  priority_scheduling:
    enabled: true
    savings_weight: 0.4
    coldness_weight: 0.3
    size_weight: 0.3
  
  cold_storage:
    enabled: true
    blob_retention_days: 30
    keep_latest_blob_only: true
    deduplicate_by_hash: true  # NEW
```

---

## Appendix B: Version History

| Version | Date | Changes |
|---------|------|---------|
| v4.5 | 2026-05-17 | Initial production fixes |
| v4.6 | 2026-05-17 | 20 production issues addressed |
