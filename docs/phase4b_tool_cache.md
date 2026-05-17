# Phase 4B – Tool Cache System Specification (v14)

**Status**: Implementation Phase
**Date**: 2026-05-17
**Version**: v14 (Production Ready - All Risks Addressed)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [State Machine](#3-state-machine)
4. [Cache Key Specification](#4-cache-key-specification)
5. [Single-Flight Coordinator](#5-single-flight-coordinator)
6. [SWR Engine](#6-swr-engine)
7. [Tool-Level Fairness Rate Limiter](#7-tool-level-fairness-rate-limiter)
8. [Adaptive Threshold Engine](#8-adaptive-threshold-engine)
9. [LRU + Pinning](#9-lru--pinning)
10. [Adaptive TTL](#10-adaptive-ttl)
11. [Warm-Up](#11-warm-up)
12. [Cold-Start Amplification Control](#12-cold-start-amplification-control)
13. [Poison Validation](#13-poison-validation)
14. [Persistence](#14-persistence)
15. [Persistence Replay Safety](#15-persistence-replay-safety)
16. [Memory Fragmentation Strategy](#16-memory-fragmentation-strategy)
17. [Metrics Engine](#17-metrics-engine)
18. [Causality Correlation Metrics](#18-causality-correlation-metrics)
19. [Cluster Consistency Layer](#19-cluster-consistency-layer)
20. [ReconciliationEngine Conflict Model](#20-reconciliationengine-conflict-model)
21. [Backpressure Propagation Model](#21-backpressure-propagation-model)
22. [Response Contract](#22-response-contract)
23. [Failure Safety](#23-failure-safety)
24. [Correctness Invariants](#24-correctness-invariants)
25. [Definition of Done](#25-definition-of-done)
26. [File Structure](#26-file-structure)
27. [Implementation Notes](#27-implementation-notes)
28. [Remaining Risks & Mitigations](#28-remaining-risks--mitigations)
29. [Minor Issues & Refinements](#29-minor-issues--refinements)

---

## 1. System Overview

### 1.1 Purpose

Build a production-grade Tool Cache Layer with Kafka-level rigor ensuring:

- **Correctness guarantees**: Linearizable behavior per cache key
- **Resilience guarantees**: Graceful degradation under overload
- **Performance guarantees**: O(1) get path, bounded concurrency
- **Cluster guarantees**: Consistent behavior across distributed nodes

### 1.2 Core Design Principle

> Cache is a **non-authoritative optimization layer**, not a correctness dependency.

- Cache failure = fallback to tool execution
- Cache corruption = automatic bypass (self-healing)
- Cache unavailability = system continues normally
- Cluster failure = local fallback, eventual consistency

### 1.3 Deployment Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `standalone` | Single node, local cache | Development |
| `cluster` | Multi-node with coordination | Production K8s |

---

## 2. Architecture

### 2.1 Component Hierarchy

```
Agent
  ↓
ToolExecutor
  ↓
ToolCache (single logical subsystem)

ToolCache
 ├── KeyStateMachine (linearizable per-key FSM)
 ├── StrictNormalizer (lossless canonicalization)
 ├── KeyGenerator (versioned SHA256)
 ├── SingleFlightCoordinator (bounded, cancellable)
 ├── SWREngine (state-driven, no duplicate refresh)
 ├── ToolRateLimiter (global + per-tool + per-key fairness pool)
 ├── AdaptiveThresholdEngine (time-decayed EMA + percentile)
 ├── LoadSheddingController (DEGRADED lifecycle manager)
 ├── LRUStore (byte+entry bounded, lock-free read path)
 ├── PinManager (dual constraint + priority eviction rules)
 ├── AdaptiveTTLEngine (time-aware EMA bounded)
 ├── ProgressiveWarmupManager (gradual readiness, not binary)
 ├── PoisonValidationEngine (Pydantic or strict schema)
 ├── PersistentStore (append-only async log)
 ├── WriteBackQueue (non-blocking, drop/spill only)
 ├── MetricsEngine (lock-free counters + sampling aggregator)
 ├── CausalityTracer (per-tool tracing + anomaly detection)
 ├── ReconciliationEngine (vector-clock conflict resolver)
 ├── BackpressureManager (propagation to upstream)
 ├── FragmentationManager (slab allocator + defrag)
 └── ClusterCoordinator (partitioning + distributed lock)
```

---

## 3. State Machine

### 3.1 States

| State | Description |
|-------|-------------|
| `MISS` | Key not in cache |
| `LOADING` | Initial load in progress |
| `FRESH` | Valid data, within TTL |
| `STALE` | TTL expired, refresh may be triggered |
| `REFRESHING` | Refresh in progress |
| `DEGRADED` | System-wide overload mode |
| `PARTIAL` | Cluster: entry exists but being synced |

### 3.2 Transition Priority Rule

**CRITICAL**: When multiple transitions are possible, apply this priority:

```
DEGRADED > REFRESHING > PARTIAL > STALE > FRESH > LOADING > MISS
```

### 3.3 Deterministic Transition Table

| Current State | Event | Next State |
|--------------|-------|------------|
| `MISS` | first request | `LOADING` |
| `LOADING` | success | `FRESH` |
| `LOADING` | failure | `MISS` (or `COOLDOWN` if threshold exceeded) |
| `LOADING` | remote update | `PARTIAL` |
| `FRESH` | TTL expired | `STALE` |
| `STALE` | refresh triggered | `REFRESHING` |
| `REFRESHING` | success | `FRESH` |
| `REFRESHING` | failure | `STALE` |
| `PARTIAL` | sync complete | `FRESH` |
| `ANY` | overload detected | `DEGRADED` |
| `DEGRADED` | recovery condition met | `STALE` |

### 3.4 DEGRADED Lifecycle

**Enter DEGRADED when ANY of:**
- `memory_pressure P95 > threshold`
- `pending_keys P95 > threshold`
- `refresh_queue_saturation > 90%`
- `fragmentation_ratio > 40%`
- `backpressure_signal severity >= 0.8`

**Exit DEGRADED when ALL true for 3 consecutive windows:**
- `memory_pressure < threshold * 0.8`
- `pending_keys < threshold * 0.8`
- `error_rate < 5%`
- `fragmentation_ratio < 30%`

---

## 4. Cache Key Specification

### 4.1 Canonical Key Structure

```json
{
    "tool": "tool_name",
    "version": "1.0.0",
    "args": { "strict_normalized_args": "value" }
}
```

### 4.2 Key Generation

```python
canonical = {
    "tool": tool_name,
    "version": tool_version,
    "args": strict_normalized_args
}
key = SHA256(JSON_SORTED(canonical))
```

### 4.3 Strict Normalization Rules

**Allowed transformations:**
- Whitespace trim
- Deterministic dict sort
- Optional case-fold (config gated)

**STRICTLY PROHIBITED:**
- Semantic transformation
- Unit conversion
- Timezone conversion
- Locale parsing

### 4.4 Cluster Partitioning

```python
def get_partition(key: str, num_partitions: int) -> int:
    """Consistent hashing for key distribution."""
    return hash(key) % num_partitions

def get_owner_node(key: str, cluster_config: ClusterConfig) -> str:
    """Determine which node owns this key."""
    partition = get_partition(key, cluster_config.num_partitions)
    return cluster_config.partition_map[partition]
```

---

## 5. Single-Flight Coordinator

### 5.1 Guarantees

- Only **1 active execution** per key at any time
- Bounded lifecycle: `timeout = 30s` default
- `max_pending_keys = N` (configurable)

### 5.2 Cluster Single-Flight

```python
async def store_with_cluster_lock(key: str, value: Any) -> bool:
    """Single-flight with distributed coordination."""
    lock_key = f"lock:{key}"
    
    if is_cluster_mode:
        # Distributed lock via Redis
        lock_acquired = await redis.set(lock_key, node_id, nx=True, ex=5)
        
        if not lock_acquired:
            await wait_for_result(key, timeout=30)
            return True  # Treat as dedup
    else:
        # Local lock
        lock_acquired = await local_lock.acquire(key, timeout=0.1)
        
        if not lock_acquired:
            await wait_for_result(key, timeout=30)
            return True
    
    try:
        return await do_store(key, value)
    finally:
        if is_cluster_mode:
            await redis.delete(lock_key)
        else:
            await local_lock.release(key)
```

### 5.3 Failure Model

| Failure Count | Behavior |
|---------------|----------|
| 1–3 | Normal retry |
| 4–10 | Exponential backoff |
| >10 | Cooldown (5 min freeze per key) |

### 5.4 Key Rule

> Keys in cooldown do **NOT** consume rate limiter tokens.

---

## 6. SWR Engine

### 6.1 Rules

| State | Behavior |
|-------|----------|
| `FRESH` | Return immediately |
| `STALE` | Return stale, trigger exactly 1 refresh per key |
| `REFRESHING` | No duplicate refresh allowed |

### 6.2 Anti-Dogpile Rule

```python
if now > 0.9 * expires_at:
    refresh_probability = 10%
# BUT must pass tool-rate limiter
# BUT must pass per-key lock
```

### 6.3 Cluster Anti-Dogpile

```python
async def trigger_refresh_with_coordinator(key: str):
    """Trigger refresh with cluster-wide deduplication."""
    
    # Check local state first
    if key_state == REFRESHING:
        return  # Already refreshing locally
    
    if is_cluster_mode:
        # Check cluster-wide refresh status
        refresh_key = f"refreshing:{key}"
        is_refreshing = await redis.get(refresh_key)
        
        if is_refreshing:
            return  # Another node is refreshing
        
        # Acquire refresh lock
        await redis.set(refresh_key, node_id, ex=30)
    
    try:
        await do_refresh(key)
    finally:
        if is_cluster_mode:
            await redis.delete(refresh_key)
```

---

## 7. Tool-Level Fairness Rate Limiter

### 7.1 Hierarchy

```
Global bucket
    ↓
Per-tool bucket
    ↓
Per-key fair queue
```

### 7.2 Scheduling Rule

- Each tool uses: **Weighted token bucket + round-robin across keys**
- **Guarantee**: No single key can dominate tool capacity

### 7.3 Token Bucket Implementation

```python
class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
    
    async def acquire(self, tokens: int = 1) -> bool:
        await self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    async def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
```

---

## 8. Adaptive Threshold Engine

### 8.1 Control Metrics

- `EMA(memory_pressure, time-decayed)`
- `P95(pending_keys, rolling window)`
- `EMA(fragmentation_ratio, time-decayed)`

### 8.2 Learning Modes

| Mode | Behavior |
|------|----------|
| Soft protection | `threshold * 1.5` |
| Hard mode | No relaxation |

### 8.3 Key Rule

> Thresholds must be **time-aware** (decay-adjusted), not static averages.

---

## 9. LRU + Pinning

### 9.1 Constraints

- `max_entries`
- `max_memory_bytes`
- `max_pinned_entries`
- `max_pinned_memory_bytes`

### 9.2 Eviction Order

1. Non-pinned LRU (first priority)
2. Pinned LRU (only if necessary)

### 9.3 Invariant

> **Pinned entries are NOT exempt from eviction under memory pressure.**

---

## 10. Adaptive TTL

### 10.1 Formula

```python
score = EMA(hit_rate, time_decay=True)
ttl_multiplier = min(1 + score, 2.0)
```

### 10.2 Constraints

- TTL cannot grow beyond **2× base**
- Score decays with inactivity time

---

## 11. Warm-Up

### 11.1 Atomic Specification

- Runs **ONLY before traffic enablement**
- Must be fully completed before serving requests
- Uses `set_if_absent(key)` OR `acquire per-key lock`

### 11.2 Prohibited Actions

- Overwrite newer data
- Run concurrently with live traffic

---

## 12. Cold-Start Amplification Control

### 12.1 Problem

Binary warm-up ON/OFF causes traffic spike amplification on cold start.

```
Current (Binary):
    Time: 0 ───────────────►
    Readiness: 0 ──── 1
                 (jump)
    
    Traffic: ───────────────►
             ↑ spike on startup

Ideal (Gradual):
    Time: 0 ───────────────►
    Readiness: 0 ────── 0.5 ────── 1
                 (gradual ramp)
    
    Traffic: 0 ────── 50% ────── 100%
              ↑ gradual increase
```

### 12.2 Progressive Readiness States

```python
class ProgressiveWarmupState(Enum):
    INITIALIZING = "initializing"    # 0-20% - Shadow traffic only
    PARTIAL = "partial"              # 20-60% - 25% traffic
    SUBSTANTIAL = "substantial"      # 60-90% - 75% traffic
    READY = "ready"                 # 90-100% - Full traffic

@dataclass
class WarmupConfig:
    min_duration_seconds: float = 30.0      # Minimum warm-up time
    ramp_duration_seconds: float = 60.0     # Time to full readiness
    shadow_traffic_ratio: float = 0.05       # 5% traffic during init
    partial_traffic_ratio: float = 0.25       # 25% during partial
    metrics_polling_interval: float = 5.0    # Check every 5 seconds
```

### 12.3 Readiness Calculator

```python
class WarmupReadinessCalculator:
    def calculate_readiness(self, metrics: WarmupMetrics) -> tuple[float, ProgressiveWarmupState]:
        weights = {
            "cache": 0.3,
            "index": 0.3,
            "pool": 0.2,
            "embedding": 0.2,
        }
        
        readiness = (
            metrics.cache_populated_pct * weights["cache"] +
            metrics.index_ready_pct * weights["index"] +
            (1.0 if metrics.connection_pool_ready else 0.0) * weights["pool"] +
            (1.0 if metrics.embedding_service_ready else 0.0) * weights["embedding"]
        )
        
        state = self._readiness_to_state(readiness)
        return readiness, state
    
    def get_traffic_ratio(self, state: ProgressiveWarmupState) -> float:
        return {
            ProgressiveWarmupState.INITIALIZING: 0.0,
            ProgressiveWarmupState.PARTIAL: 0.25,
            ProgressiveWarmupState.SUBSTANTIAL: 0.75,
            ProgressiveWarmupState.READY: 1.0,
        }[state]
```

### 12.4 Shadow Traffic Warmup

```python
async def warmup_with_shadow_traffic():
    """Warm up cache using shadow traffic before accepting real requests."""
    calculator = WarmupReadinessCalculator()
    config = WarmupConfig()
    
    warmup_queries = await load_warmup_queries()
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        
        # Enforce minimum warm-up time
        if elapsed < config.min_duration_seconds:
            await asyncio.sleep(config.min_duration_seconds - elapsed)
        
        metrics = await collect_warmup_metrics()
        readiness, state = calculator.calculate_readiness(metrics)
        
        if elapsed >= config.min_duration_seconds and readiness >= 0.9:
            break
        
        traffic_ratio = calculator.get_traffic_ratio(state)
        
        if traffic_ratio > 0:
            sample_size = int(len(warmup_queries) * traffic_ratio)
            sampled = random.sample(warmup_queries, sample_size)
            
            for query in sampled:
                await memory.retrieve(query, shadow=True)
        
        await asyncio.sleep(config.metrics_polling_interval)
    
    return ProgressiveWarmupState.READY
```

### 12.5 Gradual Ramp-Up Controller

```python
class GradualRampUpController:
    def __init__(self, config: WarmupConfig):
        self.config = config
        self.current_traffic_ratio = 0.0
    
    def calculate_traffic_ratio(self, elapsed_seconds: float, readiness: float) -> float:
        time_ratio = min(1.0, elapsed_seconds / self.config.ramp_duration_seconds)
        readiness_ratio = readiness
        base_ratio = min(time_ratio, readiness_ratio)
        
        if base_ratio < 0.2:
            return 0.0
        elif base_ratio < 0.6:
            return self.config.partial_traffic_ratio
        elif base_ratio < 0.9:
            return 0.75
        else:
            return 1.0
    
    async def should_accept_request(self) -> tuple[bool, float]:
        if self.current_traffic_ratio >= 1.0:
            return True, 1.0
        
        accepted = random.random() < self.current_traffic_ratio
        return accepted, self.current_traffic_ratio
```

---

## 13. Poison Validation

### 13.1 Modes

- Pydantic schema validation, OR
- Custom validator function

### 13.2 Fail Behavior

```python
set() → (False, reason)
reason ∈ {
    NOT_CACHEABLE,
    VALIDATION_FAILED,
    SIZE_LIMIT_EXCEEDED,
    SERIALIZATION_ERROR
}
```

### 13.3 Rule

> **Never silently cache invalid data.**

---

## 14. Persistence

### 14.1 Model

- Append-only write log
- Eventual consistency only
- Schema versioning for migration safety

### 14.2 Cleanup

- TTL > 7 days → GC
- Incremental scan only (partitioned)
- Tombstone markers for soft deletes

### 14.3 Write Queue Rules

- `drop` OR `spill_to_disk` ONLY
- **Never block**

### 14.4 Event Schema

```python
@dataclass
class CacheEvent:
    """Versioned cache event for replay safety."""
    version: int = CURRENT_SCHEMA_VERSION
    event_id: str                     # UUID for idempotency
    event_type: str                    # STORE, UPDATE, DELETE, INVALIDATE, TOMBSTONE
    key: str
    value: Optional[Any]
    metadata: dict
    vector_clock: dict[str, int]       # For conflict resolution
    timestamp: float
    sequence_number: int               # Monotonic sequence for total order
    checksum: str                     # SHA256 of payload
    previous_checksum: str             # Hash chain
    node_id: str
    is_tombstone: bool = False         # Soft delete marker

CURRENT_SCHEMA_VERSION = 3
```

---

## 15. Persistence Replay Safety

### 15.1 Schema Versioning & Migration

```python
class SchemaMigrator:
    """Handle schema version migrations for replay safety."""
    
    MIGRATIONS = {
        1: migrate_v1_to_v2,
        2: migrate_v2_to_v3,
    }
    
    @classmethod
    def migrate_if_needed(cls, event_data: dict) -> CacheEvent:
        version = event_data.get("version", 1)
        
        while version < CURRENT_SCHEMA_VERSION:
            migrator = cls.MIGRATIONS[version]
            event_data = migrator(event_data)
            version += 1
        
        return CacheEvent(**event_data)
    
    @staticmethod
    def migrate_v1_to_v2(data: dict) -> dict:
        """Add vector_clock field."""
        data["vector_clock"] = {"default": 1}
        data["version"] = 2
        return data
    
    @staticmethod
    def migrate_v2_to_v3(data: dict) -> dict:
        """Add tombstone support."""
        data["is_tombstone"] = data.get("event_type") == "DELETE"
        data["version"] = 3
        return data
```

### 15.2 Idempotency Key

```python
class IdempotencyStore:
    """Store processed event IDs for replay safety."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.processed_prefix = "idempotency:"
        self.ttl_hours = 24
    
    async def is_processed(self, event_id: str) -> bool:
        return await self.redis.exists(f"{self.processed_prefix}{event_id}")
    
    async def mark_processed(self, event_id: str):
        await self.redis.set(
            f"{self.processed_prefix}{event_id}",
            "1",
            ex=self.ttl_hours * 3600
        )
    
    async def process_event(self, event: CacheEvent) -> bool:
        if await self.is_processed(event.event_id):
            return False
        
        await self.mark_processed(event.event_id)
        await self.apply_event(event)
        return True
```

### 15.3 Corruption Detection

```python
class CorruptionDetector:
    """Detect corruption in persistence layer."""
    
    @staticmethod
    def verify_checksum(event: CacheEvent) -> bool:
        expected = event.checksum
        actual = CorruptionDetector.calculate_checksum(event)
        return expected == actual
    
    @staticmethod
    def calculate_checksum(event: CacheEvent) -> str:
        payload = f"{event.event_id}|{event.event_type}|{event.key}|{json.dumps(event.value)}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    @staticmethod
    def verify_hash_chain(events: list[CacheEvent]) -> bool:
        """Verify hash chain integrity."""
        previous_checksum = "GENESIS"
        
        for event in events:
            if event.previous_checksum != previous_checksum:
                return False
            previous_checksum = event.checksum
        
        return True
    
    async def full_audit(self, events: list[CacheEvent]) -> AuditResult:
        issues = []
        
        for i, event in enumerate(events):
            if not self.verify_checksum(event):
                issues.append(AuditIssue(
                    type="CHECKSUM_MISMATCH",
                    event_id=event.event_id,
                    position=i
                ))
            
            if i > 0 and events[i-1].sequence_number >= event.sequence_number:
                issues.append(AuditIssue(
                    type="SEQUENCE_VIOLATION",
                    event_id=event.event_id,
                    position=i
                ))
        
        if not self.verify_hash_chain(events):
            issues.append(AuditIssue(
                type="HASH_CHAIN_BROKEN",
                event_id=None,
                position=None
            ))
        
        return AuditResult(
            valid=len(issues) == 0,
            issues=issues,
            events_audited=len(events)
        )
```

### 15.4 Replay Ordering Guarantees

```python
class ReplayOrderGuarantee(Enum):
    CAUSAL = "causal"        # Respect vector clock ordering
    TOTAL = "total"          # Total order via sequence number
    EVENTUAL = "eventual"    # Eventually consistent

class SafeReplayer:
    def __init__(self, guarantee: ReplayOrderGuarantee):
        self.guarantee = guarantee
    
    async def replay_events(
        self,
        events: list[CacheEvent],
        idempotency_store: IdempotencyStore
    ) -> ReplayResult:
        if self.guarantee == ReplayOrderGuarantee.TOTAL:
            events = sorted(events, key=lambda e: e.sequence_number)
        elif self.guarantee == ReplayOrderGuarantee.CAUSAL:
            events = self._causal_sort(events)
        
        applied = 0
        skipped = 0
        errors = []
        
        for event in events:
            try:
                processed = await idempotency_store.process_event(event)
                if processed:
                    await self._apply_event(event)
                    applied += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(ReplayError(event.event_id, str(e)))
        
        return ReplayResult(applied=applied, skipped=skipped, errors=errors)
```

---

## 16. Memory Fragmentation Strategy

### 16.1 Problem

LRU + byte limit exists but fragmentation causes OOM despite "theoretical memory OK".

### 16.2 Fragmentation Metrics

```python
@dataclass
class MemoryFragmentationMetrics:
    total_allocated_bytes: int
    total_used_bytes: int
    largest_free_block: int
    num_free_blocks: int
    fragmentation_ratio: float  # 0.0 (perfect) to 1.0 (severe)
    
    @property
    def wasted_bytes(self) -> int:
        return self.total_allocated_bytes - self.total_used_bytes
    
    @property
    def is_fragmented(self) -> bool:
        return self.fragmentation_ratio > 0.3
```

### 16.3 Slab Allocator

```python
class SlabAllocator:
    """Slab allocation to reduce fragmentation."""
    
    SLAB_SIZES = [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]
    
    def __init__(self):
        self.slabs: dict[int, list[MemoryBlock]] = {size: [] for size in self.SLAB_SIZES}
        self.slab_usage: dict[int, int] = {size: 0 for size in self.SLAB_SIZES}
        self.max_slab_fill = 0.8
    
    def allocate(self, size: int) -> MemoryBlock:
        slab_size = self._best_fit_size(size)
        
        if self.slabs[slab_size]:
            block = self.slabs[slab_size].pop()
            block.in_use = True
            return block
        
        if self.slab_usage[slab_size] < self.max_slab_fill * SLAB_SIZE:
            return self._create_new_slab_block(slab_size)
        
        return self._direct_allocate(size)
    
    def _best_fit_size(self, size: int) -> int:
        for slab_size in self.SLAB_SIZES:
            if slab_size >= size:
                return slab_size
        return self.SLAB_SIZES[-1]
```

### 16.4 Large Object Eviction Penalty

```python
class LargeObjectEvictionPolicy:
    LARGE_OBJECT_THRESHOLD = 1024  # 1KB
    
    def calculate_eviction_score(
        self,
        entry: CacheEntry,
        lru_score: float,
        size_bytes: int
    ) -> float:
        score = lru_score
        
        if size_bytes > self.LARGE_OBJECT_THRESHOLD:
            size_ratio = size_bytes / self.LARGE_OBJECT_THRESHOLD
            penalty = min(0.3, 0.1 * (size_ratio - 1))
            score += penalty
        
        if entry.access_count > 10:
            score *= 0.8
        
        return score
    
    def should_evict_large_object(
        self,
        entry: CacheEntry,
        memory_pressure: float
    ) -> bool:
        if memory_pressure < 0.9:
            return False
        return True
```

### 16.5 Defragmentation Trigger

```python
class DefragmentationManager:
    def __init__(self):
        self.fragmentation_threshold = 0.4
        self.check_interval = 300
    
    async def should_defragment(self, metrics: MemoryFragmentationMetrics) -> bool:
        return (
            metrics.fragmentation_ratio > self.fragmentation_threshold and
            metrics.is_fragmented
        )
    
    async def defragment(self, cache: LRUCache) -> DefragResult:
        entries = list(cache.entries.items())
        cache.clear()
        
        for key, entry in sorted(entries, key=lambda x: x[1].size, reverse=True):
            cache.set(key, entry.value, entry.metadata)
        
        return DefragResult(entries_moved=len(entries))
```

---

## 17. Metrics Engine

### 17.1 Control Metrics (STRICT)

| Metric | Properties |
|--------|------------|
| `memory_pressure` | lock-free, 1-op stale |
| `pending_keys` | lock-free, 1-op stale |
| `hit_ratio` | lock-free, 1-op stale |
| `fragmentation_ratio` | lock-free, 1-op stale |

### 17.2 Observability Metrics

- Sampled
- Async aggregation
- Dashboard only

### 17.3 Lock-Free Counter Implementation

```python
class LockFreeCounter:
    """Atomic counter using compare-and-swap."""
    
    def __init__(self, initial: int = 0):
        self._value = initial
    
    def increment(self) -> int:
        while True:
            current = self._value
            next_val = current + 1
            if cas(self._value, current, next_val):
                return next_val
    
    def decrement(self) -> int:
        while True:
            current = self._value
            next_val = current - 1
            if cas(self._value, current, next_val):
                return next_val
    
    def get(self) -> int:
        return self._value
```

---

## 18. Causality Correlation Metrics

### 18.1 Required Metrics

```python
@dataclass
class CausalityMetrics:
    per_tool_hits: dict[str, int]
    per_tool_misses: dict[str, int]
    per_tool_latency: dict[str, LatencyBreakdown]
    per_tool_errors: dict[str, ErrorBreakdown]
    anomaly_signals: list[AnomalySignal]

@dataclass
class LatencyBreakdown:
    cache_lookup_ms: float
    tool_execution_ms: float
    embedding_generation_ms: float
    serialization_ms: float
    total_ms: float

@dataclass
class ErrorBreakdown:
    network_errors: int
    timeout_errors: int
    validation_errors: int
    resource_errors: int

@dataclass
class AnomalySignal:
    type: str
    severity: float
    probable_cause: str
    affected_metrics: list[str]
    timestamp: float
```

### 18.2 Per-Tool Causality Tracing

```python
class PerToolCausalityTracer:
    def __init__(self):
        self.tool_traces: dict[str, list[ToolTrace]] = {}
        self.correlation_window = 60
    
    async def trace_execution(
        self,
        tool_name: str,
        cache_hit: bool,
        latency_ms: float,
        error: Optional[Exception]
    ) -> ToolTrace:
        trace = ToolTrace(
            tool_name=tool_name,
            timestamp=time.time(),
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            error_type=type(error).__name__ if error else None,
            memory_state=self._capture_memory_state(),
            system_load=self._capture_system_load()
        )
        
        self.tool_traces.setdefault(tool_name, []).append(trace)
        await self._check_anomalies(tool_name)
        
        return trace
    
    async def _check_anomalies(self, tool_name: str):
        recent = self._get_recent_traces(tool_name)
        
        recent_hit_rate = sum(1 for t in recent if t.cache_hit) / len(recent)
        historical_hit_rate = self._get_historical_hit_rate(tool_name)
        
        if recent_hit_rate < historical_hit_rate * 0.5:
            await self._emit_anomaly(
                AnomalySignal(
                    type="sudden_miss_spike",
                    severity=0.8,
                    probable_cause="cache_pollution_or_ttl_expiry",
                    affected_metrics=["hit_rate", "miss_count"]
                )
            )
```

### 18.3 Latency Breakdown Analysis

```python
class LatencyAnalyzer:
    async def analyze_latency(
        self,
        request_start: float,
        request_end: float,
        cache_lookup_time: float,
        embedding_time: float,
        tool_execution_time: float
    ) -> LatencyBreakdown:
        serialization_time = (request_end - request_start) - (
            cache_lookup_time + embedding_time + tool_execution_time
        )
        
        return LatencyBreakdown(
            cache_lookup_ms=cache_lookup_time,
            tool_execution_ms=tool_execution_time,
            embedding_generation_ms=embedding_time,
            serialization_ms=max(0, serialization_time),
            total_ms=request_end - request_start
        )
    
    def identify_bottleneck(self, breakdown: LatencyBreakdown) -> str:
        components = {
            "cache_lookup": breakdown.cache_lookup_ms,
            "embedding_generation": breakdown.embedding_generation_ms,
            "tool_execution": breakdown.tool_execution_ms,
            "serialization": breakdown.serialization_ms
        }
        return max(components, key=components.get)
```

### 18.4 Anomaly Detection

```python
class AnomalyDetector:
    def __init__(self):
        self.baseline_windows: dict[str, list[float]] = {}
        self.baseline_window_size = 100
        self.zscore_threshold = 3.0
    
    async def detect_anomalies(
        self,
        current_metrics: dict[str, float]
    ) -> list[AnomalySignal]:
        anomalies = []
        
        for metric_name, current_value in current_metrics.items():
            if metric_name not in self.baseline_windows:
                self.baseline_windows[metric_name] = []
            
            window = self.baseline_windows[metric_name]
            
            if len(window) >= self.baseline_window_size:
                mean = statistics.mean(window)
                stdev = statistics.stdev(window)
                
                zscore = (current_value - mean) / stdev if stdev > 0 else 0
                
                if abs(zscore) > self.zscore_threshold:
                    anomalies.append(AnomalySignal(
                        type=f"{metric_name}_anomaly",
                        severity=min(1.0, abs(zscore) / 5.0),
                        probable_cause=self._infer_cause(metric_name, zscore),
                        affected_metrics=[metric_name],
                        timestamp=time.time()
                    ))
            
            window.append(current_value)
            if len(window) > self.baseline_window_size:
                window.pop(0)
        
        return anomalies
    
    def _infer_cause(self, metric_name: str, zscore: float) -> str:
        causes = {
            "hit_rate": "cache_pollution or TTL misconfiguration",
            "miss_count": "cold_start or cache_invalidation_storm",
            "latency_p99": "memory_pressure or embedding_service_slowdown",
            "memory_pressure": "memory_leak or large_object_accumulation",
            "pending_keys": "embedding_service_unavailable or timeout_flood"
        }
        return causes.get(metric_name, "unknown_cause")
```

---

## 19. Cluster Consistency Layer

### 19.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Cluster View                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ Node A   │  │ Node B   │  │ Node C   │                │
│  │ Partition│  │ Partition│  │ Partition│                │
│  │ Hash(A)  │  │ Hash(B)  │  │ Hash(C)  │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│         ↖           ↑           ↗                           │
│         └───────────┼───────────┘                           │
│                     │                                       │
│              ┌──────▼──────┐                               │
│              │ Coordinator │                               │
│              │  (Redis/DB) │                               │
│              │  - Lock     │                               │
│              │  - Config   │                               │
│              │  - Health   │                               │
│              └─────────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### 19.2 Partitioning Strategy

| Strategy | Use Case | Pros | Cons |
|----------|----------|------|------|
| Hash-based | Uniform distribution | Simple, predictable | Rebalancing expensive |
| Consistent hashing | Dynamic scaling | Minimize reshuffle | More complex |
| Range-based | Time-series access | Good for temporal patterns | Hot spots |

### 19.3 Shared LRU Strategies

#### Option A: Local LRU + Invalidation Broadcast

```python
async def evict_and_broadcast(key: str):
    local_lru.evict(key)
    await redis.publish("cache_invalidation", {"key": key, "node": node_id})

async def on_invalidation(message):
    key = message["key"]
    if key in local_cache:
        local_cache.delete(key)
```

#### Option B: Centralized LRU with Versioning

```python
async def get_with_version(key: str):
    entry, version = await redis.get_with_version(key)
    local_entry = local_cache.get(key)
    
    if local_entry and local_entry.version >= version:
        return local_entry
    
    return entry
```

#### Option C: Hybrid (Recommended)

```python
class HybridLRU:
    def __init__(self):
        self.local = LRUCache(max_items=1000)
        self.coordinator = RedisCoordinator()
        self.local_only_threshold = 0.8
    
    async def get(self, key: str):
        local = self.local.get(key)
        if local:
            self.local.hit(key)
            return local
        
        remote = await self.coordinator.get(key)
        if remote:
            self.local.set(key, remote)
            return remote
        
        return None
```

### 19.4 Cluster Rebalancing

```python
async def rebalance_cluster():
    target = calculate_even_distribution(num_nodes)
    hot_keys = await metrics.get_hot_keys()
    
    for key in hot_keys:
        current_node = get_current_owner(key)
        target_node = target[key]
        
        if current_node != target_node:
            await migrate_key(key, current_node, target_node)
            await asyncio.sleep(0.1)
```

**Rebalance Triggers:**

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Node join | New partition assignment | Migrate keys gradually |
| Node leave | Detect via heartbeat | Reassign partitions |
| Load skew | Ratio > 2:1 | Move hot keys |
| Periodic | Every 1 hour | Optimize distribution |

---

## 20. ReconciliationEngine Conflict Model

### 20.1 Vector Clock Specification

```python
@dataclass
class VectorClock:
    clock: dict[str, int]  # node_id → counter
    
    def increment(self, node_id: str) -> VectorClock:
        new_clock = self.clock.copy()
        new_clock[node_id] = new_clock.get(node_id, 0) + 1
        return VectorClock(new_clock)
    
    def merge(self, other: VectorClock) -> VectorClock:
        merged = {}
        for node_id in set(self.clock.keys()) | set(other.clock.keys()):
            merged[node_id] = max(
                self.clock.get(node_id, 0),
                other.clock.get(node_id, 0)
            )
        return VectorClock(merged)
    
    def happens_before(self, other: VectorClock) -> bool:
        at_most_one_larger = False
        for node_id in set(self.clock.keys()) | set(other.clock.keys()):
            s_val = self.clock.get(node_id, 0)
            o_val = other.clock.get(node_id, 0)
            if s_val > o_val:
                return False
            if s_val < o_val:
                at_most_one_larger = True
        return at_most_one_larger
    
    def conflicts_with(self, other: VectorClock) -> bool:
        return not (self.happens_before(other) or other.happens_before(self))
```

### 20.2 Conflict Resolution Rules

```python
class ConflictResolutionStrategy(Enum):
    LAST_WRITE_WINS = "lww"           # Simple, fast
    MERGE_VALUES = "merge"            # For dicts/lists
    KEEP_ALL = "keep_all"             # Store both versions
    PRIORITY_NODE = "priority"         # Certain nodes win
    DISCARD = "discard"               # Throw away conflicts

TOOL_CONFLICT_STRATEGY = {
    "code_generation": ConflictResolutionStrategy.LAST_WRITE_WINS,
    "data_retrieval": ConflictResolutionStrategy.MERGE_VALUES,
    "file_operations": ConflictResolutionStrategy.DISCARD,
}
```

### 20.3 Resolution Rule Matrix

| Scenario | Resolution Strategy | Policy |
|----------|-------------------|--------|
| Concurrent writes | Merge or Discard | Configurable per tool |
| Stale write | Auto-reject | Timestamp check |
| Node crash | Tombstone + GC | 24h retention |
| Network partition | Quorum write | 2/3 majority |

---

## 21. Backpressure Propagation Model

### 21.1 Problem

Cache can overload but agent continues spamming → upstream collapse.

### 21.2 Propagation Path

```
┌──────────────────────────────────────────────────────────────┐
│                    Backpressure Flow                          │
│                                                              │
│  ┌──────────┐   ┌────────────┐   ┌───────────┐   ┌───────┐│
│  │ ToolCache │ ← │ ToolExecutor │ ← │  Agent    │ ← │ User  ││
│  │          │   │            │   │           │   │ Input ││
│  └────┬─────┘   └─────┬──────┘   └─────┬─────┘   └───────┘│
│       │               │                │                     │
│       ▼               │                │                     │
│  ┌──────────┐         │                │                     │
│  │ OVERLOAD │ ────► │  THROTTLE      │ ────► │ REJECT     ││
│  │ DETECTED │         │                │                     │
│  └──────────┘         │                │                     │
└──────────────────────────────────────────────────────────────┘
```

### 21.3 Signal Types

```python
@dataclass
class BackpressureSignal:
    source: str
    severity: float          # 0.0 - 1.0 (0.5+ = throttle, 0.8+ = reject)
    metric: str              # memory_pressure, queue_depth, latency_p99
    current_value: float
    threshold: float
    timestamp: float

@dataclass
class AggregatedBackpressure:
    overall_severity: float
    throttle_threshold: float = 0.5
    reject_threshold: float = 0.8
    affected_endpoints: list[str]
```

### 21.4 Propagation Implementation

```python
class BackpressureManager:
    def __init__(self):
        self.signals: dict[str, BackpressureSignal] = {}
        self.throttle_threshold = 0.5
        self.reject_threshold = 0.8
    
    async def emit_signal(self, signal: BackpressureSignal):
        self.signals[signal.source] = signal
        severity = self._calculate_overall_severity()
        
        if severity >= self.reject_threshold:
            await self._propagate_reject()
        elif severity >= self.throttle_threshold:
            await self._propagate_throttle(severity)
    
    async def _propagate_throttle(self, severity: float):
        throttle_ratio = (severity - self.throttle_threshold) / (self.reject_threshold - self.throttle_threshold)
        
        await self.tool_executor.set_throttle(throttle_ratio)
        await self.agent.set_rate_limit(max_rps=100 * (1 - throttle_ratio))
    
    async def _propagate_reject(self):
        await self.tool_executor.reject_new_requests()
        await self.agent.set_rejection_mode(True)
```

### 21.5 Queue with Backpressure

```python
class BackpressureQueue:
    def __init__(self, max_size: int = 1000):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.backpressure_manager = BackpressureManager()
    
    async def put(self, item: Any, timeout: float = None):
        if self.queue.full():
            await self.backpressure_manager.emit_signal(
                BackpressureSignal(
                    source="queue",
                    severity=1.0,
                    metric="queue_depth",
                    current_value=self.queue.qsize(),
                    threshold=self.queue.maxsize
                )
            )
            raise QueueFullError()
        
        await self.queue.put(item, timeout=timeout)
```

---

## 22. Response Contract

### 22.1 CacheResponse

```python
class CacheResponse:
    value: Any | None
    state: Literal["HIT","MISS","STALE","DEGRADED","PARTIAL"]
    reason: Optional[str]
    source_node: Optional[str]  # For cluster mode
    vector_clock: Optional[dict]  # For conflict info
```

### 22.2 Semantic Rule

| State | Meaning |
|-------|---------|
| `HIT` | Safe direct use |
| `STALE` | Usable + may refresh |
| `MISS` | Must call tool |
| `DEGRADED` | Cache unreliable → avoid dependency |
| `PARTIAL` | Cluster: entry synced from another node |

---

## 23. Failure Safety

### 23.1 Global Invariants

System must guarantee:

- ✅ No deadlock
- ✅ No infinite retry
- ✅ No memory leak
- ✅ No unbounded task queue
- ✅ No silent corruption
- ✅ No blocking I/O in hot path
- ✅ No cluster split-brain (eventual consistency OK)
- ✅ No backpressure cascade without signal

---

## 24. Correctness Invariants

| ID | Invariant |
|----|-----------|
| I1 | **Linearizable key access**: Each key behaves as if processed sequentially |
| I2 | **Single-flight uniqueness**: At most 1 active execution per key (cluster-wide) |
| I3 | **No stampede amplification**: Refresh rate bounded per tool globally |
| I4 | **Memory boundedness**: LRU + fragmentation control guarantees O(capacity) |
| I5 | **Recovery safety**: System always degrades to MISS or DEGRADED safely |
| I6 | **No silent inconsistency**: All failures surface via reason/state |
| I7 | **Cluster consistency**: Vector clock ensures no lost updates |
| I8 | **Backpressure propagation**: Overload signals reach agent |

---

## 25. Definition of Done

System is production-ready when:

- ✅ No race condition possible under concurrent load
- ✅ No duplicate refresh possible per key
- ✅ Tool-level overload cannot cascade across keys
- ✅ Cache never blocks agent execution
- ✅ DEGRADED state fully functional + recoverable
- ✅ Warm-up cannot corrupt live data
- ✅ Persistence cannot affect runtime correctness
- ✅ All state transitions deterministic and formally defined
- ✅ Cluster mode passes consistency tests
- ✅ Backpressure properly propagates to agent
- ✅ Fragmentation stays under control
- ✅ Causality metrics identify root cause of anomalies

---

## 26. File Structure

```
src/infrastructure/cache/
├── __init__.py
├── tool/
│   ├── __init__.py
│   ├── types.py              # KeyState, CacheResponse, ValidationReason
│   ├── normalizer.py         # StrictNormalizer
│   ├── key_generator.py      # KeyGenerator (SHA256)
│   ├── state_machine.py      # KeyStateMachine (FSM)
│   ├── single_flight.py      # SingleFlightCoordinator (cluster-aware)
│   ├── swr_engine.py         # SWREngine (cluster-aware)
│   ├── rate_limiter.py       # ToolRateLimiter (hierarchical)
│   ├── threshold_engine.py   # AdaptiveThresholdEngine
│   ├── load_shedding.py      # LoadSheddingController
│   ├── lru_store.py          # LRUStore (byte+entry bounded)
│   ├── pin_manager.py        # PinManager
│   ├── adaptive_ttl.py       # AdaptiveTTLEngine
│   ├── validation.py         # PoisonValidationEngine
│   ├── warmup.py             # ProgressiveWarmupManager
│   ├── persistence.py        # PersistentStore
│   ├── write_back.py         # WriteBackQueue
│   ├── metrics.py            # MetricsEngine
│   ├── causality.py          # CausalityTracer + AnomalyDetector
│   ├── reconciliation.py      # ReconciliationEngine (vector clock)
│   ├── backpressure.py       # BackpressureManager
│   ├── fragmentation.py      # FragmentationManager + SlabAllocator
│   ├── cluster.py            # ClusterCoordinator + PartitionManager
│   └── cache.py              # ToolCache (main facade)
└── tests/
    └── unit/
        ├── test_types.py
        ├── test_state_machine.py
        ├── test_single_flight.py
        ├── test_rate_limiter.py
        ├── test_lru_store.py
        ├── test_validation.py
        ├── test_cluster.py
        ├── test_backpressure.py
        └── test_cache.py
```

---

## 27. Implementation Notes

### 27.1 Thread Safety

- All state transitions must be atomic
- Use `asyncio.Lock` for async operations
- Use atomic operations for metrics counters
- Use distributed locks for cluster coordination

### 27.2 Memory Management

- LRUStore enforces hard limits
- SlabAllocator reduces fragmentation
- DefragmentationManager runs periodic compaction
- PinManager handles dual constraints
- LoadSheddingController triggers eviction under pressure

### 27.3 Concurrency Model

- Single-flight coordinator prevents duplicate work
- SWR engine prevents thundering herd
- Rate limiter ensures fairness
- BackpressureManager propagates signals upstream
- Cluster coordinator ensures consistency

### 27.4 Error Handling

- All failures surface via `CacheResponse.reason`
- No silent corruption
- Automatic bypass on validation failure
- Anomaly detection identifies root causes

---

## 28. Remaining Risks & Mitigations

### 28.1 Redis Dependency & Fallback Modes

**Problem**: Cluster mode depends on Redis for distributed lock, coordinator, idempotency. No fallback defined for Redis failure.

**Risk**: Single point of failure. Redis crash can cause cluster freeze or split-brain.

**Mitigation - Fallback Modes**:

```python
class ClusterFallbackMode(Enum):
    LOCAL_ONLY = "local_only"   # Continue with local cache only
    READONLY = "readonly"       # Serve from cache, no writes
    FAIL_FAST = "fail_fast"    # Refuse to start without Redis

@dataclass
class ClusterConfig:
    fallback_mode: ClusterFallbackMode = ClusterFallbackMode.LOCAL_ONLY
    redis_required: bool = False              # If True, fail when Redis unavailable
    redis_retry_interval: float = 5.0         # Seconds between retries
    redis_max_retries: int = 3                # Retries before fallback
```

**Behavior by Mode**:

| Mode | On Redis Failure | Use Case |
|------|------------------|----------|
| `local_only` | Continue with local cache | Degraded but functional |
| `readonly` | Serve reads, queue writes | Read-heavy workloads |
| `fail_fast` | Raise error, refuse start | Redis is mandatory |

**Recommended**: Use Redis Cluster for HA or etcd as alternative coordinator.

---

### 28.2 Distributed Lock Performance

**Problem**: Each store with cluster mode requires `SET key NX EX` on Redis. With high key volume, this becomes bottleneck (RTT + lock wait).

**Risk**: Significant latency increase vs local single-flight.

**Mitigation - Hybrid Lock Strategy**:

```python
class HybridSingleFlightCoordinator:
    """
    Local single-flight first, cluster broadcast only when needed.
    Reduces Redis round-trips by 90% for typical workloads.
    """
    
    def __init__(self, redis_client=None, local_lock_threshold=100):
        self.redis = redis_client
        self.local_locks: dict[str, asyncio.Lock] = {}
        self.local_lock_threshold = local_lock_threshold
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        # Phase 1: Try local lock first
        if key in self.local_locks:
            return await self.local_locks[key].acquire(timeout=timeout)
        
        # Phase 2: Quick Redis check only if contention expected
        if self._should_use_redis(key):
            lock_acquired = await self.redis.set(
                f"lock:{key}", self.node_id, nx=True, ex=5
            )
            if not lock_acquired:
                return False
        
        # Create local lock for this key
        self.local_locks[key] = asyncio.Lock()
        return True
    
    async def release(self, key: str):
        if key in self.local_locks:
            await self.local_locks[key].release()
            del self.local_locks[key]
        
        await self.redis.delete(f"lock:{key}")
    
    def _should_use_redis(self, key: str) -> bool:
        # Only use Redis lock for hot keys (potential contention)
        return self.local_locks.get(key, asyncio.Lock()).locked()
```

**Additional Optimization**: Use lease-based locks with short TTL (5-10s) and automatic extension.

---

### 28.3 Warm-Up Sampling Quality

**Problem**: Progressive warm-up uses `random.sample` from predefined queries. May not represent actual traffic distribution.

**Risk**: Cache filled with rarely-used entries, wasting memory.

**Mitigation - Frequency-Based Sampling**:

```python
class FrequencyBasedWarmupSampler:
    """
    Sample warm-up queries based on production frequency.
    """
    
    def __init__(self, warmup_query_source: WarmupQuerySource):
        self.source = warmup_query_source
        self.query_weights: dict[str, float] = {}
    
    async def load_top_k_queries(self, k: int = 1000) -> list[WarmupQuery]:
        # Source 1: Query logs from production (highest priority)
        production_queries = await self.source.get_from_logs(k)
        
        # Source 2: Frequency-based sampling
        if len(production_queries) < k:
            historical = await self.source.get_historical(k * 2)
            production_keys = {q.key for q in production_queries}
            additional = [q for q in historical if q.key not in production_keys]
            production_queries.extend(additional[:k - len(production_queries)])
        
        # Source 3: Fallback to synthetic but weighted by entropy
        if len(production_queries) < k:
            synthetic = await self.source.generate_synthetic(k)
            production_queries.extend(synthetic)
        
        return production_queries[:k]
    
    async def sample_for_warmup(
        self,
        batch_size: int,
        warmup_progress: float
    ) -> list[WarmupQuery]:
        """
        Sample queries weighted by frequency.
        As warmup progresses, focus on hot entries.
        """
        all_queries = await self.load_top_k_queries(k=batch_size * 10)
        
        if warmup_progress < 0.5:
            # Early phase: spread coverage
            return random.sample(all_queries, batch_size)
        else:
            # Later phase: focus on hottest queries
            sorted_by_freq = sorted(all_queries, key=lambda q: q.frequency, reverse=True)
            return sorted_by_freq[:batch_size]
```

**Source Priority**:
1. Live query logs from production (real distribution)
2. Historical frequency data
3. Synthetic queries as last resort

---

### 28.4 Slab Size Configuration

**Problem**: Hardcoded slab sizes (64, 128, ..., 16384 bytes) may not fit all workloads. Large objects (200KB+) fall into 16KB slab causing waste.

**Risk**: Increased fragmentation or inefficient memory usage.

**Mitigation - Configurable Slab Sizes**:

```python
@dataclass
class SlabConfig:
    """Configurable slab sizes per environment."""
    
    # Default sizes (bytes)
    slab_sizes: list[int] = field(default_factory=lambda: [
        64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384
    ])
    
    # Environment-specific overrides
    large_object_threshold: int = 1024 * 100  # 100KB
    
    # For memory-intensive workloads
    large_slab_sizes: list[int] = field(default_factory=lambda: [
        16384, 32768, 65536, 131072, 262144  # 16KB - 256KB
    ])

class AdaptiveSlabAllocator:
    """
    Dynamically adjusts slab sizes based on workload.
    """
    
    def __init__(self, config: SlabConfig):
        self.config = config
        self.size_distribution: dict[int, int] = {}  # size -> count
        self.rebalance_interval = 3600  # 1 hour
    
    async def record_allocation(self, size: int):
        """Track size distribution for rebalancing."""
        bucket = self._get_bucket(size)
        self.size_distribution[bucket] = self.size_distribution.get(bucket, 0) + 1
    
    async def should_rebalance(self) -> bool:
        """Check if slab sizes should be adjusted."""
        if len(self.size_distribution) < 1000:
            return False
        
        # Check if any size consistently falls into "overflow"
        overflow_ratio = self.size_distribution.get(0, 0) / sum(self.size_distribution.values())
        return overflow_ratio > 0.2  # >20% overflow
    
    def get_slab_sizes(self) -> list[int]:
        """Return current slab sizes (may be adjusted)."""
        if await self.should_rebalance():
            return self._calculate_optimal_sizes()
        return self.config.slab_sizes
```

**Profile Before Deploy**: Analyze production object sizes and configure accordingly.

---

### 28.5 Self-Preservation Mode

**Problem**: Backpressure propagates to agent, but agent may not comply. Cache needs self-protection.

**Risk**: Agent continues sending requests, cache still processes → no root fix.

**Mitigation - Self-Preservation Mode**:

```python
class BackpressureManager:
    def __init__(self):
        self.signals: dict[str, BackpressureSignal] = {}
        self.self_preservation_threshold = 0.9
        self.self_preservation_active = False
        
        # Track recent self-preservation activations
        self.preservation_history: deque = deque(maxlen=10)
    
    async def emit_signal(self, signal: BackpressureSignal):
        self.signals[signal.source] = signal
        severity = self._calculate_overall_severity()
        
        # Check self-preservation threshold
        if severity >= self.self_preservation_threshold:
            await self._activate_self_preservation(severity)
            return
        
        # Normal propagation
        if severity >= self.reject_threshold:
            await self._propagate_reject()
        elif severity >= self.throttle_threshold:
            await self._propagate_throttle(severity)
    
    async def _activate_self_preservation(self, severity: float):
        """
        Cache self-protects when severity > 0.9.
        No agent cooperation required.
        """
        self.self_preservation_active = True
        self.preservation_history.append(time.time())
        
        logger.warning(
            f"Self-preservation activated: severity={severity:.2f}"
        )
    
    async def should_serve_request(self) -> tuple[bool, Optional[str]]:
        """
        Check if request should be served despite backpressure.
        Returns (allowed, reason).
        """
        if not self.self_preservation_active:
            return True, None
        
        # Auto-recover after cooldown
        if time.time() - self.preservation_history[-1] > 30:
            self.self_preservation_active = False
            return True, None
        
        # Return DEGRADED state for all requests
        return False, "SELF_PRESERVATION_ACTIVE"


class SelfPreservationIntegration:
    """Integrate self-preservation into cache get path."""
    
    async def get_with_preservation(self, key: str) -> CacheResponse:
        should_serve, reason = await backpressure_manager.should_serve_request()
        
        if not should_serve:
            return CacheResponse(
                value=None,
                state="DEGRADED",
                reason=reason
            )
        
        return await self.cache.get(key)
```

**Key Principle**: Cache protects itself regardless of agent behavior.

---

### 28.6 Causality Metrics Performance

**Problem**: Z-score, moving average, percentile calculations on each request/cycle may impact latency.

**Risk**: Slower than expected, especially with anomaly detection for all tools.

**Mitigation - Off-Critical Path Processing**:

```python
class CausalityMetricsCollector:
    """
    Run causality analysis off the critical path.
    """
    
    def __init__(self):
        self.analysis_interval = 10.0  # Analyze every 10 seconds
        self.sample_rate = 0.1  # Sample 10% of requests
        
        # Background task for analysis
        self._analysis_task: Optional[asyncio.Task] = None
    
    async def start(self):
        self._analysis_task = asyncio.create_task(self._analysis_loop())
    
    async def _analysis_loop(self):
        """Background loop for causality analysis."""
        while True:
            await asyncio.sleep(self.analysis_interval)
            
            try:
                # Collect buffered metrics
                metrics = await self._drain_buffer()
                
                # Run anomaly detection (off-path)
                anomalies = await self._detect_anomalies(metrics)
                
                # Update baselines
                await self._update_baselines(metrics)
                
                # Emit alerts if needed
                for anomaly in anomalies:
                    await self._emit_alert(anomaly)
                    
            except Exception as e:
                logger.error(f"Causality analysis failed: {e}")
    
    async def record_request(self, trace: ToolTrace):
        """Called on each request (minimal overhead)."""
        if random.random() < self.sample_rate:
            self._buffer.append(trace)
    
    async def _detect_anomalies(self, metrics: list[ToolTrace]) -> list[AnomalySignal]:
        """Z-score detection runs in background."""
        # Implement with batch processing
        pass
```

**Optimization Summary**:

| Component | Strategy |
|-----------|----------|
| Z-score | Calculate every 10s, not per-request |
| Percentile | Use t-digest sketch for approximation |
| Moving average | Exponential decay, O(1) update |
| Anomaly detection | Only on sampled data (10%) |

---

### 28.7 Reconciliation Frequency & Triggers

**Problem**: Vector clock stored but reconciliation job timing undefined. Nodes may drift indefinitely.

**Risk**: Extended cache inconsistency between nodes.

**Mitigation - Reconciliation Schedule**:

```python
@dataclass
class ReconciliationConfig:
    """Define when reconciliation runs."""
    
    # Periodic reconciliation
    interval_seconds: int = 60          # Run every 60 seconds
    
    # Event-driven triggers
    trigger_on_write: bool = True       # Push vector clocks after write
    trigger_on_partition_migration: bool = True
    
    # Threshold-based triggers
    drift_threshold: int = 5            # Reconcile if drift > 5
    
    # Background task
    max_batch_size: int = 100           # Keys per reconciliation cycle

class ReconciliationScheduler:
    """
    Manages when reconciliation runs.
    """
    
    def __init__(self, config: ReconciliationConfig):
        self.config = config
        self._periodic_task: Optional[asyncio.Task] = None
    
    async def start(self, coordinator: ClusterCoordinator):
        self._periodic_task = asyncio.create_task(
            self._periodic_reconciliation(coordinator)
        )
    
    async def trigger_reconciliation(
        self,
        key: str,
        local_clock: VectorClock,
        coordinator: ClusterCoordinator
    ):
        """Event-driven reconciliation after writes."""
        if not self.config.trigger_on_write:
            return
        
        # Send vector clock to coordinator
        remote_clock = await coordinator.get_vector_clock(key)
        
        if self._has_drift(local_clock, remote_clock):
            await self._reconcile_key(key, coordinator)
    
    async def _periodic_reconciliation(self, coordinator: ClusterCoordinator):
        """Background periodic reconciliation."""
        while True:
            await asyncio.sleep(self.config.interval_seconds)
            
            # Get keys with potential drift
            drifted_keys = await coordinator.get_drifted_keys(
                threshold=self.config.drift_threshold
            )
            
            # Process in batches
            for batch in self._batches(drifted_keys, self.config.max_batch_size):
                await self._reconcile_batch(batch, coordinator)
                await asyncio.sleep(0.1)  # Rate limit
    
    def _has_drift(self, local: VectorClock, remote: VectorClock) -> bool:
        """Check if drift exceeds threshold."""
        for node_id in set(local.clock.keys()) | set(remote.clock.keys()):
            drift = abs(
                local.clock.get(node_id, 0) - remote.clock.get(node_id, 0)
            )
            if drift > self.config.drift_threshold:
                return True
        return False
```

**Recommended Settings**:

| Environment | Interval | Trigger on Write | Drift Threshold |
|-------------|----------|------------------|-----------------|
| Development | 30s | False | 10 |
| Staging | 60s | True | 5 |
| Production | 60s | True | 3 |

---

### 28.8 Graceful Shutdown

**Problem**: When node leaves cluster, pending writes, in-flight requests, and held locks may hang.

**Risk**: Deadlock, resource leak.

**Mitigation - Graceful Shutdown Protocol**:

```python
class GracefulShutdownManager:
    """
    Coordinates graceful shutdown for cluster nodes.
    """
    
    async def on_shutdown(self, cache: ToolCache, coordinator: ClusterCoordinator):
        """
        Execute shutdown sequence:
        1. Stop accepting new requests
        2. Wait for in-flight requests
        3. Release distributed locks
        4. Transfer partition ownership
        5. Flush pending writes
        """
        logger.info("Initiating graceful shutdown...")
        
        # Phase 1: Stop accepting (30s timeout)
        await self._stop_accepting_requests(timeout=30)
        
        # Phase 2: Wait for in-flight (60s timeout)
        await self._wait_for_inflight(timeout=60)
        
        # Phase 3: Release distributed locks
        await self._release_locks(coordinator)
        
        # Phase 4: Transfer partition ownership
        await self._transfer_ownership(coordinator)
        
        # Phase 5: Flush write queue
        await self._flush_write_queue(cache)
        
        # Phase 6: Final sync
        await coordinator.mark_node_offline(self.node_id)
        
        logger.info("Graceful shutdown complete")
    
    async def _release_locks(self, coordinator: ClusterCoordinator):
        """Release all distributed locks held by this node."""
        held_locks = await coordinator.get_held_locks(self.node_id)
        
        for lock_key in held_locks:
            try:
                await coordinator.release_lock(lock_key, self.node_id)
            except Exception as e:
                logger.warning(f"Failed to release lock {lock_key}: {e}")
    
    async def _transfer_ownership(
        self,
        coordinator: ClusterCoordinator
    ):
        """
        Transfer partition ownership to other nodes.
        Uses consistent hashing ring.
        """
        owned_partitions = coordinator.get_node_partitions(self.node_id)
        
        for partition in owned_partitions:
            target_node = coordinator.get_next_node(partition)
            
            try:
                # Copy partition data
                await coordinator.transfer_partition(
                    partition,
                    from_node=self.node_id,
                    to_node=target_node
                )
            except Exception as e:
                logger.error(f"Failed to transfer partition {partition}: {e}")
                # Continue with other partitions
    
    async def _flush_write_queue(self, cache: ToolCache):
        """Flush pending writes to persistence."""
        flush_timeout = 30
        await asyncio.wait_for(
            cache.write_back_queue.flush(),
            timeout=flush_timeout
        )
```

**Shutdown Timeout**: Total shutdown should complete within 3-5 minutes.

---

### 28.9 Cluster Node Join Warm-Up

**Problem**: Progressive warm-up only applies to first node start. New node joining running cluster is cold and may cause traffic spike.

**Risk**: Same as cold-start problem, but occurs on scale-out.

**Mitigation - Cluster Node Join Warm-Up**:

```python
class ClusterNodeJoinWarmup:
    """
    Warm up new node joining existing cluster.
    """
    
    async def on_node_join(
        self,
        new_node: str,
        coordinator: ClusterCoordinator
    ):
        """
        Sequence for new node joining cluster.
        """
        logger.info(f"Node {new_node} joining cluster, initiating warmup...")
        
        # Phase 1: Enter shadow mode
        await coordinator.set_node_mode(new_node, "shadow")
        
        # Phase 2: Copy hot entries from other nodes
        hot_entries = await self._fetch_hot_entries(coordinator)
        await self._populate_local_cache(new_node, hot_entries)
        
        # Phase 3: Monitor shadow traffic performance
        await self._validate_shadow_performance(new_node, coordinator)
        
        # Phase 4: Gradually increase traffic
        await self._gradual_traffic_increase(new_node, coordinator)
        
        # Phase 5: Mark as active
        await coordinator.set_node_mode(new_node, "active")
        
        logger.info(f"Node {new_node} warmup complete, now active")
    
    async def _fetch_hot_entries(
        self,
        coordinator: ClusterCoordinator
    ) -> list[CacheEntry]:
        """
        Fetch top-k hot entries from existing nodes.
        Uses coordinator as relay.
        """
        all_nodes = await coordinator.get_active_nodes()
        hot_entries = []
        
        # Collect from each node (parallel)
        results = await asyncio.gather(*[
            coordinator.get_hot_entries(node, k=500)
            for node in all_nodes
        ])
        
        for entries in results:
            hot_entries.extend(entries)
        
        # Dedupe and return top-k
        seen_keys = set()
        unique_entries = []
        for entry in hot_entries:
            if entry.key not in seen_keys:
                seen_keys.add(entry.key)
                unique_entries.append(entry)
        
        return unique_entries[:1000]  # Top 1000 unique entries
    
    async def _gradual_traffic_increase(
        self,
        new_node: str,
        coordinator: ClusterCoordinator
    ):
        """
        Gradually increase traffic to new node over time.
        """
        traffic_stages = [
            (0.1, 30),   # 10% for 30s
            (0.25, 60),  # 25% for 60s
            (0.5, 120),  # 50% for 2min
            (1.0, 0),    # 100% - done
        ]
        
        for ratio, duration in traffic_stages:
            await coordinator.set_node_traffic_ratio(new_node, ratio)
            
            if duration > 0:
                await asyncio.sleep(duration)
```

---

### 28.10 Cluster Model: Partitioned vs Replicated

**Problem**: Spec says "cluster mode" but doesn't clarify:
- Are all nodes reading/writing to same partition?
- Is each key owned by single node (partitioned) or all nodes (replicated)?

**Risk**: Conflict resolution differs by model. Partitioned = minimal conflict. Replicated = frequent conflicts.

**Decision - Partitioned Cluster (Recommended)**:

```python
@dataclass
class ClusterTopology:
    """
    Cluster topology configuration.
    Partitioned model: each key has single owner.
    """
    
    model: Literal["partitioned", "replicated"] = "partitioned"
    
    # For partitioned model
    num_partitions: int = 256           # Consistent hashing partitions
    replication_factor: int = 1         # Replicas per partition (for HA)
    
    # For replicated model
    quorum_size: int = 2                # Required for writes

class PartitionManager:
    """
    Manages consistent hashing for partitioned cluster.
    """
    
    def __init__(self, config: ClusterTopology):
        self.config = config
        self.ring: list[tuple[int, str]] = []  # (hash, node_id)
        self._build_ring()
    
    def get_owner(self, key: str) -> str:
        """Get primary owner of key."""
        hash_value = self._hash(key)
        return self._find_node(hash_value)
    
    def get_replicas(self, key: str) -> list[str]:
        """Get replica owners for key (for HA)."""
        if self.config.replication_factor == 1:
            return []
        
        primary = self.get_owner(key)
        return self._find_next_n_nodes(primary, self.config.replication_factor)
    
    def _find_node(self, hash_value: int) -> str:
        """Binary search for node in ring."""
        # Simplified: linear search for example
        for ring_hash, node_id in sorted(self.ring):
            if hash_value <= ring_hash:
                return node_id
        return self.ring[0][1]  # Wrap around


class PartitionedCache:
    """
    Cache operations respect partition ownership.
    """
    
    def __init__(self, partition_manager: PartitionManager):
        self.pm = partition_manager
    
    async def get(self, key: str) -> CacheResponse:
        owner = self.pm.get_owner(key)
        
        if owner == self.node_id:
            # Local access
            return await self.local_cache.get(key)
        else:
            # Remote access via coordinator
            return await self.coordinator.fetch_remote(owner, key)
    
    async def set(self, key: str, value: Any) -> bool:
        owner = self.pm.get_owner(key)
        
        if owner != self.node_id:
            # Forward to owner
            return await self.coordinator.forward_to(owner, key, value)
        
        # Local write
        return await self.local_cache.set(key, value)
```

**Model Comparison**:

| Aspect | Partitioned | Replicated |
|--------|-------------|------------|
| Conflict Frequency | Rare (only on migration) | Frequent |
| Consistency Model | Strong per-key | Eventual per-node |
| Memory Efficiency | High | Low (multiple copies) |
| Complexity | Lower | Higher |
| Recommended For | Most production | Specialized cases |

**Partitioned Model Selected**: Recommended for production due to simplicity and low conflict rate.

---

## 29. Minor Issues & Refinements

### 29.1 Self-Preservation Flapping Prevention

**Problem**: When severity oscillates around 0.9 threshold, cache may rapidly switch between normal and self-preservation modes, causing instability.

**Fix - Add Flapping Prevention**:

```python
@dataclass
class BackpressureConfig:
    # Flapping prevention
    min_preservation_duration: float = 30.0    # Minimum time in preservation mode
    cooldown_after_preservation: float = 60.0  # Cooldown before re-entry
    flapping_threshold: int = 3                 # Max activations in window

class BackpressureManager:
    def __init__(self, config: BackpressureConfig):
        self.config = config
        self.self_preservation_active = False
        self.preservation_enter_time: Optional[float] = None
        self.last_exit_time: Optional[float] = None
        self.activation_count = 0
        self.activation_window_start = time.time()
    
    async def should_enter_preservation(self, severity: float) -> bool:
        """Check if should enter preservation mode with flapping prevention."""
        
        if self.self_preservation_active:
            return False  # Already in preservation
        
        # Check cooldown after last exit
        if self.last_exit_time:
            if time.time() - self.last_exit_time < self.config.cooldown_after_preservation:
                return False
        
        # Check flapping threshold
        if self.activation_count >= self.config.flapping_threshold:
            if time.time() - self.activation_window_start < 300:  # 5 min window
                logger.error("Flapping detected! Forcing extended cooldown")
                self.last_exit_time = time.time()
                self.activation_count = 0
                return False
        
        # Enter if severity exceeds threshold
        return severity >= self.self_preservation_threshold
    
    async def _activate_self_preservation(self, severity: float):
        """Activate with flapping tracking."""
        
        self.self_preservation_active = True
        self.preservation_enter_time = time.time()
        
        # Track activations
        self.activation_count += 1
        if time.time() - self.activation_window_start > 300:
            self.activation_count = 1
            self.activation_window_start = time.time()
    
    async def should_exit_preservation(self) -> bool:
        """Check if can exit preservation mode."""
        
        if not self.self_preservation_active:
            return False
        
        # Enforce minimum duration
        elapsed = time.time() - self.preservation_enter_time
        if elapsed < self.config.min_preservation_duration:
            return False
        
        # Check if severity has dropped below recovery threshold
        severity = self._calculate_overall_severity()
        return severity < 0.5  # Exit only when severity drops to 0.5
    
    async def _exit_self_preservation(self):
        """Exit preservation mode with tracking."""
        
        self.self_preservation_active = False
        self.preservation_enter_time = None
        self.last_exit_time = time.time()
```

---

### 29.2 Environment-Specific Drift Threshold

**Problem**: Fixed drift threshold = 3 may be too aggressive in slow networks, causing unnecessary reconciliation.

**Fix - Configurable Per Environment**:

```python
@dataclass
class ReconciliationConfig:
    # Drift threshold with environment defaults
    drift_threshold: int = 3                    # Production default
    
    # Environment-specific overrides
    environment_overrides: dict[str, int] = field(default_factory=lambda: {
        "development": 10,
        "staging": 5,
        "production": 3,
    })
    
    # Or use percentile-based threshold
    use_percentile_threshold: bool = False
    drift_percentile: float = 0.95  # Reconcile if drift > P95 latency
    
    # Network latency awareness
    typical_latency_ms: float = 10.0  # Used to calculate acceptable drift

class ReconciliationScheduler:
    def _calculate_adaptive_threshold(self, coordinator: ClusterCoordinator) -> int:
        """Calculate threshold based on current network conditions."""
        
        if self.config.use_percentile_threshold:
            # Use P95 latency as threshold
            recent_latencies = coordinator.get_recent_latencies()
            if recent_latencies:
                return int(percentile(recent_latencies, self.config.drift_percentile * 100))
        
        return self.config.drift_threshold
    
    def _has_drift(self, local: VectorClock, remote: VectorClock) -> bool:
        """Check drift with adaptive threshold."""
        
        threshold = self._calculate_adaptive_threshold(self.coordinator)
        
        for node_id in set(local.clock.keys()) | set(remote.clock.keys()):
            drift = abs(
                local.clock.get(node_id, 0) - remote.clock.get(node_id, 0)
            )
            if drift > threshold:
                return True
        return False
```

**Recommended Settings**:

| Environment | Drift Threshold | Notes |
|-------------|-----------------|-------|
| Development | 10 | High latency acceptable |
| Staging | 5 | Moderate |
| Production | 3 | Strict, low latency |

---

### 29.3 QueryLogCollector Specification

**Problem**: Spec mentions "load from production logs" but doesn't specify log storage, format, or ingestion mechanism.

**Fix - QueryLogCollector Component**:

```python
@dataclass
class WarmupQuery:
    key: str
    tool_name: str
    args: dict
    frequency: int = 1
    last_accessed: float
    avg_latency_ms: float

class QueryLogCollector:
    """
    Collects query logs for warm-up sampling.
    """
    
    def __init__(self, storage_path: str, sample_rate: float = 0.01):
        self.storage_path = storage_path
        self.sample_rate = sample_rate  # 1% of queries
        self._buffer: list[WarmupQuery] = []
        self._flush_interval = 3600  # Flush hourly
    
    async def record_query(self, key: str, tool_name: str, args: dict, latency_ms: float):
        """Record query for warm-up (sampled)."""
        
        if random.random() > self.sample_rate:
            return  # Skip based on sample rate
        
        query = WarmupQuery(
            key=key,
            tool_name=tool_name,
            args=args,
            frequency=1,
            last_accessed=time.time(),
            avg_latency_ms=latency_ms
        )
        
        self._buffer.append(query)
        
        if len(self._buffer) >= 1000:
            await self._flush()
    
    async def _flush(self):
        """Flush buffer to persistent storage."""
        
        if not self._buffer:
            return
        
        # Read existing data
        existing = await self._read_log()
        
        # Merge frequencies
        key_freq_map: dict[str, WarmupQuery] = {q.key: q for q in existing}
        
        for query in self._buffer:
            if query.key in key_freq_map:
                existing_q = key_freq_map[query.key]
                existing_q.frequency += 1
                existing_q.last_accessed = max(existing_q.last_accessed, query.last_accessed)
            else:
                key_freq_map[query.key] = query
        
        # Write back sorted by frequency
        sorted_queries = sorted(
            key_freq_map.values(),
            key=lambda q: q.frequency,
            reverse=True
        )
        
        await self._write_log(sorted_queries)
        self._buffer.clear()
    
    async def get_top_k_queries(self, k: int = 1000) -> list[WarmupQuery]:
        """Get top-k most frequent queries."""
        
        queries = await self._read_log()
        return queries[:k]
    
    async def _read_log(self) -> list[WarmupQuery]:
        """Read from persistent storage."""
        
        log_file = f"{self.storage_path}/warmup_queries.jsonl"
        
        if not os.path.exists(log_file):
            return []
        
        queries = []
        with open(log_file, 'r') as f:
            for line in f:
                queries.append(WarmupQuery(**json.loads(line)))
        
        return queries
    
    async def _write_log(self, queries: list[WarmupQuery]):
        """Write to persistent storage."""
        
        log_file = f"{self.storage_path}/warmup_queries.jsonl"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        with open(log_file, 'w') as f:
            for query in queries:
                f.write(json.dumps(asdict(query)) + '\n')
```

**Log Format** (JSONL):

```json
{"key": "sha256_hash", "tool_name": "code_search", "args": {...}, "frequency": 1523, "last_accessed": 1715932800.0, "avg_latency_ms": 45.2}
```

**Warm-Up Integration**:

```python
class WarmupManager:
    async def warmup_from_logs(self):
        """Warm up using collected query logs."""
        
        collector = QueryLogCollector(storage_path="/var/cache/query_logs")
        
        # Get top queries from last 7 days
        recent_queries = await collector.get_top_k_queries(k=5000)
        
        for query in recent_queries:
            await self.cache.get(query.key)  # Pre-populate
        
        return len(recent_queries)
```

---

### 29.4 WeakRef Lock Dictionary

**Problem**: `local_locks[key]` created on lock but not cleaned up when unused. Dictionary may grow indefinitely.

**Fix - Use WeakValueDictionary**:

```python
import weakref
from collections import defaultdict

class HybridSingleFlightCoordinator:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._local_locks: dict[str, asyncio.Lock] = {}
        self._lock_last_used: dict[str, float] = {}  # For cleanup tracking
        self._cleanup_interval = 300  # 5 minutes
        self._max_idle_locks = 10000  # Max idle locks before cleanup
    
    def _get_or_create_lock(self, key: str) -> asyncio.Lock:
        """Get existing lock or create new one with cleanup."""
        
        if key not in self._local_locks:
            self._local_locks[key] = asyncio.Lock()
            self._lock_last_used[key] = time.time()
        else:
            self._lock_last_used[key] = time.time()
        
        return self._local_locks[key]
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        lock = self._get_or_create_lock(key)
        
        try:
            return await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
    
    async def release(self, key: str):
        if key in self._local_locks:
            self._local_locks[key].release()
    
    async def cleanup_idle_locks(self):
        """Periodic cleanup of unused locks."""
        
        now = time.time()
        idle_threshold = 3600  # 1 hour idle
        
        keys_to_remove = [
            key for key, last_used in self._lock_last_used.items()
            if now - last_used > idle_threshold
        ]
        
        for key in keys_to_remove:
            if key in self._local_locks:
                del self._local_locks[key]
            del self._lock_last_used[key]
        
        if keys_to_remove:
            logger.info(f"Cleaned up {len(keys_to_remove)} idle locks")
    
    async def start_cleanup_task(self):
        """Start background cleanup task."""
        
        while True:
            await asyncio.sleep(self._cleanup_interval)
            
            if len(self._local_locks) > self._max_idle_locks:
                await self.cleanup_idle_locks()
```

**Alternative - LRU-based Lock Pool**:

```python
class LockPool:
    """LRU pool of locks to bound memory usage."""
    
    def __init__(self, max_locks: int = 5000):
        self.max_locks = max_locks
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
    
    def get_lock(self, key: str) -> asyncio.Lock:
        if key in self._locks:
            # Move to end (most recently used)
            self._locks.move_to_end(key)
            return self._locks[key]
        
        # Create new lock
        if len(self._locks) >= self.max_locks:
            # Remove oldest
            self._locks.popitem(last=False)
        
        lock = asyncio.Lock()
        self._locks[key] = lock
        return lock
```

---

### 29.5 Disk Space Check Before Spill

**Problem**: When queue is full and `on_full = "spill_to_disk"`, if disk is also full, spill fails silently.

**Fix - Disk Space Validation**:

```python
@dataclass
class WriteBackConfig:
    # Disk spill configuration
    on_full: Literal["drop", "spill_to_disk"] = "spill_to_disk"
    
    # Disk space requirements
    min_disk_free_mb: float = 100.0  # Minimum free space before spill
    spill_dir: str = "/var/cache/tool_cache/spill"
    max_spill_file_size_mb: float = 1024  # Max size per spill file

class WriteBackQueue:
    def __init__(self, config: WriteBackConfig):
        self.config = config
    
    async def _can_spill_to_disk(self) -> bool:
        """Check if disk has enough space for spill."""
        
        if not shutil.os.path.exists(self.config.spill_dir):
            return True  # Directory doesn't exist yet
        
        disk_usage = shutil.disk_usage(self.config.spill_dir)
        free_mb = disk_usage.free / (1024 * 1024)
        
        if free_mb < self.config.min_disk_free_mb:
            logger.error(
                f"Disk space low: {free_mb:.1f}MB free, "
                f"need {self.config.min_disk_free_mb}MB"
            )
            return False
        
        return True
    
    async def _write_spill_file(self, data: bytes) -> bool:
        """Write data to spill file with validation."""
        
        if len(data) > self.config.max_spill_file_size_mb * 1024 * 1024:
            logger.error(f"Data too large for spill: {len(data)} bytes")
            return False
        
        spill_path = f"{self.config.spill_dir}/spill_{int(time.time())}.bin"
        
        try:
            with open(spill_path, 'wb') as f:
                f.write(data)
            return True
        except IOError as e:
            logger.error(f"Failed to write spill file: {e}")
            return False
    
    async def on_queue_full(self, item: Any) -> bool:
        """Handle queue full situation."""
        
        if self.config.on_full == "drop":
            logger.warning("Queue full, dropping item")
            return False
        
        # spill_to_disk mode
        if not await self._can_spill_to_disk():
            # Fallback to drop if disk full
            logger.warning("Disk full, falling back to drop")
            return False
        
        serialized = self._serialize(item)
        return await self._write_spill_file(serialized)
```

**Behavior Matrix**:

| Queue State | Disk State | Action |
|-------------|------------|--------|
| Full | Has space | Spill to disk |
| Full | Low space | Drop + log warning |
| Full | No space | Drop + log error |

---

### 29.6 Clock Skew Detection & TTL Protection

**Problem**: System clock errors (NTP drift, manual changes) can cause all TTLs to expire simultaneously, triggering stampede even with probabilistic refresh.

**Fix - Clock Skew Detection**:

```python
@dataclass
class ClockSkewConfig:
    # Skew detection
    skew_warning_threshold_seconds: float = 5.0   # Warn if drift > 5s
    skew_protection_threshold_seconds: float = 10.0  # Activate protection > 10s
    
    # TTL protection
    ttl_extension_factor: float = 2.0  # Double TTL during skew
    max_skew_extension_duration: float = 300  # Max 5 min extension
    
    # Node comparison
    compare_with_nodes: bool = True
    min_nodes_for_comparison: int = 2

class ClockSkewDetector:
    """
    Detect system clock skew and protect against TTL stampede.
    """
    
    def __init__(self, config: ClockSkewConfig, coordinator=None):
        self.config = config
        self.coordinator = coordinator
        self._is_protection_active = False
        self._protection_start_time: Optional[float] = None
        self._local_clock_offset = 0.0  # Offset from "true" time
    
    async def detect_skew(self) -> float:
        """Detect clock skew by comparing with other nodes."""
        
        if not self.config.compare_with_nodes or not self.coordinator:
            # Fallback: compare with system monotonic time
            return self._detect_from_monotonic()
        
        # Compare with other nodes
        node_times = await self.coordinator.get_all_node_times()
        
        if len(node_times) < self.config.min_nodes_for_comparison:
            return self._detect_from_monotonic()
        
        # Calculate median time (assumed correct)
        all_times = [t for _, t in node_times]
        median_time = statistics.median(all_times)
        
        # Calculate skew
        local_time = time.time()
        skew = abs(local_time - median_time)
        
        return skew
    
    def _detect_from_monotonic(self) -> float:
        """Fallback skew detection using monotonic + wall time comparison."""
        
        # Monotonic time is immune to system clock changes
        # Compare wall clock delta with monotonic delta
        wall_before = self._last_wall_time
        mono_before = self._last_mono_time
        
        wall_now = time.time()
        mono_now = time.monotonic()
        
        wall_delta = wall_now - wall_before
        mono_delta = mono_now - mono_before
        
        # If wall delta differs significantly from mono delta, clock jumped
        skew = abs(wall_delta - mono_delta)
        
        self._last_wall_time = wall_now
        self._last_mono_time = mono_now
        
        return skew
    
    async def should_extend_ttl(self, current_ttl: float) -> tuple[float, bool]:
        """
        Check if TTL should be extended due to clock skew.
        Returns (new_ttl, was_extended).
        """
        
        skew = await self.detect_skew()
        
        # Update protection state
        if skew > self.config.skew_protection_threshold_seconds:
            if not self._is_protection_active:
                self._is_protection_active = True
                self._protection_start_time = time.time()
                logger.warning(f"Clock skew detected: {skew:.1f}s, activating TTL protection")
        elif self._is_protection_active:
            # Check if protection should expire
            elapsed = time.time() - self._protection_start_time
            if elapsed > self.config.max_skew_extension_duration:
                self._is_protection_active = False
                logger.info("Clock skew protection expired")
        
        # Extend TTL if protection active
        if self._is_protection_active:
            return current_ttl * self.config.ttl_extension_factor, True
        
        return current_ttl, False
    
    async def get_entry_ttl(self, entry: CacheEntry) -> float:
        """Get entry TTL with skew protection."""
        
        base_ttl = entry.expires_at - time.time()
        
        if base_ttl <= 0:
            return 0.0  # Already expired
        
        protected_ttl, extended = await self.should_extend_ttl(base_ttl)
        
        if extended:
            logger.debug(f"TTL extended due to skew: {base_ttl:.1f}s -> {protected_ttl:.1f}s")
        
        return protected_ttl
```

**Skew Detection Flow**:

```
1. Periodic check (every 60s)
         ↓
2. Compare local time with cluster median
         ↓
3. If drift > 10s → Activate protection
         ↓
4. All TTLs multiplied by 2x
         ↓
5. Auto-expire after 5 minutes or when skew resolved
```

---

## Gap Summary

| # | Feature | Severity | Status |
|---|---------|----------|--------|
| 1 | Cluster Consistency Layer | **CRITICAL** | Added |
| 2 | ReconciliationEngine Conflict Model | **CRITICAL** | Added |
| 3 | Backpressure Propagation | **HIGH** | Added |
| 4 | Cold-Start Amplification | **MEDIUM** | Added |
| 5 | Persistence Replay Safety | **HIGH** | Added |
| 6 | Memory Fragmentation | **MEDIUM** | Added |
| 7 | Causality Correlation | **MEDIUM** | Added |

## Remaining Risk Summary

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | Redis dependency | **CRITICAL** | Fallback modes (local_only/readonly/fail_fast) |
| R2 | Lock contention | **HIGH** | Hybrid local-first lock strategy |
| R3 | Warm-up sampling | **MEDIUM** | Frequency-based sampling from production logs |
| R4 | Slab size mismatch | **MEDIUM** | Configurable + adaptive slab sizing |
| R5 | Agent non-compliance | **HIGH** | Self-preservation mode (cache self-protects) |
| R6 | Metrics overhead | **MEDIUM** | Off-critical-path analysis, 10% sampling |
| R7 | Reconciliation drift | **HIGH** | Configurable interval + event triggers |
| R8 | Graceful shutdown | **HIGH** | 5-phase shutdown protocol |
| R9 | Node join cold-start | **MEDIUM** | Cluster-aware warm-up with hot entry sync |
| R10 | Partitioned vs Replicated | **HIGH** | Documented as partitioned model |

## Minor Issue Summary

| # | Issue | Fix |
|---|-------|-----|
| M1 | Self-preservation flapping | Min duration + cooldown + flapping threshold |
| M2 | Drift threshold too aggressive | Environment-specific + percentile-based |
| M3 | QueryLogCollector unspecified | Full component specification |
| M4 | local_locks memory leak | LRU pool + periodic cleanup |
| M5 | Disk spill without space check | Pre-check + fallback to drop |
| M6 | Clock skew TTL stampede | Detection + TTL extension protection |
