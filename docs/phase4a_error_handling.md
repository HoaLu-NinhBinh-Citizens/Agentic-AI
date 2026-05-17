# Phase 4A – SemanticMemory Agent Error Handling Contract (v6)

**Status**: Implementation Complete
**Date**: 2026-05-17

## Overview

Tài liệu này định nghĩa cách AI Agent tương tác và xử lý lỗi của SemanticMemory system.

## Core Principle

All decisions must be derived from structured API state, not logs.

SemanticMemory là hệ thống:
- **best-effort**
- **silent-failure tolerant**
- **no-exception runtime**

## Agent Contract

Agent chỉ sử dụng **3 nguồn duy nhất**:

| Source | Type | Description |
|--------|------|-------------|
| `return value` | `bool` | `True` = success, `False` = failed/skipped/deduped |
| `memory.last_operation` | `MemoryOperation` | PRIMARY state source |
| `memory.health_check()` | `HealthStatus` | System health |

## NEVER Use Logs for Decision Making

Agents must **NOT** read logs for decision making. All decisions are based on structured state.

## API Contracts

### 1. Store API Contract

```python
success: bool = await memory.store_conversation(session_id, role, content)
```

#### Return Value

| Value | Meaning |
|-------|---------|
| `True` | Stored successfully |
| `False` | Failed OR skipped OR deduped OR no-memory |

#### last_operation State

```python
state = memory.last_operation
{
  "status": "success | failed | skipped | deduped | no_memory",
  "error_code": "string | null",       # e.g., "LIMIT_REACHED"
  "reason": "human readable explanation",
  "retryable": true | false,
  "dedup_parent_id": "string | null",
  "timestamp": 1234567890
}
```

### 2. Status Enum

| Status | Meaning | Agent Action |
|--------|---------|--------------|
| `success` | Write stored | Done |
| `failed` | System error | Check error_code, decide retry |
| `skipped` | Intentionally ignored | Done (non-blocking) |
| `deduped` | Already exists | Treat as SUCCESS |
| `no_memory` | System degraded | Continue without memory |

### 3. Error Code Enum

#### Retryable (TRANSIENT)

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `EMBEDDING_TIMEOUT` | Embedding request timed out | Retry max 2 times |
| `EMBEDDING_NETWORK_ERROR` | Network failure | Retry max 2 times |
| `OLLAMA_UNAVAILABLE` | Ollama service down | Retry max 2 times |
| `DB_CONNECTION_LOST` | Database connection lost | Retry max 2 times |

#### Non-retryable (PERMANENT)

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `DIMENSION_MISMATCH` | Embedding dimension changed | Do NOT retry |
| `LIMIT_REACHED` | Storage limit reached | Do NOT retry, alert system |
| `INVALID_INPUT` | Invalid input provided | Do NOT retry |
| `BLOOM_ERROR` | Bloom filter error | Do NOT retry |

#### Dedup

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `DUPLICATE_CONTENT` | Content already exists | Treat as SUCCESS |

#### System Degraded

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `NO_MEMORY_MODE` | System offline | Continue without memory |

## Store Decision Engine

### Step 1: Call store

```python
success = await memory.store_conversation(...)
```

### Step 2: If success == True

Done.

### Step 3: If success == False

Read the state:

```python
state = memory.last_operation
```

### Decision Rules

#### (A) Dedup Case (SAFE SUCCESS)

```python
if state.status == "deduped" or state.error_code == "DUPLICATE_CONTENT":
    # Treat as SUCCESS
    # Do NOT retry
    # Optionally use state.dedup_parent_id
```

#### (B) Limit Reached (FATAL)

```python
if state.error_code == "LIMIT_REACHED":
    # Do NOT retry
    # Action: stop writes, alert system
```

#### (C) Transient Errors (RETRYABLE)

```python
if state.error_code in {"EMBEDDING_TIMEOUT", "EMBEDDING_NETWORK_ERROR", 
                        "OLLAMA_UNAVAILABLE", "DB_CONNECTION_LOST"}:
    # Retry max 2 times
    # Backoff: 0.1s → 0.3s → 0.7s
```

#### (D) Permanent Errors (NO RETRY)

```python
if state.error_code == "DIMENSION_MISMATCH":
    # Do NOT retry
    # Action: stop memory writes, reinitialize if possible
```

#### (E) No-Memory Mode

```python
if state.status == "no_memory" or state.error_code == "NO_MEMORY_MODE":
    # System degraded
    # Action: continue agent normally, use local context only
```

#### (F) Unknown Failure

```python
# Retry 1 time only
# If still fail → fallback local memory
```

## Retry Policy

### Allowed Retries ONLY if:

```python
error_code in TRANSIENT_ERRORS
# EMBEDDING_TIMEOUT
# EMBEDDING_NETWORK_ERROR
# OLLAMA_UNAVAILABLE
# DB_CONNECTION_LOST
```

### Forbidden Retry Cases:

- `LIMIT_REACHED`
- `DIMENSION_MISMATCH`
- `NO_MEMORY_MODE`
- `DUPLICATE_CONTENT`

## Health Check Contract

```python
health = await memory.health_check()
```

### Response Structure

```python
{
  "status": "healthy | degraded | no_memory",
  "db": true | false,
  "embedding": true | false
}
```

### Status Meanings

| Status | Meaning | Agent Action |
|--------|---------|--------------|
| `healthy` | Full functionality | Proceed normally |
| `degraded` | Partial failure | Use fallback reasoning |
| `no_memory` | System offline | Use local context only |

### Important Rule

