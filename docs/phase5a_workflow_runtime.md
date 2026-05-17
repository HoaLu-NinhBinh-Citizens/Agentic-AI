# Phase 5A - Durable Workflow Runtime (v7)

**Status**: Implementation Complete
**Date**: 2026-05-17
**Version**: v7

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core Concepts](#3-core-concepts)
4. [Deterministic Replay Contract](#4-deterministic-replay-contract)
5. [Side Effect API](#5-side-effect-api)
6. [Event Ordering Guarantees](#6-event-ordering-guarantees)
7. [Replay Optimization](#7-replay-optimization)
8. [Components](#8-components)
9. [API Reference](#9-api-reference)
10. [Configuration](#10-configuration)
11. [Error Handling](#11-error-handing)
12. [Done Criteria](#12-done-criteria)

---

## 1. Overview

Phase 5A implements a durable workflow runtime inspired by Temporal/Cadence patterns:

| Feature | Description |
|---------|-------------|
| **Event Sourcing** | Workflow state is event log; replay for recovery |
| **Deterministic** | Workflow code is pure orchestration; side effects in Activities |
| **Saga Pattern** | Compensation with state machine, idempotent retry |
| **At-Least-Once** | Activities may retry; must be idempotent |
| **Heartbeat & Lease** | Long-running activities send heartbeat to extend lease |
| **Signal Sequencing** | Signals ordered by sequence number; idempotent handling |
| **Parent Close Policy** | Child workflow policy when parent closes |
| **Distributed Lock** | Fencing tokens prevent split-brain |
| **Fair Scheduling** | Deficit Round Robin for CPU sharing |
| **Query Consistency** | Eventual or strong (replay) queries |
| **Deterministic Replay** | Command sequence verification, version patching |
| **Sticky Worker Cache** | Workflow affinity with cache invalidation |
| **Side Effect API** | Captures non-deterministic values for replay |
| **Replay Optimization** | Incremental, partial, checksum shortcuts |
| **Archive Retrieval** | Lazy restore, selective restore, verification |

---

## 2. Architecture

```
WorkflowRuntime
+-- WorkflowOrchestrator     # Deterministic workflow replay
+-- ActivityExecutor         # Side effects, heartbeat, lease
+-- CompensationStateMachine  # Idempotent Saga compensation
+-- EventStore              # Event sourcing
+-- SnapshotManager          # Periodic snapshots
+-- TaskQueue                # Claim-based execution
+-- SignalManager            # Sequenced signals, backpressure
+-- ChildWorkflowManager     # Parent close policy
+-- LockManager              # Distributed lock with fencing
+-- FairScheduler            # Deficit Round Robin
+-- AdmissionController       # Backpressure
+-- EventCompactor           # Terminal workflow compaction
+-- RetentionManager         # Cleanup old data
+-- MigrationHook            # Version migration
+-- StickyWorkerCache        # Workflow affinity cache
+-- VersionPatcher           # Replay-safe code upgrades
+-- ReplayOptimizer          # Incremental/partial replay
+-- ArchiveRetriever         # Archived workflow retrieval
+-- EventOrdering            # Event sequence guarantees
```

---

## 3. Core Concepts

### 3.1 Workflow vs Activity

**Workflow (Deterministic)**
- Orchestration logic only
- No I/O, no random, no wall-clock time
- Uses `WorkflowContext` to call Activities
- Replayed from event log on recovery

**Activity (Side Effect)**
- Performs actual work
- Can use I/O, random, time
- Must be idempotent
- Supports heartbeat and cancellation

### 3.2 Event Sourcing

Every state change is an event:

```python
WorkflowEvent(
    event_id="...",
    workflow_id="...",
    event_type="activity_completed",
    sequence=5,
    event_data={"activity_id": "...", "result": ...},
)
```

Replay: Replay events to reconstruct state.

Snapshot: Periodic snapshot to speed up replay.

### 3.3 Saga Compensation

When activity fails in a saga:

1. Activity marks compensation needed
2. Compensation scheduled with idempotency key
3. Compensator executes compensation
4. On failure: retry with backoff
5. After max retries: dead letter queue

### 3.4 Signal Sequencing

Signals are ordered:

```python
Signal(
    workflow_id="...",
    name="update",
    sequence=1,  # Monotonically increasing
    payload={...},
)
```

Handler checks sequence; duplicate signals are ignored.

---

## 4. Deterministic Replay Contract

This is the **core invariant** of durable execution.

### 4.1 Command Sequence Matching

**FUNDAMENTAL RULE**: During replay, the workflow MUST emit **exactly the same command sequence** as the original execution.

### 4.2 NonDeterministicWorkflowError

When command sequence mismatches during replay, throws `NonDeterministicWorkflowError`.

### 4.3 Command Verification Protocol

```
1. Load event history: [E1, E2, E3, ..., En]
2. Load current workflow code
3. Reset workflow state to initial
4. Replay events in order:
   FOR each event Ei:
     - Apply event to state
     - Continue workflow execution
     - Collect emitted commands
     - Verify command matches next historical command
5. IF mismatch: HALT, throw NonDeterministicWorkflowError
6. IF complete match: Continue normal execution
```

### 4.4 Version Patching API

For safe code upgrades without breaking replay:

#### get_version()

```python
version = ctx.get_version("pricing-update", min_version=1, max_version=2)
if version >= 2:
    price = await ctx.execute_activity("get_price_v2", {})
else:
    price = await ctx.execute_activity("get_price", {})
```

#### patched()

```python
if ctx.patched("new-shipping-logic"):
    result = await ctx.execute_activity("ship_v2", input)
else:
    result = await ctx.execute_activity("ship_v1", input)
```

### 4.5 Illegal Operations in Workflow

| Operation | Why Illegal | Correct Alternative |
|-----------|-------------|---------------------|
| `time.time()` | Wall-clock varies | `ctx.now()` |
| `random.random()` | Non-deterministic | `ctx.random()` |
| `uuid.uuid4()` | Non-deterministic | `ctx.uuid()` |
| `datetime.now()` | Wall-clock varies | `ctx.now()` |
| File I/O | Side effect | Activity call |
| `asyncio.sleep()` | Time-dependent | `ctx.sleep()` |

---

## 5. Side Effect API

### 5.1 ctx.side_effect()

Execute a side effect and cache result for replay.

**Protocol:**
1. **NEW EXECUTION**: Execute fn(), store result in history
2. **REPLAY**: Return cached result from history

```python
# Capture config snapshot
config = ctx.side_effect(lambda: load_config())

# Deterministic entropy
entropy = ctx.side_effect(lambda: ctx.random())

# Feature flag
flags = ctx.side_effect(lambda: fetch_flags(ctx.workflow_id))
```

### 5.2 ctx.mutable_side_effect()

Execute a mutable side effect with explicit ID.

Unlike side_effect(), this allows the function result to change across replays based on the provided ID.

```python
value = ctx.mutable_side_effect(
    lambda: expensive_or_nondeterministic(),
    id="unique-id-for-this-side-effect"
)
```

### 5.3 ctx.activity_execution_id

Get current activity execution ID for downstream deduplication.

```python
# In activity implementation:
execution_id = ctx.activity_execution_id
# Use for API deduplication, etc.
```

---

## 6. Event Ordering Guarantees

### 6.1 Formal Guarantees

| Guarantee | Description |
|-----------|-------------|
| **Strict Monotonicity** | seq(n) < seq(n+1) for all events |
| **Gap-Free Invariant** | No skipped sequence numbers |
| **Atomic Commit** | Event and state mutation committed together |
| **Serialization** | Only one writer at a time per workflow |
| **Durability Before ACK** | Event written before acknowledgment |

### 6.2 EventOrdering Implementation

```python
class EventOrdering:
    async def append_event(
        self,
        workflow_id: str,
        event_type: str,
        event_data: dict,
    ) -> WorkflowEvent:
        """Append event with guaranteed ordering."""
        
    async def verify_sequence_integrity(
        self,
        workflow_id: str,
    ) -> tuple[bool, List[int]]:
        """Verify gap-free sequence numbers."""
        
    async def verify_atomic_commit(
        self,
        workflow_id: str,
        sequence: int,
    ) -> bool:
        """Verify event is atomically committed with state."""
```

### 6.3 Concurrency Handling

When multiple events arrive simultaneously (signal, activity completion, cancellation):

```
Events are serialized under workflow lock:
1. Signal arrives -> queued
2. Activity completes -> queued  
3. Timer fires -> queued
4. Lock acquired -> events processed in order
5. Lock released -> next batch
```

---

## 7. Replay Optimization

### 7.1 Replay Strategies

| Strategy | Description |
|----------|-------------|
| **FULL** | Replay all events from beginning |
| **INCREMENTAL** | Resume from last checkpoint |
| **PARTIAL** | Replay only affected events |
| **CHECKSUM** | Skip if state unchanged |

### 7.2 ReplayOptimizer

```python
class ReplayOptimizer:
    async def create_checkpoint(
        self,
        workflow_id: str,
        version: str,
        sequence: int,
        state: dict,
    ) -> ReplayCheckpoint:
        """Create checkpoint for incremental replay."""
        
    async def plan_replay(
        self,
        workflow_id: str,
        version: str,
        strategy: ReplayStrategy = ReplayStrategy.INCREMENTAL,
    ) -> ReplayPlan:
        """Plan optimized replay."""
        
    async def execute_replay(
        self,
        workflow_id: str,
        plan: ReplayPlan,
        state: dict,
    ) -> dict:
        """Execute optimized replay."""
```

### 7.3 Checkpoint-Based Optimization

```
Workflow with 10,000 events:
- Full replay: ~1000ms
- Incremental (from checkpoint at 9000): ~100ms  
- Checksum shortcut (state unchanged): ~1ms
```

---

## 8. Components

### 8.1 WorkflowContext

Deterministic workflow orchestration:

```python
class WorkflowContext:
    # Activity execution
    async def execute_activity(
        self,
        activity_name: str,
        input: dict,
        options: ActivityOptions = None,
    ) -> Any:
        
    # Signal handling
    async def wait_for_signal(self, name: str, timeout_seconds: float = None) -> Any:
        
    # Child workflows
    async def start_child_workflow(
        self,
        name: str,
        input: dict,
        parent_close_policy: str = "TERMINATE",
    ) -> str:
        
    # Cancellation
    def is_cancelled(self) -> bool:
        
    # Version patching
    def get_version(self, change_id: str, min_version: int, max_version: int = None) -> int:
    def patched(self, feature_id: str) -> bool:
    
    # Side effects
    def side_effect(self, fn: Callable[[], Any]) -> Any:
    def mutable_side_effect(self, fn: Callable[[], Any], id: str) -> Any:
    
    # Deterministic operations
    def now(self) -> float:
    def sleep(self, seconds: float) -> None:
    def random(self) -> float:
    def uuid(self) -> str:
    
    # Activity deduplication
    @property
    def activity_execution_id(self) -> Optional[str]:
```

### 8.2 ActivityContext

Activity execution context:

```python
class ActivityContext:
    async def heartbeat(self, details: Any = None) -> None:
    def is_cancelled(self) -> bool:
```

### 8.3 CompensationStateMachine

Saga compensation with idempotent retry.

### 8.4 SignalManager

Sequenced, idempotent signals with backpressure:

```python
# Signal Backpressure Config:
max_pending_signals_per_workflow: 1000
signal_retention_days: 30
dedupe_ttl_seconds: 60
```

### 8.5 ChildWorkflowManager

Child workflows with close policy and cancellation propagation.

### 8.6 LockManager

Distributed lock with fencing and recovery semantics:

```python
# Recovery Semantics:
- Clock skew tolerance: 1.0s
- Partition recovery: pending locks transferred on reconnect
- Token monotonicity: via fencing
```

### 8.7 FairScheduler

Deficit Round Robin scheduling.

### 8.8 AdmissionController

Backpressure and limits.

### 8.9 StickyWorkerCache

Workflow affinity cache with LRU eviction.

### 8.10 StrongQueryExecutor

Strong consistency queries with lock + replay.

### 8.11 CancellationManager

Deep cancellation with propagation and escalation.

### 8.12 ArchiveRetriever

Archived workflow retrieval:

```python
class ArchiveRetriever:
    async def restore_workflow(
        self,
        workflow_id: str,
        from_sequence: int = 0,
        to_sequence: int = 0,
    ) -> List[Any]:
        """Restore archived events."""
        
    async def restore_event_stream(
        self,
        workflow_id: str,
        from_sequence: int = 0,
    ):
        """Async generator for streaming restore."""
```

### 8.13 MigrationManager

Migration with transactional boundary:

```python
# Transactional Boundary:
# 1. PREPARE: Save old_snapshot, create record (preparing)
# 2. EXECUTE: Transform state, validate
# 3. COMMIT: Save new snapshot, mark completed
# 4. ROLLBACK: Restore old_snapshot on failure
```

---

## 9. API Reference

### 9.1 Start Workflow

```python
async def start_workflow(
    workflow_type: str,
    input: dict,
    workflow_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    priority: int = 5,
    timeout_seconds: Optional[int] = None,
    parent_close_policy: str = "TERMINATE",
) -> str:
```

### 9.2 Send Signal

```python
async def send_signal(
    workflow_id: str,
    name: str,
    payload: Any,
    idempotency_key: Optional[str] = None,
) -> None:
    # Raises: SignalBackpressureError
```

### 9.3 Query Workflow

```python
async def query(
    workflow_id: str,
    query_name: str,
    args: dict,
    consistency: Literal["eventual", "strong"] = "eventual",
) -> Any:
```

### 9.4 Cancel Workflow

```python
async def cancel_workflow(
    workflow_id: str,
    reason: str = "",
    timeout_seconds: float = 10.0,
) -> CancellationResult:
```

### 9.5 Migrate Workflow

```python
async def migrate_workflow(
    workflow_id: str,
    target_version: str,
    migration_hook: Optional[Callable] = None,
) -> None:
```

---

## 10. Configuration

```yaml
workflow_runtime:
  store:
    type: "postgres"
    dsn: "${WORKFLOW_DB_DSN}"
    pool_size: 20

  event_sourcing:
    snapshot_interval_events: 100
    enable_snapshot: true

  task_queue:
    claim_timeout_seconds: 60
    poll_interval_seconds: 0.5
    max_parallel_workers: 50
    scheduling_algorithm: "deficit_round_robin"
    quantum_ms: 100

  activity:
    heartbeat_interval_seconds: 10
    lease_duration_seconds: 30
    max_heartbeat_timeout_seconds: 300
    max_result_size_bytes: 1048576  # 1MB limit

  retry:
    default_max_attempts: 3
    default_initial_delay_seconds: 1.0
    default_backoff_multiplier: 2.0

  workflow_retry:
    enabled: true
    default_max_attempts: 1
    default_initial_delay_seconds: 5.0
    strategy: "replay"

  distributed_lock:
    type: "redis"
    redis_url: "${REDIS_URL}"
    lock_timeout_seconds: 10
    fencing_enabled: true
    clock_skew_tolerance_seconds: 1.0

  admission_control:
    max_pending_workflows: 10000
    max_pending_tasks: 50000
    reject_policy: "fail"

  signal_backpressure:
    max_pending_signals_per_workflow: 1000
    signal_retention_days: 30
    dedupe_ttl_seconds: 60

  sticky_worker:
    enabled: true
    sticky_timeout_seconds: 10
    max_cache_size: 10000
    eviction_policy: "lru"

  cancellation:
    default_timeout_seconds: 10.0
    escalation_warning_seconds: 5.0

  replay_optimizer:
    checkpoint_ttl_seconds: 86400
    default_strategy: "incremental"

  archive:
    enabled: true
    archive_path: "s3://bucket/events/"
    verify_checksum: true

  retention:
    workflow_completed_retention_days: 7
    workflow_failed_retention_days: 7
    event_retention_days: 30

  compaction:
    enabled: true
    workflow_terminal_retention_days: 1
    archive_path: "s3://bucket/events/"

  migration:
    timeout_seconds: 300
    max_retry_attempts: 3
```

---

## 11. Error Handling

| Scenario | Handling |
|----------|----------|
| Activity failure | Retry with backoff; on max retries, compensation |
| Non-deterministic code | Fail workflow with NonDeterministicWorkflowError |
| Activity no heartbeat | Lease expires; task reassigned |
| Lock token mismatch | Operation rejected; fencing prevents split-brain |
| Resource exhausted | Reject new workflows/tasks |
| Compensator failure | Retry; move to dead letter after max retries |
| Signal backpressure | Reject signal with SignalBackpressureError |
| Cancellation timeout | Force terminate after escalation timeout |
| Activity result too large | Reject with ResultTooLargeError |
| Archive corrupted | Reject with ArchiveCorruptedError |
| Migration failure | Rollback to old_snapshot |

### 11.1 Dead Letter Queue

```python
item = await dead_letter.get(item_id)
await dead_letter.retry(item_id)  # Retry
await dead_letter.discard(item_id)  # Discard
```

---

## 12. Done Criteria

- [x] Workflow orchestration deterministic (only Activity calls)
- [x] Activity idempotent, with heartbeat, lease, reassign
- [x] Compensation state machine with idempotent retry
- [x] Event compaction for terminal workflows
- [x] ParentClosePolicy (TERMINATE, ABANDON, REQUEST_CANCEL)
- [x] Signal sequencing with idempotent handler
- [x] Distributed lock with fencing token
- [x] Query consistency (eventual/strong)
- [x] Migration hook for version upgrades
- [x] Deficit Round Robin scheduling
- [x] Admission control with backpressure
- [x] Cancellation semantics (cooperative)
- [x] Deterministic Replay Contract (command matching, NonDeterministicWorkflowError)
- [x] Version Patching API (get_version, patched)
- [x] Sticky Worker Cache (invalidation, eviction, ownership transfer)
- [x] Strong Query Mechanics (lock acquisition, replay)
- [x] Deep Cancellation Semantics (propagation, compensation, escalation)
- [x] Activity Result Size Limits (max_result_size_bytes)
- [x] Signal Backpressure (retention, max pending, dedupe)
- [x] **Side Effect API** (side_effect, mutable_side_effect)
- [x] **Event Ordering Formal Guarantees** (monotonicity, gap-free, atomicity)
- [x] **Replay Optimization** (incremental, partial, checksum)
- [x] **Activity Execution ID** (for downstream deduplication)
- [x] **Archive Retrieval** (lazy restore, selective restore, verification)
- [x] **LockManager Recovery** (clock skew, partition recovery)
- [x] **Migration Transactional Boundary** (rollback semantics)

---

## Files Structure

```
src/core/runtime/workflow/
+-- __init__.py              # Module exports
+-- types.py                  # Core types and enums
+-- workflow_context.py       # WorkflowContext, ActivityContext
+-- activity_executor.py      # Activity execution with heartbeat
+-- compensation.py          # Saga compensation state machine
+-- signal_manager.py        # Signal sequencing + backpressure
+-- child_workflow.py        # Child workflows with close policy
+-- lock_manager.py           # Distributed lock with fencing
+-- fair_scheduler.py         # Deficit Round Robin
+-- admission_controller.py   # Backpressure
+-- compaction.py            # Event compaction
+-- retention.py             # Retention policies
+-- migration.py             # Version migration with rollback
+-- sticky_cache.py         # Sticky worker cache
+-- strong_query.py          # Strong query mechanics
+-- cancellation.py          # Deep cancellation semantics
+-- version_patcher.py       # Version patching
+-- replay_verifier.py       # Command sequence verification
+-- event_ordering.py        # Event ordering guarantees
+-- replay_optimizer.py       # Replay optimization
+-- archival.py              # Archive retrieval
```
