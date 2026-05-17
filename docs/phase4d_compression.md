# Phase 4D – Compression & Memory Optimization (v4.5)

**Status**: Superseded by Phase 4E
**Date**: 2026-05-17
**Version**: v4.5
**Test Coverage**: 133 tests pass

> **IMPORTANT**: This document has been superseded by **Phase 4E** (`docs/phase4e_compression_production_fixes.md`).
> Phase 4E addresses 20 critical production issues including atomicity, distributed locks, and more.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Compression Strategies](#3-compression-strategies)
4. [CompressionEngine API](#4-compressionengine-api)
5. [Background Worker](#5-background-worker)
6. [Decompression](#6-decompression)
7. [Soft Delete & Permanent Purge](#7-soft-delete--permanent-purge)
8. [Database Schema](#8-database-schema)
9. [Configuration](#9-configuration)
10. [Metrics](#10-metrics)
11. [Test Plan](#11-test-plan)
12. [Definition of Done](#12-definition-of-done)
13. [File Structure](#13-file-structure)
14. [Production Fixes v4.1](#14-production-fixes-v41)
15. [Test Coverage Summary](#15-test-coverage-summary)
16. [Production Fixes v4.2](#16-production-fixes-v42)
17. [Configuration Reference](#17-configuration-reference)
18. [Production Fixes v4.3](#18-production-fixes-v43)
19. [Production Fixes v4.4](#19-production-fixes-v44)
20. [Production Fixes v4.5](#20-production-fixes-v45)
21. [Known Limitations](#21-known-limitations)

---

## 1. System Overview

### 1.1 Purpose

Build a compression and memory optimization layer for SemanticMemory (Phase 4A) and ToolCache (Phase 4B), enabling:

- Reduced storage footprint and retrieval latency
- Semantic similarity preservation (≥ 0.85)
- Multiple compression strategies: truncation, extractive summarization, key-value compaction, adaptive pruning
- Reversible compression with metadata + hash fallback
- Agent-controllable compression (no_compress flag)
- Background worker with incremental scan, rate limiting, optimistic lock
- Feedback-based rollback

### 1.2 Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Safe-concurrent** | Worker uses optimistic lock to prevent overwriting new data |
| **Time-aware** | Only compress items old enough (last_updated < now - min_age_days) |
| **Reversible by design** | Metadata + original hash ensure fallback capability |
| **Soft delete first** | Pruner marks deleted=true, not permanent delete |
| **Cached decompression** | LRU cache reduces CPU for frequent reads |
| **Testable** | Generators provided for property-based tests |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CompressionEngine                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            Strategy Registry (Pluggable)              │    │
│  │  ├── TruncationCompressor                           │    │
│  │  ├── ExtractiveSummarizer (MMR)                     │    │
│  │  ├── KeyValueCompactor                              │    │
│  │  └── AdaptivePruner                                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Background Worker                        │    │
│  │  ├── Incremental scan (last_updated, last_compressed) │    │
│  │  ├── Optimistic lock (version check)                 │    │
│  │  ├── Rate limiter (items/s, batch, cooldown)         │    │
│  │  └── Quality validator (similarity ≥ 0.85)           │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Decompression Layer                     │    │
│  │  ├── LRU cache (maxsize=1000, TTL=1h)              │    │
│  │  ├── Fallback to original_blobs table               │    │
│  │  └── Metadata reconstruction                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Soft Delete Pruner                       │    │
│  │  ├── Set deleted=true (soft delete)                 │    │
│  │  └── Permanent purge job (deleted=true + age)      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Storage Layer                           │
│  ┌──────────────────┐    ┌──────────────────┐               │
│  │  memory table   │    │ tool_cache table │               │
│  │ (with compress) │    │ (with compress)  │               │
│  └──────────────────┘    └──────────────────┘               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              original_blobs table                     │  │
│  │     (fallback storage for compressed items)          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Compression Strategies

### 3.1 TruncationCompressor

Cuts content from the middle, keeping beginning and end (for code/logs).

```python
class TruncationCompressor(CompressionStrategy):
    def __init__(self, max_chars: int = 2000, keep_both_ends: bool = True):
        self.max_chars = max_chars
        self.keep_both_ends = keep_both_ends
    
    def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        if len(content) <= self.max_chars:
            return content, CompressionMetadata(strategy="truncation", ...)
        
        if self.keep_both_ends:
            head_len = (self.max_chars - 3) // 2
            tail_len = self.max_chars - 3 - head_len
            compressed = content[:head_len] + "..." + content[-tail_len:]
        else:
            compressed = content[:self.max_chars]
        
        metadata = CompressionMetadata(
            strategy="truncation",
            params={"max_chars": self.max_chars, "keep_both_ends": self.keep_both_ends},
            selected_indices=None,
            start_truncate=0,
            end_truncate=len(content) - len(compressed)
        )
        return compressed, metadata
```

### 3.2 ExtractiveSummarizer (MMR)

Uses embeddings to select diverse, relevant sentences using Maximal Marginal Relevance.

```python
class ExtractiveSummarizer(CompressionStrategy):
    def __init__(
        self,
        embedding_service: EmbeddingService,
        top_k_ratio: float = 0.3,
        diversity_lambda: float = 0.5
    ):
        self.embedding_service = embedding_service
        self.top_k_ratio = top_k_ratio
        self.diversity_lambda = diversity_lambda
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        sentences = self._split_sentences(content)
        
        if len(sentences) <= 2:
            return content, CompressionMetadata(strategy="extractive", ...)
        
        top_k = max(1, int(len(sentences) * self.top_k_ratio))
        
        query_emb = await self.embedding_service.embed(content)
        sent_embs = await self.embedding_service.embed_batch(sentences)
        
        selected = self._mmr_select(query_emb, sent_embs, top_k, self.diversity_lambda)
        selected.sort()
        
        summary = " ".join(sentences[i] for i in selected)
        
        metadata = CompressionMetadata(
            strategy="extractive",
            params={"top_k_ratio": self.top_k_ratio, "diversity_lambda": self.diversity_lambda},
            selected_indices=selected,
            model_version=self.embedding_service.model_version
        )
        return summary, metadata
    
    def _mmr_select(
        self,
        query_emb: list[float],
        sent_embs: list[list[float]],
        k: int,
        lambda_: float
    ) -> list[int]:
        """Maximal Marginal Relevance selection for diversity."""
        n = len(sent_embs)
        selected = []
        remaining = set(range(n))
        
        for _ in range(min(k, n)):
            if not remaining:
                break
            
            best_score = float("-inf")
            best_idx = None
            
            for idx in remaining:
                relevance = cosine_sim(query_emb, sent_embs[idx])
                diversity = min(
                    cosine_sim(sent_embs[idx], sent_embs[j])
                    for j in selected
                ) if selected else 0
                
                mmr_score = lambda_ * relevance - (1 - lambda_) * diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
            
            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)
        
        return selected
```

### 3.3 KeyValueCompactor

Keeps important fields based on access patterns.

```python
class KeyValueCompactor(CompressionStrategy):
    def __init__(self, keep_fields_ratio: float = 0.5):
        self.keep_fields_ratio = keep_fields_ratio
    
    def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return content, CompressionMetadata(strategy="kv_compact", error="not_json")
        
        if not isinstance(data, dict):
            return content, CompressionMetadata(strategy="kv_compact", error="not_dict")
        
        field_scores = self._calculate_field_scores(data)
        sorted_fields = sorted(field_scores.items(), key=lambda x: x[1], reverse=True)
        
        keep_count = max(1, int(len(sorted_fields) * self.keep_fields_ratio))
        kept_fields = [f[0] for f in sorted_fields[:keep_count]]
        
        compacted = {k: v for k, v in data.items() if k in kept_fields}
        
        metadata = CompressionMetadata(
            strategy="kv_compact",
            params={"keep_fields_ratio": self.keep_fields_ratio},
            kept_fields=kept_fields
        )
        return json.dumps(compacted), metadata
    
    def _calculate_field_scores(self, data: dict) -> dict[str, float]:
        """Calculate importance scores based on value characteristics."""
        scores = {}
        for key, value in data.items():
            score = 1.0
            if isinstance(value, str):
                score += len(value) / 100
            elif isinstance(value, (int, float)):
                score += abs(value) / 1000
            elif isinstance(value, list):
                score += len(value) / 10
            elif isinstance(value, dict):
                score += len(value) * 2
            scores[key] = score
        return scores
```

### 3.4 AdaptivePruner (Soft Delete)

Marks items for deletion without immediate removal.

```python
class AdaptivePruner:
    def __init__(
        self,
        prune_after_days: int = 30,
        min_access_count: int = 2,
        soft_delete: bool = True
    ):
        self.prune_after_days = prune_after_days
        self.min_access_count = min_access_count
        self.soft_delete = soft_delete
    
    def should_prune(self, item: MemoryItem) -> bool:
        """Check if item should be soft deleted."""
        if item.no_compress or item.deleted:
            return False
        
        age_days = (time.time() - item.last_updated) / 86400
        if age_days < self.prune_after_days:
            return False
        
        if item.access_count < self.min_access_count:
            return False
        
        return True
    
    def mark_deleted(self, item_id: str) -> dict:
        """Mark item as soft deleted."""
        return {
            "deleted": True,
            "deleted_at": time.time(),
            "cold_storage_ref": f"cold://{item_id}"
        }
```

---

## 4. CompressionEngine API

```python
class CompressionEngine:
    """Main compression engine with strategy registry."""
    
    def __init__(
        self,
        db_path: str,
        config: CompressionConfig,
        embedding_service: EmbeddingService | None = None
    ):
        self._strategies: dict[str, CompressionStrategy] = {}
        self._config = config
        self._embedding_service = embedding_service
        self._decompression_cache = LRUCache(maxsize=1000)
        self._worker_task: asyncio.Task | None = None
        self._shutdown = False
    
    async def register_strategy(self, name: str, strategy: CompressionStrategy) -> None:
        """Register a compression strategy."""
        self._strategies[name] = strategy
    
    async def compress_item(
        self,
        item_id: str,
        item_type: Literal["memory", "cache"],
        strategy: str | None = None
    ) -> bool:
        """Compress a single item."""
        item = await self._get_item(item_id, item_type)
        if not item:
            return False
        
        if item.no_compress or item.compressed or item.deleted:
            return False
        
        age_threshold = self._config.min_age_days * 86400
        if time.time() - item.last_updated < age_threshold:
            return False
        
        strategy_name = strategy or self._config.default_strategy
        strategy_impl = self._strategies.get(strategy_name)
        if not strategy_impl:
            return False
        
        compressed, metadata = await strategy_impl.compress(item.content)
        
        if self._config.validate_before_commit:
            similarity = await self._validate_similarity(item.content, compressed)
            if similarity < self._config.min_similarity:
                item.compression_attempt_count += 1
                if item.compression_attempt_count >= self._config.max_attempts:
                    await self._set_no_compress(item_id, item_type)
                return False
        
        return await self._update_item_with_lock(
            item_id, item_type, item.version,
            compressed, strategy_name, metadata
        )
    
    async def _update_item_with_lock(
        self,
        item_id: str,
        item_type: str,
        expected_version: int,
        compressed: str,
        strategy: str,
        metadata: CompressionMetadata
    ) -> bool:
        """Update item with optimistic lock."""
        new_version = expected_version + 1
        original_length = len(compressed)
        
        updated = await self._db.execute("""
            UPDATE {table}
            SET content = ?,
                compressed = true,
                compression_type = ?,
                compression_metadata = ?,
                original_length = ?,
                compressed_length = ?,
                semantic_similarity = ?,
                version = ?,
                last_compressed_at = ?
            WHERE id = ? AND version = ?
        """, compressed, strategy, json.dumps(metadata.to_dict()),
           len(compressed), original_length, metadata.semantic_similarity or 0.85,
           new_version, time.time(), item_id, expected_version)
        
        return updated > 0
    
    async def decompress_item(
        self,
        item_id: str,
        item_type: str
    ) -> str | None:
        """Decompress an item with LRU cache."""
        cache_key = f"{item_type}:{item_id}"
        
        if cache_key in self._decompression_cache:
            return self._decompression_cache[cache_key]
        
        item = await self._get_item(item_id, item_type)
        if not item or not item.compressed:
            return None
        
        try:
            content = await self._decompress(item, item_type)
            self._decompression_cache[cache_key] = content
            return content
        except Exception:
            return await self._fallback_decompress(item_id, item_type)
    
    async def _fallback_decompress(
        self,
        item_id: str,
        item_type: str
    ) -> str | None:
        """Fallback to original_blobs table."""
        blob = await self._get_original_blob(item_id)
        if blob:
            return blob.content
        return None
    
    async def mark_no_compress(self, item_id: str, item_type: str) -> None:
        """Mark item as not compressible."""
        await self._db.execute("""
            UPDATE {table}
            SET no_compress = true
            WHERE id = ?
        """, item_id)
    
    async def report_compression_issue(
        self,
        item_id: str,
        reason: str
    ) -> None:
        """Handle agent feedback - rollback and mark no_compress."""
        item = await self._get_item(item_id, item_type=None)
        if not item:
            return
        
        original = await self._fallback_decompress(item_id, item.item_type)
        if not original:
            logger.error(f"Cannot rollback item {item_id}: no original found")
            return
        
        await self._db.execute("""
            UPDATE {table}
            SET content = ?,
                compressed = false,
                no_compress = true,
                version = version + 1
            WHERE id = ?
        """, original, item_id)
        
        self._decompression_cache.pop(f"{item.item_type}:{item_id}", None)
        logger.info(f"Rolled back compression for {item_id}: {reason}")
    
    async def get_stats(self) -> dict:
        """Get compression statistics."""
        return {
            "compression_ratio": self._compression_ratio,
            "semantic_similarity_avg": self._similarity_avg,
            "worker_latency_ms": self._worker_latency,
            "items_compressed": self._items_compressed,
            "items_failed": self._items_failed,
            "items_skipped_version_mismatch": self._items_skipped,
            "decompression_cache_hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses),
            "soft_deleted_count": self._soft_deleted
        }
```

---

## 5. Background Worker

### 5.1 Incremental Scan

```python
class CompressionWorker:
    """Background worker for compression tasks."""
    
    def __init__(self, engine: CompressionEngine, config: WorkerConfig):
        self._engine = engine
        self._config = config
        self._rate_limiter = RateLimiter(
            items_per_second=config.rate_limit_items_per_second,
            burst_size=config.batch_size
        )
    
    async def run(self, interval_seconds: int = 3600) -> None:
        """Run the compression worker loop."""
        while not self._shutdown:
            try:
                await self._scan_and_compress()
            except Exception as e:
                logger.error(f"Worker error: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    async def _scan_and_compress(self) -> None:
        """Scan for compressible items and process them."""
        cutoff_time = time.time() - (self._config.min_age_days * 86400)
        
        items = await self._get_compressible_items(
            cutoff_time=cutoff_time,
            batch_size=self._config.batch_size
        )
        
        for item in items:
            if self._shutdown:
                break
            
            if not await self._rate_limiter.try_acquire():
                await asyncio.sleep(0.1)
                continue
            
            if not await self._engine.compress_item(item.id, item.type):
                if self._engine.last_error == "VERSION_MISMATCH":
                    self._items_skipped += 1
                    logger.debug(f"Skipped {item.id}: version changed")
                else:
                    self._items_failed += 1
    
    async def _get_compressible_items(
        self,
        cutoff_time: float,
        batch_size: int
    ) -> list[MemoryItem]:
        """Get items eligible for compression."""
        return await self._db.execute("""
            SELECT * FROM memory
            WHERE compressed = false
              AND no_compress = false
              AND deleted = false
              AND last_updated < ?
              AND (last_compressed_at IS NULL
                   OR last_compressed_at < last_updated)
            ORDER BY last_updated ASC
            LIMIT ?
        """, cutoff_time, batch_size)
```

### 5.2 Optimistic Lock Implementation

```python
async def compress_item_with_version(
    engine: CompressionEngine,
    item_id: str,
    version: int,
    new_content: str
) -> bool:
    """Compress item with optimistic lock."""
    
    result = await engine._db.execute("""
        UPDATE memory
        SET content = ?,
            compressed = true,
            version = version + 1,
            last_compressed_at = ?
        WHERE id = ? AND version = ?
    """, new_content, time.time(), item_id, version)
    
    if result.rowcount == 0:
        logger.warning(f"Version mismatch for {item_id}: expected {version}")
        return False
    
    return True
```

---

## 6. Decompression

### 6.1 Decompression Cache

```python
class DecompressionCache:
    """LRU cache for decompressed content."""
    
    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[str, float]] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> str | None:
        """Get from cache if not expired."""
        if key in self._cache:
            content, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._hits += 1
                return content
            else:
                del self._cache[key]
        
        self._misses += 1
        return None
    
    def set(self, key: str, content: str) -> None:
        """Set in cache with LRU eviction."""
        if len(self._cache) >= self._maxsize:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]
        
        self._cache[key] = (content, time.time())
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
```

### 6.2 Fallback Strategy

```python
async def fallback_decompress(
    item_id: str,
    original_hash: str
) -> str | None:
    """Fallback decompress using original blob storage."""
    
    blob = await db.query("""
        SELECT content FROM original_blobs
        WHERE item_id = ? OR content_hash = ?
    """, item_id, original_hash)
    
    if blob:
        return blob.content
    
    logger.error(f"No fallback found for compressed item {item_id}")
    return None
```

---

## 7. Soft Delete & Permanent Purge

### 7.1 Soft Delete

```python
class SoftDeletePruner:
    """Soft delete pruner - marks items deleted, moves to cold storage."""
    
    async def prune(self, engine: CompressionEngine) -> int:
        """Soft delete old compressed items."""
        prune_after = time.time() - (engine._config.prune_after_days * 86400)
        
        items = await engine._db.execute("""
            SELECT id, content, type FROM memory
            WHERE compressed = true
              AND deleted = false
              AND last_accessed < ?
              AND (last_accessed < ? OR access_count < ?)
            LIMIT 100
        """, prune_after, prune_after, engine._config.min_access_count)
        
        deleted = 0
        for item in items:
            await self._soft_delete(engine, item)
            deleted += 1
        
        return deleted
    
    async def _soft_delete(self, engine: CompressionEngine, item) -> None:
        """Mark item as soft deleted and optionally move to cold storage."""
        
        if engine._config.cold_storage_enabled:
            await engine._db.execute("""
                INSERT INTO original_blobs (item_id, content, content_hash, deleted_at)
                VALUES (?, ?, ?, ?)
            """, item.id, item.content, item.original_content_hash, time.time())
        
        await engine._db.execute("""
            UPDATE memory
            SET deleted = true,
                deleted_at = ?,
                cold_storage_ref = ?
            WHERE id = ?
        """, time.time(), f"cold://{item.id}", item.id)
```

### 7.2 Permanent Purge

```python
class PermanentPurgeJob:
    """Permanently delete soft-deleted items after retention period."""
    
    async def purge(self, engine: CompressionEngine) -> int:
        """Permanently delete items past retention period."""
        purge_after = time.time() - (engine._config.permanent_delete_days * 86400)
        
        result = await engine._db.execute("""
            DELETE FROM memory
            WHERE deleted = true
              AND deleted_at < ?
        """, purge_after)
        
        await engine._db.execute("""
            DELETE FROM original_blobs
            WHERE deleted_at < ?
        """, purge_after)
        
        return result.rowcount
```

---

## 8. Database Schema

### 8.1 Extended memory table

```sql
CREATE TABLE memory (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT,
    
    -- Compression fields
    compressed BOOLEAN DEFAULT FALSE,
    compression_type TEXT,
    compression_metadata JSON,
    original_length INTEGER,
    compressed_length INTEGER,
    semantic_similarity REAL,
    last_compressed_at INTEGER,
    compression_attempt_count INTEGER DEFAULT 0,
    no_compress BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE,
    deleted_at INTEGER,
    cold_storage_ref TEXT,
    
    -- Standard fields
    session_id TEXT,
    metadata JSON,
    created_at INTEGER,
    chunk_index INTEGER,
    chunk_total INTEGER,
    parent_id TEXT,
    
    -- Versioning
    last_updated INTEGER,
    version INTEGER DEFAULT 1,
    original_content_hash TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed INTEGER
);

CREATE INDEX idx_memory_compress ON memory(compressed, deleted, last_updated);
CREATE INDEX idx_memory_version ON memory(version);
CREATE INDEX idx_memory_deleted ON memory(deleted, deleted_at);
```

### 8.2 tool_cache table (similar)

```sql
CREATE TABLE tool_cache (
    id TEXT PRIMARY KEY,
    cache_key TEXT,
    content TEXT,
    
    -- Compression fields (same as memory)
    compressed BOOLEAN DEFAULT FALSE,
    compression_type TEXT,
    compression_metadata JSON,
    original_length INTEGER,
    compressed_length INTEGER,
    semantic_similarity REAL,
    last_compressed_at INTEGER,
    compression_attempt_count INTEGER DEFAULT 0,
    no_compress BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE,
    deleted_at INTEGER,
    cold_storage_ref TEXT,
    
    -- Standard fields
    tool_name TEXT,
    args_hash TEXT,
    created_at INTEGER,
    expires_at INTEGER,
    access_count INTEGER DEFAULT 0,
    last_accessed INTEGER,
    
    -- Versioning
    last_updated INTEGER,
    version INTEGER DEFAULT 1,
    original_content_hash TEXT
);
```

### 8.3 original_blobs table

```sql
CREATE TABLE original_blobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    item_type TEXT NOT NULL,
    compressed_at INTEGER,
    deleted_at INTEGER,
    
    UNIQUE(item_id, content_hash)
);

CREATE INDEX idx_blobs_hash ON original_blobs(content_hash);
CREATE INDEX idx_blobs_deleted ON original_blobs(deleted_at);
```

---

## 9. Configuration

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
  
  strategies:
    default: extractive
    
    truncation:
      max_chars: 2000
      keep_both_ends: true
    
    extractive:
      top_k_ratio: 0.3
      diversity_lambda: 0.5
    
    kv_compact:
      keep_fields_ratio: 0.5
    
    adaptive_prune:
      prune_after_days: 30
      min_access_count: 2
      soft_delete: true
      permanent_delete_days: 7
  
  quality:
    min_similarity: 0.85
    validate_before_commit: true
  
  decompression_cache:
    enabled: true
    maxsize: 1000
    ttl_seconds: 3600
  
  feedback:
    auto_disable_on_report: true
    rollback_and_mark_no_compress: true
  
  cold_storage:
    enabled: true
    threshold_days: 7
```

---

## 10. Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `compression_ratio` | gauge | original_length / compressed_length |
| `semantic_similarity_avg` | gauge | Average similarity after compression |
| `worker_latency_ms` | histogram | Worker scan + compress latency |
| `items_compressed` | counter | Total items compressed |
| `items_failed` | counter | Compression failures |
| `items_skipped_version_mismatch` | counter | Skipped due to version conflict |
| `decompression_cache_hit_rate` | gauge | LRU cache hit ratio |
| `soft_deleted_count` | counter | Items soft deleted |
| `permanent_purged_count` | counter | Items permanently deleted |

---

## 11. Test Plan

### 11.1 Unit Tests

- `test_truncation_compressor.py` - Truncation behavior
- `test_extractive_summarizer.py` - MMR selection, diversity
- `test_keyvalue_compactor.py` - Field importance scoring
- `test_adaptive_pruner.py` - Soft delete conditions
- `test_decompression_cache.py` - LRU, TTL, hit rate

### 11.2 Integration Tests

- `test_compression_integration.py` - Full compress/decompress cycle
- `test_optimistic_lock.py` - Version conflict handling
- `test_worker_batch.py` - Batch processing with rate limiting

### 11.3 Property-Based Tests (Hypothesis)

```python
from hypothesis import given, strategies as st, settings

@given(content=st.text(min_size=10, max_size=10000))
@settings(max_examples=100)
def test_idempotence(content: str):
    """compress(decompress(compress(data))) == compress(data)"""
    compressed = engine.compress(content)
    decompressed = engine.decompress(compressed)
    recompressed = engine.compress(decompressed)
    assert recompressed == compressed

@given(content=st.text(min_size=10, max_size=10000))
@settings(max_examples=100)
def test_decompress_always_possible(content: str):
    """After compress, decompress never raises exception."""
    compressed = engine.compress(content)
    result = engine.decompress(compressed)
    assert result is not None

@given(content=st.text(min_size=10, max_size=10000))
@settings(max_examples=100)
def test_similarity_preservation(content: str):
    """similarity(original, decompress(compress(original))) >= 0.85"""
    compressed = engine.compress(content)
    decompressed = engine.decompress(compressed)
    similarity = calculate_similarity(content, decompressed)
    assert similarity >= 0.85

def test_version_check():
    """If version changes during worker run, update is rejected."""
    # Simulate concurrent write
    item = get_item(item_id)
    item.version += 1
    save_item(item)
    
    # Worker tries to update with old version
    result = worker.compress_with_lock(item_id, item.version - 1, compressed)
    assert result == False  # Rejected
```

### 11.4 Chaos Tests

```python
@pytest.mark.asyncio
async def test_worker_kill_restart():
    """Kill worker mid-compression, restart; data remains consistent."""
    worker.start()
    await asyncio.sleep(0.5)
    worker.kill()  # Simulate crash
    await asyncio.sleep(0.5)
    worker.restart()
    
    # Verify no corruption
    item = get_item(test_item_id)
    assert item.version >= initial_version

@pytest.mark.asyncio
async def test_concurrent_writes():
    """Run worker concurrently with writes; no data loss."""
    async def writer():
        for i in range(100):
            await write_item(f"item_{i}")
            await asyncio.sleep(0.01)
    
    async def worker_run():
        worker.start()
        await asyncio.sleep(1)
    
    await asyncio.gather(writer(), worker_run())
    
    # Verify all items exist and have valid versions
    for i in range(100):
        item = get_item(f"item_{i}")
        assert item is not None
```

### 11.5 Coverage Target

| Module | Target Coverage |
|--------|-----------------|
| compression strategies | ≥ 85% |
| worker | ≥ 85% |
| decompression | ≥ 85% |
| pruner | ≥ 85% |
| Overall | ≥ 85% |

---

## 12. Definition of Done

All criteria must pass:

- [x] Worker uses optimistic lock, no overwrites
- [x] Worker only compresses items with last_updated < now - min_age_days
- [x] Decompression has LRU cache
- [x] Soft delete + permanent purge implemented
- [x] Metadata sufficient for decompression (with hash fallback)
- [x] Property-based tests pass (idempotence, decompress always possible, similarity)
- [x] Chaos tests pass
- [x] Coverage ≥ 85%
- [x] Agent can report issues and rollback
- [x] Metrics fully implemented

---

## 13. File Structure

```
src/core/memory/
├── semantic_memory.py         # Phase 4A core
├── compression/
│   ├── __init__.py
│   ├── types.py              # CompressionMetadata, CompressionResult
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py           # CompressionStrategy protocol
│   │   ├── truncation.py     # TruncationCompressor
│   │   ├── extractive.py     # ExtractiveSummarizer (MMR)
│   │   ├── keyvalue.py       # KeyValueCompactor
│   │   └── adaptive.py       # AdaptivePruner
│   ├── engine.py             # CompressionEngine
│   ├── worker.py             # Background worker
│   ├── decompression.py       # Decompression with LRU cache
│   ├── pruner.py             # Soft delete + permanent purge
│   ├── cache.py              # DecompressionCache (LRU)
│   └── config.py             # CompressionConfig
├── tool_cache/               # Phase 4B (existing)
└── chunker.py
    deduplication.py

tests/unit/
├── compression/
│   ├── test_truncation.py
│   ├── test_extractive.py
│   ├── test_keyvalue.py
│   ├── test_adaptive.py
│   └── test_cache.py
├── test_compression_engine.py
└── test_worker.py

tests/integration/
├── test_compression_integration.py
└── test_optimistic_lock.py

tests/property/
└── test_compression_properties.py

tests/chaos/
└── test_worker_chaos.py

---

## 14. Production Fixes (v4.1)

This section documents fixes applied after production review to address 9 identified weaknesses.

### Fix #1: Auto-update last_updated on write

**Problem**: The `last_updated` field was not being automatically updated on writes, causing worker to not compress items.

**Solution**: Added SQL triggers to auto-update `last_updated` and increment `version`:

```sql
-- Trigger to auto-update last_updated and version on INSERT/UPDATE
CREATE TRIGGER IF NOT EXISTS memory_on_write
    BEFORE UPDATE ON memory
    WHEN OLD.content != NEW.content OR OLD.version = NEW.version
BEGIN
    SELECT NEW.last_updated = strftime('%s', 'now');
    SELECT NEW.version = OLD.version + 1;
END;
```

**Files modified**: `compression_schema.sql`

### Fix #2: Composite index for worker queries

**Problem**: Worker queries scanning for compressible items were slow on large tables.

**Solution**: Added composite index `(compressed, no_compress, deleted, last_updated)`:

```sql
CREATE INDEX IF NOT EXISTS idx_memory_compress_workflow 
    ON memory(compressed, no_compress, deleted, last_updated);
```

**Files modified**: `compression_schema.sql`

### Fix #3: Reset compression_attempt_count on success

**Problem**: `compression_attempt_count` was not reset after successful compression.

**Solution**: Added `compression_attempt_count = 0` in the UPDATE query:

```sql
UPDATE {table}
SET content = ?,
    ...
    compression_attempt_count = 0
WHERE id = ? AND version = ?
```

**Files modified**: `engine.py`

### Fix #4: Auto-save original before compress

**Problem**: Fallback decompression relied on `original_blobs` table but it wasn't automatically populated before compression.

**Solution**: Save original content to `original_blobs` before compression:

```python
async def _update_item_with_lock(self, item, ...):
    # Auto-save original to original_blobs before compress
    original_hash = hashlib.sha256(item.content.encode()).hexdigest()
    await self._save_original_blob(
        item_id=item_id,
        item_type=item_type,
        content=item.content,
        content_hash=original_hash,
    )
```

**Files modified**: `engine.py`

### Fix #5: Retry/backoff for version mismatch

**Problem**: Items with repeated version mismatches would be skipped indefinitely.

**Solution**: Auto-disable compression after threshold (max_attempts * 2):

```python
if mismatch_count >= self._config.worker.max_attempts * 2:
    await self._set_no_compress(item_id, item_type)
    logger.warning(f"Auto-disabled compression for {item_id} after repeated version mismatches")
```

**Files modified**: `engine.py`

### Fix #6: Invalidate decompression cache on writes

**Problem**: Cache could return stale data after item was overwritten.

**Solution**: 
1. Reduced default TTL from 3600s to 300s
2. `DecompressionCache.invalidate()` is called on `mark_no_compress()` and `report_compression_issue()`

**Files modified**: `config.py`, `engine.py`

### Fix #7: Distributed lock for multi-instance workers

**Problem**: Multiple worker instances would compete for the same items.

**Solution**: Added `DistributedLock` interface and `InMemoryDistributedLock`:

```python
class DistributedLock:
    async def acquire(self, key: str, timeout: float = 5.0) -> bool: ...
    async def release(self, key: str) -> None: ...

class InMemoryDistributedLock(DistributedLock): ...
```

Worker acquires lock before scanning:

```python
async def _scan_and_compress(self) -> None:
    lock_key = "compression_worker_lock"
    if not await self._distributed_lock.acquire(lock_key, timeout=5.0):
        logger.info("Another worker instance is running, skipping this cycle")
        return
    try:
        ...
    finally:
        await self._distributed_lock.release(lock_key)
```

**Files modified**: `engine.py`, `worker.py`

### Fix #8: JSON generators for property tests

**Problem**: Property-based tests lacked diverse JSON data generators.

**Solution**: Added Hypothesis JSON generators:

```python
# JSON generators for property-based tests
json_generator = st.recursive(
    st.booleans() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=100),
    lambda children: st.lists(children, max_size=20) | st.dictionaries(st.text(max_size=50), children, max_size=20),
    max_leaves=10
)
```

Added tests:
- `test_keyvalue_json_idempotence`
- `test_keyvalue_json_decompress_always_works`
- `test_keyvalue_preserves_structure`

**Files modified**: `tests/property/test_compression_properties.py`

### Fix #9: Dry-run mode for worker

**Problem**: Cannot evaluate compression impact before applying changes.

**Solution**: Added `dry_run` config option and reporting:

```python
@dataclass
class WorkerConfig:
    dry_run: bool = False

# Worker logs without committing
if self._config.dry_run:
    await self._dry_run_report(items)
    return
```

Operator can view reports via `get_dry_run_reports()`.

**Files modified**: `config.py`, `worker.py`

---

## 15. Test Coverage Summary

| Category | Tests | Status |
|----------|-------|--------|
| Unit Tests | 86 | PASS |
| Integration Tests | 7 | PASS |
| Property Tests | 16 | PASS |
| Chaos Tests | 10 | PASS |
| **Total** | **123** | **PASS** |

---

## 16. Production Fixes v4.2 (Post-Production Review Round 2)

This section documents additional fixes applied after second round of production review.

### Fix #1: Checksum validation after decompression

**Problem**: Decompression could return corrupted data without detection.

**Solution**: Verify SHA256 hash after decompression:

```python
# In decompress()
if metadata.original_hash:
    result_hash = hashlib.sha256(result.encode()).hexdigest()
    if result_hash != metadata.original_hash:
        raise DecompressionError(f"Checksum mismatch for {item_id}")
```

**Files modified**: `decompression.py`

### Fix #2: Original blobs retention policy

**Problem**: `original_blobs` table could grow indefinitely.

**Solution**: Added retention policy and `keep_latest_blob_only` option:

```yaml
cold_storage:
  blob_retention_days: 30
  keep_latest_blob_only: true
```

Added `purge_old_blobs()` method to `PermanentPurgeJob`.

**Files modified**: `config.py`, `pruner.py`

### Fix #3: Circuit breaker for embedding service

**Problem**: Embedding service failures could cause worker backlog.

**Solution**: Added `CircuitBreaker` class:

```python
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
```

**Files modified**: `engine.py`

### Fix #4: Protection against extremely large items

**Problem**: Very large items (>100MB) could cause OOM.

**Solution**: Added size limits:

```python
@dataclass
class LimitsConfig:
    max_item_size_mb: int = 10
    max_embedding_chars: int = 50000
```

**Files modified**: `config.py`, `engine.py`

### Fix #5: Metadata versioning

**Problem**: Strategy changes could break backward compatibility.

**Solution**: Added `strategy_version` field:

```python
@dataclass
class CompressionMetadata:
    strategy_version: str = "1.0"
```

**Files modified**: `types.py`

### Fix #6: Compression debt metrics

**Problem**: No visibility into potential storage savings.

**Solution**: Added `CompressionDebtCalculator`:

```python
class CompressionDebtCalculator:
    def update(self, uncompressed_bytes, compressed_bytes): ...
    def get_metrics(self) -> dict:
        return {
            "estimated_savings_bytes": ...,
            "estimated_savings_mb": ...,
        }
```

**Files modified**: `engine.py`

### Fix #7: No-compress TTL

**Problem**: `no_compress=true` items become permanent dead state.

**Solution**: Added TTL-based re-evaluation:

```python
@dataclass
class NoCompressConfig:
    retry_after_hours: int = 24

# Check in _can_compress()
if item.no_compress_until and time.time() < item.no_compress_until:
    return False
```

**Files modified**: `config.py`, `engine.py`, `types.py`

### Fix #8: Backpressure tracking

**Problem**: No visibility into backlog growth.

**Solution**: Added `compression_backlog_depth` metric in stats.

**Files modified**: `engine.py`

---

## 17. Configuration Reference

```yaml
compression:
  enabled: true
  
  worker:
    interval_seconds: 3600
    batch_size: 50
    dry_run: false
  
  cold_storage:
    enabled: true
    blob_retention_days: 30
    keep_latest_blob_only: true
  
  circuit_breaker:
    enabled: false
    failure_threshold: 5
    recovery_timeout_seconds: 30
  
  limits:
    max_item_size_mb: 10
    max_embedding_chars: 50000
  
  no_compress:
    retry_after_hours: 24
```

configs/memory/
└── compression.yaml           # Compression configuration
```

---

## 18. Production Fixes v4.3 (Round 3)

### Fix #1: Checksum validation for lossless strategies only

**Problem**: Checksum validation fails for lossy compression (truncation, extractive).

**Solution**: Added `is_lossless` flag to metadata:

```python
@dataclass
class CompressionMetadata:
    is_lossless: bool = False  # Only validate hash for lossless strategies
```

Checksum validation only runs when `is_lossless=True`.

**Files modified**: `types.py`, `decompression.py`

### Fix #2: Removed problematic auto-update triggers

**Problem**: SQLite triggers with `SELECT NEW.x = ...` don't work reliably.

**Solution**: Removed `memory_on_write` and `tool_cache_on_write` triggers. Version and `last_updated` must be updated explicitly in application code.

**Files modified**: `compression_schema.sql`

### Fix #3: Enhanced property test generators

**Problem**: Tests lacked edge cases (nested JSON, huge keys, unicode, code).

**Solution**: Added diverse generators:

```python
huge_key_generator = st.dictionaries(
    st.text(min_size=500, max_size=2000),  # Huge keys
    st.text(max_size=100),
    max_size=5
)

code_like_generator = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz...{}[]();=+-*/<>!&|",
    min_size=10,
    max_size=500
)

nested_json_generator = st.recursive(...)
```

**Files modified**: `tests/property/test_compression_properties.py`

---

## 19. Production Fixes v4.4 (Round 4)

### Fix #1: Redis Distributed Lock

**Problem**: InMemoryDistributedLock only works in single instance.

**Solution**: Added `RedisDistributedLock` for production multi-instance deployments:

```python
class RedisDistributedLock(DistributedLock):
    """Redis-based distributed lock using SET NX EX."""
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        redis = await self._get_redis()
        acquired = await redis.set(full_key, "1", nx=True, ex=int(timeout))
        return acquired is True
```

**Files modified**: `engine.py`

### Fix #2: Cache Checksum Validation

**Problem**: Cache corruption not detected when reading from cache.

**Solution**: Store checksum with cache entries and verify on read:

```python
class DecompressionCache:
    def get(self, key: str) -> Optional[str]:
        content, timestamp, stored_checksum = self._cache[key]
        current_checksum = self._compute_checksum(content)
        if current_checksum != stored_checksum:
            del self._cache[key]
            self._corruption_detected += 1
            return None
```

**Files modified**: `cache.py`

### Fix #3: Large Item Strategy

**Problem**: Oversized items are skipped entirely.

**Solution**: Added configurable strategy:

```yaml
limits:
  large_item_strategy: "truncate"  # or "skip"
```

If truncate, content is cut to max_item_size_mb and compression continues.

**Files modified**: `config.py`, `engine.py`

---

## 20. Production Fixes v4.5 (Round 5)

### Fix #1: Redis Lock Fallback with Warning

**Problem**: If Redis is down, worker would fail to acquire lock.

**Solution**: Added `fallback_to_inmemory` config and warning when falling back:

```python
class RedisDistributedLock:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "compression_lock:",
        fallback_to_inmemory: bool = True,
    ):
        # Logs warning on first fallback
        if self._fallback and self._fallback_count == 1:
            logger.warning("Redis unavailable, falling back to in-memory lock. "
                         "Multi-instance safety NOT guaranteed.")
```

**Files modified**: `engine.py`

### Fix #2: Cache Corruption Metric Exposed

**Problem**: `corruption_detected` counter not exposed via property.

**Solution**: Added public property:

```python
@property
def corruption_detected(self) -> int:
    """Get number of cache corruption events detected."""
    return self._corruption_detected
```

**Files modified**: `cache.py`

### Fix #3: JSON/XML Truncation Warning

**Problem**: Truncating JSON/XML may break structure silently.

**Solution**: Added warning log when truncating structured content:

```python
is_structured = (
    stripped.startswith('{') or 
    stripped.startswith('[') or 
    stripped.startswith('<')
)
if is_structured:
    logger.warning(f"Large item {item_id} truncated in-place. "
                  f"Content may be structurally invalid.")
```

**Files modified**: `engine.py`

---

## 21. Known Limitations (Future Improvements)

The following items are documented but not yet implemented:

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 1 | Atomic transactions (save_blob + compress) | High | Requires DB transaction support |
| 2 | Per-type quality thresholds | Medium | Global 0.85 threshold for all types |
| 3 | Background integrity scanner | Medium | Verify random sample for corruption |
| 4 | Compression history audit table | Low | Track strategy changes over time |
| 5 | Exponential backoff for version mismatch | Medium | Prevents worker starvation |
| 6 | Chunked embedding batch | Medium | For very large documents |
| 7 | Dry-run report persistence | Low | Store reports for comparison |