Call health check **ONLY before important writes**:

- User input memory
- Tool results
- Structured JSON
- Multi-paragraph content

## Retrieve Contract

```python
results = await memory.retrieve(query)
```

### Empty Result Handling

```python
if results == []:
    health = await memory.health_check()
    
    if health["status"] == "no_memory":
        # System offline
        use_fallback_reasoning()
    elif health["status"] == "healthy":
        # No relevant memory found
        relax_query()  # or proceed normally
    else:
        # degraded
        use_fallback_reasoning()
```

### Important Rule

Empty retrieval **≠ error**. It means "no relevant memory found".

## RAG Context Contract

```python
context = await memory.build_rag_context(query)
```

If empty string returned:
- **NOT an error**
- Means "no relevant context"

Agent behavior:
- Proceed normally
- Use base knowledge

## min_score Policy

| Scenario | min_score |
|----------|----------|
| Factual question | 0.7 |
| Normal RAG | 0.5 |
| Exploration | 0.4 |
| Unknown | 0.5 default |

## last_operation Default State

```python
memory.last_operation = None  # Initially
```

Rule:
- Do NOT retry based on missing state
- Treat as fresh session

## Dedup Semantics

```python
if state.status == "deduped":
    # Equivalent to success
    # No duplicate stored
    # Safe to continue
    # Optional: use state.dedup_parent_id for reference
```

## Retrieval Limitation

`retrieve()` is **probabilistic**. It does NOT guarantee full coverage of memory.

Causes of missing results:
- Small session data
- High min_score
- Embedding mismatch
- ANN approximation

Agent rule:
- Do NOT assume memory absence
- Try relaxed query before concluding

## No-Memory Mode

**Definition**: System is offline or degraded.

**Detection**:
```python
health.status == "no_memory"
```

**Agent behavior**:
- Continue reasoning
- Use local context only
- Avoid retries
- Optional caching

## Safe Patterns

### Pattern A – Safe Store

```python
for i in range(2):
    ok = await memory.store_conversation(...)
    if ok:
        break
    
    state = memory.last_operation
    if not state["retryable"]:
        break
    
    await asyncio.sleep(0.3 * (2 ** i))
```

### Pattern B – Fallback Store

```python
if not await memory.store_conversation(...):
    state = memory.last_operation
    if state.status == "deduped":
        pass  # Safe success
    else:
        local_cache.append(data)
```

### Pattern C – Safe Retrieve

```python
results = await memory.retrieve(query)

if not results:
    health = await memory.health_check()
    
    if health["status"] == "no_memory":
        use_local_context()
    else:
        relax_query()
```

### Pattern D – Health Check Before Write

```python
health = await memory.health_check()

if health["status"] == "no_memory":
    # Skip memory write, use local context
    return

if health["status"] == "degraded":
    # Proceed with caution, may fail
    pass

# Important write with fallback
try:
    await memory.store_conversation(...)
except:
    local_cache.append(data)
```

## Mental Model

SemanticMemory is:

> A probabilistic, best-effort semantic cache with partial recall guarantees

NOT:
- Database of truth
- Complete memory store
- Deterministic retrieval system

## Critical Rules

| Rule | Description |
|------|-------------|
| 1 | Never rely on logs |
| 2 | Always check return value |
| 3 | Always check last_operation when False |
| 4 | Dedup = success |
| 5 | Empty retrieval = valid state |
| 6 | No-memory mode ≠ error |
| 7 | Never block agent execution |

## Summary

This contract ensures:
- Deterministic agent behavior
- Safe failure handling
- Clear retry boundaries
- No silent ambiguity
- Production-grade resilience

## Implementation

| Component | File |
|-----------|------|
| SemanticMemory | `src/core/memory/semantic_memory.py` |
| EmbeddingService | `src/infrastructure/embeddings/embedding_service.py` |
| Tests | `tests/unit/test_semantic_memory_error_contract.py` |

---

## Phase 4B – Missing Critical Specifications

**Status**: Gap Analysis Identified
**Date**: 2026-05-17

---

## (1) Cluster Consistency Layer / Partitioning Strategy

### Problem

When deployed on K8s/multi-pod, the cache becomes a **distributed system**. Without coordination:

- Duplicate execution across nodes (anti-dogpile fails at cluster level)
- LRU inconsistency between nodes
- Stale cache serving outdated results
- No single-flight conflict resolution across instances

### Design: Shared-Nothing with Partitioning

```
┌─────────────────────────────────────────────────────────────┐
│                     Cluster View                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Node A   │  │ Node B   │  │ Node C   │                  │
│  │ Partition│  │ Partition│  │ Partition│                  │
│  │ Hash(A)  │  │ Hash(B)  │  │ Hash(C)  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│         ↖           ↑           ↗                          │
│         └───────────┼───────────┘                          │
│                     │                                       │
│              ┌──────▼──────┐                               │
│              │ Coordinator │                               │
│              │  (Redis/DB) │                               │
│              │  - Lock     │                               │
│              │  - Config   │                               │
│              └─────────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### Partitioning Strategy

#### Key Hashing

```python
def get_partition(key: str, num_partitions: int) -> int:
    """Consistent hashing for key distribution."""
    return hash(key) % num_partitions
```

#### Partition Assignment

| Strategy | Use Case | Pros | Cons |
|----------|----------|------|------|
| Hash-based | Uniform distribution | Simple, predictable | Rebalancing expensive |
| Consistent hashing | Dynamic scaling | Minimize reshuffle | More complex |
| Range-based | Time-series access | Good for temporal patterns | Hot spots |

### Multi-Node Coordination

#### Distributed Lock (Single-Flight)

```python
async def store_with_lock(key: str, value: Any) -> bool:
    lock_key = f"lock:{key}"
    lock_acquired = await redis.set(lock_key, node_id, nx=True, ex=5)
    
    if not lock_acquired:
        # Another node is writing - wait for result
        await wait_for_result(key, timeout=30)
        return True  # Treat as dedup
    
    try:
        return await do_store(key, value)
    finally:
        await redis.delete(lock_key)
```

#### Cross-Node Single-Flight Pattern

```
Request arrives at Node A
        │
        ▼
┌─────────────────────────┐
│ Check local cache       │
│ If hit → return         │
└─────────────────────────┘
        │ miss
        ▼
┌─────────────────────────┐
│ Acquire distributed lock │
│ (Redis/DB)              │
└─────────────────────────┘
        │ acquired
        ▼
┌─────────────────────────┐
│ Double-check other node │
│ may have populated      │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Execute tool call       │
│ Store result            │
│ Broadcast to cluster    │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Release lock            │
│ Notify waiting nodes    │
└─────────────────────────┘
```

### Shared LRU Strategy

#### Option A: Local LRU + Invalidation Broadcast

```python
# Each node has local LRU
# On eviction, broadcast invalidation
async def evict_and_broadcast(key: str):
    local_lru.evict(key)
    await redis.publish("cache_invalidation", {"key": key, "node": node_id})

# Subscribe to invalidation
async def on_invalidation(message):
    key = message["key"]
    if key in local_cache:
        local_cache.delete(key)  # Invalidate stale entry
```

#### Option B: Centralized LRU with Versioning

```python
# Coordinator tracks LRU order
# Nodes query before serving
async def get_with_version(key: str):
    entry, version = await redis.get_with_version(key)
    local_entry = local_cache.get(key)
    
    if local_entry and local_entry.version >= version:
        return local_entry  # Local is fresh
    
    return entry  # Use coordinator version
```

#### Option C: Hybrid (Recommended)

```python
class HybridLRU:
    def __init__(self):
        self.local = LRUCache(max_items=1000)
        self.coordinator = RedisCoordinator()
        self.local_only_threshold = 0.8  # 80% hits → stay local
    
    async def get(self, key: str):
        local = self.local.get(key)
        if local:
            self.local.hit(key)
            return local
        
        remote = await self.coordinator.get(key)
        if remote:
            self.local.set(key, remote)  # Populate local
            return remote
        
        return None
```

### Cluster Rebalancing

#### Rebalance Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Node join | New partition assignment | Migrate keys gradually |
| Node leave | Detect via heartbeat | Reassign partitions |
| Load skew | Ratio > 2:1 | Move hot keys |
| Periodic | Every 1 hour | Optimize distribution |

#### Rebalance Algorithm

```python
async def rebalance_cluster():
    # Step 1: Calculate target distribution
    target = calculate_even_distribution(num_nodes)
    
    # Step 2: Find hot keys (top 20% by access)
    hot_keys = await metrics.get_hot_keys()
    
    # Step 3: Migrate in batches
    for key in hot_keys:
        current_node = get_current_owner(key)
        target_node = target[key]
        
        if current_node != target_node:
            await migrate_key(key, current_node, target_node)
            await asyncio.sleep(0.1)  # Throttle to avoid overload
```

---

## (2) ReconciliationEngine – Conflict Model

### Problem

Vector-clock conflict resolver mentioned but not defined. This is where **silent inconsistency** occurs.

### Vector Clock Specification

#### Per-Key Vector Clock (Recommended)

```python
@dataclass
class VectorClock:
    """Vector clock for cache entry consistency."""
    clock: dict[str, int]  # node_id → counter
    
    def increment(self, node_id: str) -> VectorClock:
        """Increment local counter."""
        new_clock = self.clock.copy()
        new_clock[node_id] = new_clock.get(node_id, 0) + 1
        return VectorClock(new_clock)
    
    def merge(self, other: VectorClock) -> VectorClock:
        """Merge two vector clocks (take max of each component)."""
        merged = {}
        for node_id in set(self.clock.keys()) | set(other.clock.keys()):
            merged[node_id] = max(
                self.clock.get(node_id, 0),
                other.clock.get(node_id, 0)
            )
        return VectorClock(merged)
    
    def happens_before(self, other: VectorClock) -> bool:
        """Check if self happened before other."""
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
        """Check if concurrent modification."""
        return not (self.happens_before(other) or other.happens_before(self))
```

### Conflict Resolution Rules

#### Rule Matrix

| Scenario | Resolution Strategy | Policy |
|----------|-------------------|--------|
| Concurrent writes | Merge or Discard | Configurable per tool |
| Stale write | Auto-reject | Timestamp check |
| Node crash | Tombstone + GC | 24h retention |
| Network partition | Quorum write | 2/3 majority |

#### Resolution Strategies

```python
class ConflictResolutionStrategy(Enum):
    LAST_WRITE_WINS = "lww"           # Simple, fast
    MERGE_VALUES = "merge"            # For dicts/lists
    KEEP_ALL = "keep_all"             # Store both versions
    PRIORITY_NODE = "priority"        # Certain nodes win
    DISCARD = "discard"               # Throw away conflicts

# Per-tool configuration
TOOL_CONFLICT_STRATEGY = {
    "code_generation": ConflictResolutionStrategy.LAST_WRITE_WINS,
    "data_retrieval": ConflictResolutionStrategy.MERGE_VALUES,
    "file_operations": ConflictResolutionStrategy.DISCARD,
}
```

### Persistence Replay Semantics

#### Event Schema with Versioning

```python
@dataclass
class CacheEvent:
    """Versioned cache event for replay safety."""
    version: int = 1  # Schema version
    event_id: str     # UUID for idempotency
    event_type: str   # STORE, UPDATE, DELETE, INVALIDATE
    key: str
    value: Any
    vector_clock: VectorClock
    timestamp: float
    checksum: str     # SHA256 of payload
    node_id: str
```

#### Idempotency for Replay

```python
async def replay_event(event: CacheEvent, seen_ids: set[str]) -> bool:
    """Replay event with idempotency check."""
    if event.event_id in seen_ids:
        return False  # Already processed
    
    # Verify checksum
    expected_checksum = calculate_checksum(event)
    if expected_checksum != event.checksum:
        raise CorruptedEventError(event.event_id)
    
    # Apply event
    await apply_event(event)
    seen_ids.add(event.event_id)
    
    return True
```

#### Replay Ordering Guarantees

```python
class ReplayOrderGuarantee(Enum):
    CAUSAL = "causal"        # Respect vector clock ordering
    TOTAL = "total"          # Total order via sequence number
    EVENTUAL = "eventual"    # Eventually consistent
```

---

## (3) Backpressure Propagation Model

### Problem

Cache can overload but agent continues spamming → upstream collapse.

### Propagation Path

```
┌──────────────────────────────────────────────────────────────┐
│                    Backpressure Flow                          │
│                                                              │
│  ┌──────────┐   ┌────────────┐   ┌───────────┐   ┌───────┐ │
│  │ ToolCache │ ← │ ToolExecutor │ ← │  Agent    │ ← │ User  │ │
│  │          │   │            │   │           │   │ Input │ │
│  └────┬─────┘   └─────┬──────┘   └─────┬─────┘   └───────┘ │
│       │               │                │                     │
│       ▼               │                │                     │
│  ┌──────────┐         │                │                     │
│  │ OVERLOAD │ ────► │  THROTTLE      │ ────► │ REJECT     │ │
│  │ DETECTED │         │                │                     │
│  └──────────┘         │                │                     │
│       │               │                │                     │
│       ▼               ▼                ▼                     │
│  ┌──────────────────────────────────────────────┐           │
│  │         Backpressure Signal (async)           │           │
│  │  - Memory pressure > 80%                      │           │
│  │  - Queue depth > 100                          │           │
│  │  - Latency p99 > 500ms                        │           │
│  └──────────────────────────────────────────────┘           │
└──────────────────────────────────────────────────────────────┘
```

### Signal Types

```python
@dataclass
class BackpressureSignal:
    """Backpressure signal for propagation."""
    source: str              # Component generating signal
    severity: float          # 0.0 - 1.0 (0.5+ = throttle, 0.8+ = reject)
    metric: str              # memory_pressure, queue_depth, latency_p99
    current_value: float
    threshold: float
    timestamp: float

# Signal aggregation
@dataclass
class AggregatedBackpressure:
    overall_severity: float  # Max of all signals
    throttle_threshold: float = 0.5
    reject_threshold: float = 0.8
    affected_endpoints: list[str]
```

### Propagation Implementation

```python
class BackpressureManager:
    def __init__(self):
        self.signals: dict[str, BackpressureSignal] = {}
        self.throttle_threshold = 0.5
        self.reject_threshold = 0.8
    
    async def emit_signal(self, signal: BackpressureSignal):
        self.signals[signal.source] = signal
        severity = self._calculate_overall_severity()
        
        # Propagate to upstream
        if severity >= self.reject_threshold:
            await self._propagate_reject()
        elif severity >= self.throttle_threshold:
            await self._propagate_throttle(severity)
    
    async def _propagate_throttle(self, severity: float):
        """Throttle upstream requests."""
        throttle_ratio = (severity - self.throttle_threshold) / (self.reject_threshold - self.throttle_threshold)
        
        # Tell ToolExecutor to slow down
        await self.tool_executor.set_throttle(throttle_ratio)
        
        # Tell Agent to reduce request rate
        await self.agent.set_rate_limit(max_rps=100 * (1 - throttle_ratio))
    
    async def _propagate_reject(self):
        """Reject new requests."""
        await self.tool_executor.reject_new_requests()
        await self.agent.set_rejection_mode(True)
```

### Queue Management

```python
class BackpressureQueue:
    """Queue with backpressure support."""
    def __init__(self, max_size: int = 1000):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.backpressure_manager = BackpressureManager()
    
    async def put(self, item: Any, timeout: float = None):
        if self.queue.full():
            # Signal backpressure
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
    
    async def get(self, timeout: float = None) -> Any:
        item = await self.queue.get(timeout=timeout)
        
        # Adjust queue fill ratio feedback
        fill_ratio = self.queue.qsize() / self.queue.maxsize
        if fill_ratio > 0.8:
            await self.backpressure_manager.emit_signal(...)
        
        return item
```

---

## (4) Cold-Start Amplification Control

### Problem

Binary warm-up ON/OFF causes traffic spike amplification on cold start.

### Current State vs Ideal

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

### Progressive Readiness Model

```python
class ProgressiveWarmupState(Enum):
    INITIALIZING = "initializing"    # 0-20% - Shadow traffic only
    PARTIAL = "partial"              # 20-60% - 25% traffic
    SUBSTANTIAL = "substantial"      # 60-90% - 75% traffic
    READY = "ready"                  # 90-100% - Full traffic

@dataclass
class WarmupMetrics:
    cache_populated_pct: float
    index_ready_pct: float
    connection_pool_ready: bool
    embedding_service_ready: bool

@dataclass
class WarmupConfig:
    min_duration_seconds: float = 30.0      # Minimum warm-up time
    ramp_duration_seconds: float = 60.0      # Time to full readiness
    shadow_traffic_ratio: float = 0.05       # 5% traffic during init
    partial_traffic_ratio: float = 0.25      # 25% during partial
    metrics_polling_interval: float = 5.0   # Check every 5 seconds
```

### Warmup Readiness Calculator

```python
class WarmupReadinessCalculator:
    def calculate_readiness(self, metrics: WarmupMetrics) -> tuple[float, ProgressiveWarmupState]:
        """Calculate overall readiness (0.0 - 1.0)."""
        
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
    
    def _readiness_to_state(self, readiness: float) -> ProgressiveWarmupState:
        if readiness < 0.2:
            return ProgressiveWarmupState.INITIALIZING
        elif readiness < 0.6:
            return ProgressiveWarmupState.PARTIAL
        elif readiness < 0.9:
            return ProgressiveWarmupState.SUBSTANTIAL
        else:
            return ProgressiveWarmupState.READY
    
    def get_traffic_ratio(self, state: ProgressiveWarmupState) -> float:
        return {
            ProgressiveWarmupState.INITIALIZING: 0.0,      # Shadow only
            ProgressiveWarmupState.PARTIAL: 0.25,
            ProgressiveWarmupState.SUBSTANTIAL: 0.75,
            ProgressiveWarmupState.READY: 1.0,
        }[state]
```

### Shadow Traffic Pattern

```python
async def warmup_with_shadow_traffic():
    """Warm up cache using shadow traffic before accepting real requests."""
    calculator = WarmupReadinessCalculator()
    config = WarmupConfig()
    
    # Get representative queries for warm-up
    warmup_queries = await load_warmup_queries()
    
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        
        # Enforce minimum warm-up time
        if elapsed < config.min_duration_seconds:
            await asyncio.sleep(config.min_duration_seconds - elapsed)
        
        # Calculate readiness
        metrics = await collect_warmup_metrics()
        readiness, state = calculator.calculate_readiness(metrics)
        
        # Check if minimum time elapsed OR fully ready
        if elapsed >= config.min_duration_seconds and readiness >= 0.9:
            break
        
        # Execute shadow traffic at current ratio
        traffic_ratio = calculator.get_traffic_ratio(state)
        
        if traffic_ratio > 0:
            # Sample and execute queries without returning to users
            sample_size = int(len(warmup_queries) * traffic_ratio)
            sampled = random.sample(warmup_queries, sample_size)
            
            for query in sampled:
                # Execute but discard result
                await memory.retrieve(query, shadow=True)
        
        await asyncio.sleep(config.metrics_polling_interval)
    
    return ProgressiveWarmupState.READY
```

### Gradual Ramp-Up

```python
class GradualRampUpController:
    def __init__(self, config: WarmupConfig):
        self.config = config
        self.current_traffic_ratio = 0.0
    
    def calculate_traffic_ratio(self, elapsed_seconds: float, readiness: float) -> float:
        """Calculate allowed traffic ratio based on time and readiness."""
        
        # Time-based progress
        time_ratio = min(1.0, elapsed_seconds / self.config.ramp_duration_seconds)
        
        # Readiness-based progress
        readiness_ratio = readiness
        
        # Use the lower (conservative)
        base_ratio = min(time_ratio, readiness_ratio)
        
        # Apply traffic ratios for each state
        if base_ratio < 0.2:
            return 0.0
        elif base_ratio < 0.6:
            return self.config.partial_traffic_ratio
        elif base_ratio < 0.9:
            return 0.75
        else:
            return 1.0
    
    async def should_accept_request(self) -> tuple[bool, float]:
        """Decide if request should be accepted and return confidence."""
        
        if self.current_traffic_ratio >= 1.0:
            return True, 1.0
        
        # Stochastic acceptance
        accepted = random.random() < self.current_traffic_ratio
        return accepted, self.current_traffic_ratio
```

---

## (5) Persistence Replay Safety

### Problem

Append-only log specified but missing safety guarantees for replay.

### Event Schema with Versioning

```python
CURRENT_SCHEMA_VERSION = 3

@dataclass
class CacheEvent:
    """Versioned cache event with safety guarantees."""
    version: int                    # Schema version for migrations
    event_id: str                   # UUID for idempotency
    event_type: str                 # STORE, UPDATE, DELETE, INVALIDATE, TOMBSTONE
    key: str                        # Cache key
    value: Optional[Any]            # Value (None for DELETE)
    metadata: dict                 # Additional metadata
    vector_clock: dict[str, int]    # Vector clock for consistency
    timestamp: float                # Wall clock time
    sequence_number: int            # Monotonic sequence for total order
    checksum: str                   # SHA256 of [event_id + event_type + key + value]
    previous_checksum: str         # Hash chain for tampering detection
    node_id: str                    # Originating node
    is_tombstone: bool              # Soft delete marker
```

### Schema Versioning & Migration

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

### Idempotency Key

```python
class IdempotencyStore:
    """Store processed event IDs for replay safety."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.processed_prefix = "idempotency:"
        self.ttl_hours = 24
    
    async def is_processed(self, event_id: str) -> bool:
        """Check if event was already processed."""
        return await self.redis.exists(f"{self.processed_prefix}{event_id}")
    
    async def mark_processed(self, event_id: str):
        """Mark event as processed."""
        await self.redis.set(
            f"{self.processed_prefix}{event_id}",
            "1",
            ex=self.ttl_hours * 3600
        )
    
    async def process_event(self, event: CacheEvent) -> bool:
        """Process event with idempotency check."""
        if await self.is_processed(event.event_id):
            return False  # Already processed
        
        await self.mark_processed(event.event_id)
        await self.apply_event(event)
        return True
```

### Corruption Detection

```python
class CorruptionDetector:
    """Detect corruption in persistence layer."""
    
    @staticmethod
    def verify_checksum(event: CacheEvent) -> bool:
        """Verify event checksum."""
        expected = event.checksum
        actual = CorruptionDetector.calculate_checksum(event)
        return expected == actual
    
    @staticmethod
    def calculate_checksum(event: CacheEvent) -> str:
        """Calculate SHA256 checksum of event payload."""
        payload = f"{event.event_id}|{event.event_type}|{event.key}|{json.dumps(event.value)}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    @staticmethod
    def verify_hash_chain(events: list[CacheEvent]) -> bool:
        """Verify hash chain integrity (previous_checksum linkage)."""
        previous_checksum = "GENESIS"  # Initial value
        
        for event in events:
            if event.previous_checksum != previous_checksum:
                return False  # Chain broken
            
            previous_checksum = event.checksum
        
        return True
    
    async def full_audit(self, events: list[CacheEvent]) -> AuditResult:
        """Full integrity audit of event stream."""
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

### Replay Ordering Guarantees

```python
class ReplayOrderGuarantee(Enum):
    CAUSAL = "causal"        # Respect vector clock ordering
    TOTAL = "total"          # Total order via sequence number
    EVENTUAL = "eventual"    # Eventually consistent

class SafeReplayer:
    """Safe replay with ordering guarantees."""
    
    def __init__(self, guarantee: ReplayOrderGuarantee):
        self.guarantee = guarantee
    
    async def replay_events(
        self,
        events: list[CacheEvent],
        idempotency_store: IdempotencyStore
    ) -> ReplayResult:
        """Replay events with safety guarantees."""
        
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
        
        return ReplayResult(
            applied=applied,
            skipped=skipped,
            errors=errors
        )
    
    def _causal_sort(self, events: list[CacheEvent]) -> list[CacheEvent]:
        """Topological sort based on vector clocks."""
        # Group concurrent events by key
        by_key: dict[str, list[CacheEvent]] = {}
        for event in events:
            by_key.setdefault(event.key, []).append(event)
        
        # Sort each key's events
        sorted_events = []
        for key_events in by_key.values():
            sorted_events.extend(self._sort_key_events(key_events))
        
        return sorted_events
    
    def _sort_key_events(self, events: list[CacheEvent]) -> list[CacheEvent]:
        """Sort events for a single key by causality."""
        sorted_list = []
        remaining = events.copy()
        
        while remaining:
            for i, event in enumerate(remaining):
                can_apply = all(
                    self._happens_before(e, event)
                    for e in sorted_list
                )
                if can_apply:
                    sorted_list.append(event)
                    remaining.pop(i)
                    break
            else:
                # Concurrent events - use sequence number tiebreaker
                remaining.sort(key=lambda e: e.sequence_number)
                sorted_list.extend(remaining)
                break
        
        return sorted_list
```

---

## (6) Memory Fragmentation Strategy

### Problem

LRU + byte limit exists but fragmentation causes OOM despite "theoretical memory OK".

### Fragmentation Model

```python
@dataclass
class MemoryFragmentationMetrics:
    """Track fragmentation state."""
    total_allocated_bytes: int
    total_used_bytes: int
    largest_free_block: int
    num_free_blocks: int
    fragmentation_ratio: float  # 0.0 (perfect) to 1.0 (severe)
    
    @property
    def wasted_bytes(self) -> int:
        """Bytes lost to fragmentation."""
        return self.total_allocated_bytes - self.total_used_bytes
    
    @property
    def is_fragmented(self) -> bool:
        """Check if fragmentation is problematic."""
        return self.fragmentation_ratio > 0.3  # >30% wasted
```

### Fragmentation Calculation

```python
class FragmentationCalculator:
    """Calculate memory fragmentation metrics."""
    
    def calculate_metrics(self, memory_stats: dict) -> MemoryFragmentationMetrics:
        """Calculate fragmentation from memory stats."""
        
        total_allocated = memory_stats.get("allocated_bytes", 0)
        total_used = memory_stats.get("used_bytes", 0)
        
        # Simulate free blocks analysis
        free_blocks = self._simulate_free_blocks(memory_stats)
        
        largest_free = max((b.size for b in free_blocks), default=0)
        num_free = len(free_blocks)
        
        # Fragmentation ratio: wasted / allocated
        fragmentation = (total_allocated - total_used) / total_allocated if total_allocated > 0 else 0
        
        return MemoryFragmentationMetrics(
            total_allocated_bytes=total_allocated,
            total_used_bytes=total_used,
            largest_free_block=largest_free,
            num_free_blocks=num_free,
            fragmentation_ratio=fragmentation
        )
```

### Slab Allocator Strategy

```python
class SlabAllocator:
    """Slab allocation to reduce fragmentation."""
    
    SLAB_SIZES = [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]  # Bytes
    
    def __init__(self):
        self.slabs: dict[int, list[MemoryBlock]] = {size: [] for size in self.SLAB_SIZES}
        self.slab_usage: dict[int, int] = {size: 0 for size in self.SLAB_SIZES}
        self.max_slab_fill = 0.8  # 80% fill before allocating new slab
    
    def allocate(self, size: int) -> MemoryBlock:
        """Allocate memory from appropriate slab."""
        slab_size = self._best_fit_size(size)
        
        # Try to use existing slab block
        if self.slabs[slab_size]:
            block = self.slabs[slab_size].pop()
            block.in_use = True
            return block
        
        # Allocate new slab if under limit
        if self.slab_usage[slab_size] < self.max_slab_fill * SLAB_SIZE:
            return self._create_new_slab_block(slab_size)
        
        # Fall back to direct allocation
        return self._direct_allocate(size)
    
    def _best_fit_size(self, size: int) -> int:
        """Find smallest slab that fits."""
        for slab_size in self.SLAB_SIZES:
            if slab_size >= size:
                return slab_size
        return self.SLAB_SIZES[-1]  # Max slab
    
    def release(self, block: MemoryBlock):
        """Return block to slab pool."""
        block.in_use = False
        slab_size = block.size
        
        # Reset block data
        block.data = None
        
        # Return to slab
        self.slabs[slab_size].append(block)
```

### Large Object Eviction Penalty

```python
class LargeObjectEvictionPolicy:
    """Penalize large objects in eviction decisions."""
    
    LARGE_OBJECT_THRESHOLD = 1024  # 1KB
    
    def calculate_eviction_score(
        self,
        entry: CacheEntry,
        lru_score: float,
        size_bytes: int
    ) -> float:
        """
        Calculate eviction score with large object penalty.
        Higher score = more likely to evict.
        """
        
        # Base score from LRU (0.0 = newest, 1.0 = oldest)
        score = lru_score
        
        # Large object penalty (0.0 - 0.3)
        if size_bytes > self.LARGE_OBJECT_THRESHOLD:
            # Exponential penalty for very large objects
            size_ratio = size_bytes / self.LARGE_OBJECT_THRESHOLD
            penalty = min(0.3, 0.1 * (size_ratio - 1))
            score += penalty
        
        # Frequent access penalty reduction (don't evict hot large objects easily)
        if entry.access_count > 10:
            score *= 0.8  # 20% reduction
        
        return score
    
    def should_evict_large_object(
        self,
        entry: CacheEntry,
        memory_pressure: float
    ) -> bool:
        """
        Decide if large object should be evicted.
        Only evict if under severe memory pressure.
        """
        
        if memory_pressure < 0.9:
            return False  # Not enough pressure
        
        # Under severe pressure, evict largest first
        return True
```

### Defragmentation Trigger

```python
class DefragmentationManager:
    """Manage memory defragmentation."""
    
    def __init__(self):
        self.fragmentation_threshold = 0.4
        self.check_interval = 300  # 5 minutes
    
    async def should_defragment(self, metrics: MemoryFragmentationMetrics) -> bool:
        """Check if defragmentation should run."""
        return (
            metrics.fragmentation_ratio > self.fragmentation_threshold and
            metrics.is_fragmented
        )
    
    async def defragment(self, cache: LRUCache) -> DefragResult:
        """Compact memory by rewriting fragmented entries."""
        
        # Phase 1: Snapshot current state
        entries = list(cache.entries.items())
        
        # Phase 2: Clear and rebuild
        cache.clear()
        
        # Phase 3: Re-insert in optimal order
        for key, entry in sorted(entries, key=lambda x: x[1].size, reverse=True):
            cache.set(key, entry.value, entry.metadata)
        
        return DefragResult(
            entries_moved=len(entries),
            memory_freed=0,  # Calculated by caller
            duration=0
        )
```

---

## (7) MetricsEngine – Causality Correlation

### Problem

Current metrics (hit ratio, pressure, pending) lack causality tracing.

### Required Metrics

```python
@dataclass
class CausalityMetrics:
    """Metrics with causality correlation."""
    
    # Per-tool metrics
    per_tool_hits: dict[str, int]
    per_tool_misses: dict[str, int]
    per_tool_latency: dict[str, LatencyBreakdown]
    per_tool_errors: dict[str, ErrorBreakdown]
    
    # Latency breakdown
    latency_breakdown: LatencyBreakdown
    
    # Anomaly detection
    anomaly_signals: list[AnomalySignal]
    
@dataclass
class LatencyBreakdown:
    """Latency breakdown for causal analysis."""
    cache_lookup_ms: float
    tool_execution_ms: float
    embedding_generation_ms: float
    serialization_ms: float
    total_ms: float
    
@dataclass
class ErrorBreakdown:
    """Error breakdown by cause."""
    network_errors: int
    timeout_errors: int
    validation_errors: int
    resource_errors: int
    
@dataclass
class AnomalySignal:
    """Anomaly detected in metrics."""
    type: str                      # "sudden_miss_spike", "latency_spike", etc.
    severity: float                 # 0.0 - 1.0
    probable_cause: str            # Likely cause
    affected_metrics: list[str]    # Which metrics triggered
    timestamp: float
```

### Per-Tool Causality Tracing

```python
class PerToolCausalityTracer:
    """Trace causality per tool execution."""
    
    def __init__(self):
        self.tool_traces: dict[str, list[ToolTrace]] = {}
        self.correlation_window = 60  # seconds
    
    async def trace_execution(
        self,
        tool_name: str,
        cache_hit: bool,
        latency_ms: float,
        error: Optional[Exception]
    ) -> ToolTrace:
        """Record tool execution with causality data."""
        
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
        
        # Detect anomalies
        await self._check_anomalies(tool_name)
        
        return trace
    
    def _capture_memory_state(self) -> dict:
        """Capture memory state at trace time."""
        return {
            "pressure": get_memory_pressure(),
            "lru_size": get_lru_size(),
            "pending_keys": get_pending_key_count()
        }
    
    async def _check_anomalies(self, tool_name: str):
        """Check for anomalies in recent traces."""
        recent = self._get_recent_traces(tool_name)
        
        # Sudden miss spike
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

### Latency Breakdown Analysis

```python
class LatencyAnalyzer:
    """Breakdown latency into causal components."""
    
    async def analyze_latency(
        self,
        request_start: float,
        request_end: float,
        cache_lookup_time: float,
        embedding_time: float,
        tool_execution_time: float
    ) -> LatencyBreakdown:
        """Break down total latency into components."""
        
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
        """Identify the main bottleneck from breakdown."""
        components = {
            "cache_lookup": breakdown.cache_lookup_ms,
            "embedding_generation": breakdown.embedding_generation_ms,
            "tool_execution": breakdown.tool_execution_ms,
            "serialization": breakdown.serialization_ms
        }
        
        return max(components, key=components.get)
```

### Anomaly Detection

```python
class AnomalyDetector:
    """Detect anomalies in metrics using statistical methods."""
    
    def __init__(self):
        self.baseline_windows: dict[str, list[float]] = {}
        self.baseline_window_size = 100
        self.zscore_threshold = 3.0
    
    async def detect_anomalies(
        self,
        current_metrics: dict[str, float]
    ) -> list[AnomalySignal]:
        """Detect anomalies using z-score method."""
        
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
            
            # Update baseline window
            window.append(current_value)
            if len(window) > self.baseline_window_size:
                window.pop(0)
        
        return anomalies
    
    def _infer_cause(self, metric_name: str, zscore: float) -> str:
        """Infer probable cause from anomaly pattern."""
        
        causes = {
            "hit_rate": "cache_pollution or TTL misconfiguration",
            "miss_count": "cold_start or cache_invalidation_storm",
            "latency_p99": "memory_pressure or embedding_service_slowdown",
            "memory_pressure": "memory_leak or large_object_accumulation",
            "pending_keys": "embedding_service_unavailable or timeout_flood"
        }
        
        return causes.get(metric_name, "unknown_cause")
```

### Correlation Dashboard Data

```python
class CausalityDashboard:
    """Generate dashboard data for causality analysis."""
    
    def generate_report(
        self,
        tracer: PerToolCausalityTracer,
        latency_analyzer: LatencyAnalyzer,
        anomaly_detector: AnomalyDetector
    ) -> dict:
        """Generate comprehensive causality report."""
        
        return {
            "per_tool_summary": {
                tool: {
                    "total_requests": len(traces),
                    "hit_rate": sum(1 for t in traces if t.cache_hit) / len(traces),
                    "avg_latency_ms": statistics.mean(t.latency_ms for t in traces),
                    "p99_latency_ms": self._percentile([t.latency_ms for t in traces], 99),
                    "error_rate": sum(1 for t in traces if t.error_type) / len(traces)
                }
                for tool, traces in tracer.tool_traces.items()
            },
            
            "latency_breakdown_summary": {
                "cache_lookup_avg": statistics.mean(...),
                "embedding_avg": statistics.mean(...),
                "tool_execution_avg": statistics.mean(...),
                "bottleneck_distribution": self._bottleneck_histogram(latency_analyzer)
            },
            
            "anomalies": anomaly_detector.detected_anomalies,
            
            "correlations": self._find_correlations(tracer)
        }
    
    def _find_correlations(self, tracer: PerToolCausalityTracer) -> list[dict]:
        """Find correlated metrics for causality analysis."""
        correlations = []
        
        # Example: Memory pressure vs hit rate correlation
        for tool, traces in tracer.tool_traces.items():
            pressures = [t.memory_state["pressure"] for t in traces]
            hit_rates = [1 if t.cache_hit else 0 for t in traces]
            
            if len(pressures) >= 10:
                correlation = self._pearson_correlation(pressures, hit_rates)
                if abs(correlation) > 0.5:
                    correlations.append({
                        "metric_a": "memory_pressure",
                        "metric_b": "hit_rate",
                        "tool": tool,
                        "correlation": correlation
                    })
        
        return correlations
```

---

## Gap Summary

| # | Gap | Severity | Impact |
|---|-----|----------|--------|
| 1 | Cluster Consistency Layer | **CRITICAL** | Duplicate execution, stale cache |
| 2 | Conflict Model (ReconciliationEngine) | **CRITICAL** | Silent inconsistency |
| 3 | Backpressure Propagation | **HIGH** | Cache overload, upstream collapse |
| 4 | Cold-Start Amplification | **MEDIUM** | Traffic spike on startup |
| 5 | Persistence Replay Safety | **HIGH** | Corrupted replay, divergence |
| 6 | Memory Fragmentation | **MEDIUM** | OOM despite available memory |
| 7 | Causality Correlation | **MEDIUM** | Hard to debug, no root cause |

## Recommended Implementation Order

1. **Phase 1** (Immediate): #1 Cluster Consistency, #3 Backpressure
2. **Phase 2** (Soon): #2 Conflict Model, #5 Persistence Safety
3. **Phase 3** (Next): #4 Cold-Start, #6 Fragmentation
4. **Phase 4** (Later): #7 Causality Correlation
