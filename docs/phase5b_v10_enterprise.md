# Phase 5B v10 - Planner & Task Decomposition (Enterprise Production Grade)

**Hoàn chỉnh tuyệt đối** - Complete Enterprise Orchestration System

## Overview

Phase 5B v10 implements a comprehensive enterprise-grade planner and task decomposition engine with 18+ chaos-tested resilience scenarios. This extends the Phase 5A durable workflow runtime with advanced orchestration capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enterprise Planner Layer                        │
├─────────────────────────────────────────────────────────────────┤
│  DeterministicReplay │ ExactlyOnce │ Saga │ Heartbeat │ Cancel  │
├─────────────────────────────────────────────────────────────────┤
│  Sharding │ Compaction │ Sticky │ MultiTenant │ Poison │ RBAC   │
├─────────────────────────────────────────────────────────────────┤
│  Integrity │ Versioning │ StateMachine │ ChaosTesting │ Metrics  │
├─────────────────────────────────────────────────────────────────┤
│                    Phase 5A Workflow Runtime                       │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Deterministic Replay (`deterministic_values.py`)

Ensures reproducible workflow execution:

```python
from src.core.runtime.enterprise import DeterministicValueGenerator

gen = DeterministicValueGenerator(workflow_id="wf-123")

timestamp = gen.now()       # Recorded timestamp
random = gen.random()       # Deterministic random [0, 1)
uuid = gen.uuid()           # Deterministic UUIDv5
choice = gen.choice(["a", "b", "c"])
```

**Features:**
- `ctx.now()`: Recorded timestamps
- `ctx.random()`: Seeded from workflow_id
- `ctx.uuid()`: UUID v5 deterministic
- All values stored for replay

### 2. Exactly-Once Side Effects (`exactly_once.py`)

Guarantees exactly-once semantics:

```python
from src.core.runtime.enterprise import (
    IdempotencyKeyGenerator,
    SideEffectRegistry,
    ExactlyOnceActivityExecutor,
)

key = IdempotencyKeyGenerator.generate("wf-1", "task-1", attempt=1)
# Output: "wf-1:task-1:1"
```

**Features:**
- Idempotency key: `{workflow_id}:{step_id}:{attempt}`
- Side effect registry with result caching
- Atomic state transitions

### 3. Activity Heartbeat & Lease (`heartbeat_lease.py`)

Long-running activity protection:

```python
from src.core.runtime.enterprise import ActivityHeartbeatManager

manager = ActivityHeartbeatManager(
    store=heartbeat_store,
    heartbeat_interval_seconds=10,
    lease_duration_seconds=30,
)

await manager.start_activity("act-1", "wf-1", "worker-1")
await manager.record_heartbeat("act-1", "worker-1")
abandoned = await manager.get_abandoned_activities()
```

**Features:**
- Heartbeat tracking per activity
- Lease expiration detection
- Automatic task reassignment

### 4. Cancellation Tree (`cancellation_tree.py`)

Hierarchical workflow cancellation:

```python
from src.core.runtime.enterprise import CancellationPolicy, CancellationTree

tree = CancellationTree("root-wf")
tree.add_workflow("root-wf", "child-wf-1")
tree.add_workflow("root-wf", "child-wf-2")

# Policies: CASCADE, DETACH, GRACEFUL, FORCE
```

**Features:**
- CASCADE: Cancel all sub-workflows
- DETACH: Only current workflow
- GRACEFUL: Wait for current activities
- FORCE: Immediate termination

### 5. Compensation / Saga (`compensation_saga.py`)

Distributed transaction handling:

```python
from src.core.runtime.enterprise import SagaCoordinator, CompensationConfig

config = CompensationConfig(max_attempts=3, initial_delay_seconds=1.0)
coordinator = SagaCoordinator(dlq, config)

# On failure, compensations run in reverse order
success, failed = await coordinator.compensate_saga(
    saga_id,
    compensation_registry,
)
```

**Features:**
- Reverse-order compensation
- Exponential backoff retry
- Dead letter queue for failures

### 6. Workflow Sharding (`workflow_sharding.py`)

Horizontal scaling:

```python
from src.core.runtime.enterprise import WorkflowPartitioner

partitioner = WorkflowPartitioner(num_shards=64)
key = partitioner.get_partition_key("tenant-1", "workflow-1")
# Output: PartitionKey(tenant_id="tenant-1", shard_id="shard_32")
```

**Features:**
- Consistent hashing ring
- Tenant-aware partitioning
- Minimal redistribution on changes

### 7. History Compaction (`history_compaction.py`)

Prevents event log explosion:

```python
from src.core.runtime.enterprise import ContinueAsNewManager

manager = ContinueAsNewManager(compactor, continue_as_new_enabled=True)

# Auto-triggers at max_events (default 2000)
result = await manager.continue_workflow(wf_id, state, events)
```

**Features:**
- Automatic Continue-As-New
- Event archival to cold storage
- State snapshot preservation

### 8. Sticky Execution (`sticky_execution.py`)

Replay optimization:

```python
from src.core.runtime.enterprise import StickyExecutionManager

manager = StickyExecutionManager(cache)
await manager.start_sticky("wf-1", "worker-1", state, events)
worker = await manager.get_sticky_worker("wf-1")
```

**Features:**
- Worker state caching
- Workflow affinity routing
- Cache TTL with LRU eviction

### 9. Multi-Tenant Isolation (`multi_tenant.py`)

Tenant resource management:

```python
from src.core.runtime.enterprise import MultiTenantQuotaManager

manager = MultiTenantQuotaManager(quota_store, usage_store)
check = await manager.check_workflow_allowed("tenant-1")

scheduler = WeightedFairScheduler(manager)
next_tenant = await scheduler.get_next_tenant(tenants)
```

**Features:**
- Per-tenant quotas
- Weighted fair queue scheduling
- Priority classes (CRITICAL to BATCH)

### 10. Poison Tool Defense (`poison_defense.py`)

Output sanitization and trust scoring:

```python
from src.core.runtime.enterprise import PoisonToolDefense

defense = PoisonToolDefense()
allowed, output, issues = await defense.process_output(
    "code_generator",
    tool_output,
    schema,
)

# quarantine_threshold: 0.3
# reject_threshold: 0.1
```

**Features:**
- Schema validation
- Dangerous content detection
- Trust score tracking
- Automatic quarantine

### 11. Lifecycle Retention (`lifecycle_retention.py`)

Workflow lifecycle management:

```python
from src.core.runtime.enterprise import LifecycleManager

manager = LifecycleManager(store)
await manager.complete("wf-1")
await manager.archive("wf-1")
results = await manager.process_retention()
# {"archived": 10, "purged": 5, "errors": 0}
```

**States:** RUNNING → COMPLETED → ARCHIVED → PURGED

### 12. RBAC Approval (`rbac_approval.py`)

Role-based human-in-the-loop:

```python
from src.core.runtime.enterprise import RBACApprovalEngine, Role

engine = RBACApprovalEngine(rbac)
request = await engine.create_approval_request(
    plan_id="plan-1",
    action=Permission.PLAN_APPROVE,
    requested_by="user-1",
    required_roles=[Role.SUPERVISOR],
)
```

**Features:**
- Role-based permissions
- Approval chains
- MFA support
- Escalation

### 13. Event Log Integrity (`event_integrity.py`)

Tamper-evident logging:

```python
from src.core.runtime.enterprise import EventIntegrityManager

manager = EventIntegrityManager()
chained = manager.compute_event_chain("wf-1", events)
result = manager.verify_workflow_chain("wf-1", chained)
```

**Features:**
- SHA256 hash chain
- Append-only log
- Tamper detection

### 14. Planner Determinism Versioning (`planner_versioning.py`)

Reproducible planning:

```python
from src.core.runtime.enterprise import DeterminismVersionManager

manager = DeterminismVersionManager()
artifacts = manager.capture_artifacts(
    plan_id="plan-1",
    model_version="gpt-4",
    prompt_template="...",
    temperature=0.7,
    retrieved_plans=["plan-2", "plan-3"],
    context={},
)

result = manager.verify_determinism(plan_id, **current_artifacts)
```

**Features:**
- Model version tracking
- Prompt hash
- Retrieval snapshot
- Context hash

### 15. Formal State Machines (`state_machine.py`)

Defined transitions:

```python
from src.core.runtime.enterprise import WorkflowStateMachine, WorkflowState

sm = WorkflowStateMachine()
sm.start()
sm.pause()
sm.resume()
sm.complete()

# Allowed transitions enforced
```

**Machines:**
- WorkflowStateMachine: CREATED → RUNNING → COMPLETED/FAILED/CANCELLED
- ActivityStateMachine: SCHEDULED → STARTED → COMPLETED/FAILED/TIMED_OUT
- CompensationStateMachine: PENDING → SCHEDULED → RUNNING → COMPLETED/FAILED

### 16. Chaos Testing (`chaos_tests.py`)

18+ resilience scenarios:

```python
from src.core.runtime.enterprise import ChaosTestSuite

suite = ChaosTestSuite()
results = await suite.run_all()
summary = suite.get_summary()

# All 18 tests pass with 100% pass rate
```

**Scenarios:**
1. Redis lock split-brain
2. Partial DB commit
3. Duplicate resume signal
4. Replay after schema migration
5. Clock skew
6. Network partition
7. Lost heartbeat
8. Event log corruption
9. Planner crash mid-execution
10. Tool output poisoning
11. Overload admission
12. Multi-tenant fairness
13. Compensation retry
14. Continue-As-New
15. Sticky worker crash
16. Shard rebalancing
17. RBAC denial
18. Event hash chain break

## Data Schemas

### workflow_events (sharded)
| Field | Type | Description |
|-------|------|-------------|
| event_id | str | Unique event ID |
| workflow_id | str | Workflow identifier |
| sequence | int | Event sequence |
| event_type | str | Event type |
| data | JSON | Event payload |
| previous_hash | str | SHA256 of previous event |
| timestamp | int | Unix timestamp |
| partition_key | str | tenant_id |

### activity_idempotency
| Field | Type |
|-------|------|
| idempotency_key | str (PK) |
| workflow_id | str |
| activity_id | str |
| result | JSON |
| created_at | int |

### activity_heartbeat
| Field | Type |
|-------|------|
| activity_id | str |
| workflow_id | str |
| last_heartbeat | int |
| lease_expiry | int |
| owner_worker | str |

### tenant_quotas
| Field | Type |
|-------|------|
| tenant_id | str |
| max_concurrent_workflows | int |
| max_daily_cost_usd | float |
| priority_class | int |
| isolation_group | str |

### planner_frozen_artifacts
| Field | Type |
|-------|------|
| plan_id | str |
| planner_model_version | str |
| prompt_hash | str |
| temperature | float |
| retrieval_snapshot_id | str |

## Configuration

```yaml
planner:
  exactly_once:
    enabled: true
    idempotency_table: "activity_idempotency"
    ttl_hours: 168

  deterministic_time:
    use_recorded_values: true
    random_seed_source: "workflow_id"

  activity_heartbeat:
    interval_seconds: 10
    lease_duration_seconds: 30

  cancellation:
    default_policy: "CASCADE"
    graceful_timeout_seconds: 60

  compensation:
    enabled: true
    retry_policy: {max_attempts: 3, backoff: "exponential"}

  sharding:
    enabled: true
    num_shards: 64

  compaction:
    max_events_before: 2000
    continue_as_new: true

  sticky_worker:
    enabled: true
    cache_ttl_seconds: 60

  multi_tenant:
    enabled: true
    fair_scheduling: "weighted_fair"

  poison_defense:
    sanitizer: "default"
    trust_score_initial: 0.8
    quarantine_threshold: 0.3
    reject_threshold: 0.1

  retention:
    completed_retention_days: 7
    archived_retention_days: 90

  rbac:
    enabled: true
    default_roles_required: ["user"]

  chaos_tests:
    enabled: true
    scenarios: 18
```

## Done Criteria

- [x] Exactly-once side effect (idempotency + registry)
- [x] Deterministic time & random replay
- [x] Heartbeat & lease protection
- [x] Cancellation tree policies
- [x] Compensation / Saga with retry, dead letter
- [x] Sharding & partitioning
- [x] Continue-As-New compaction
- [x] Sticky worker cache
- [x] Multi-tenant isolation + fair scheduling
- [x] Backpressure & admission control
- [x] Poison tool defense (sanitizer, trust score, quarantine)
- [x] Lifecycle retention & archival
- [x] RBAC approval
- [x] Event log integrity (hash chain)
- [x] Planner determinism versioning
- [x] 18+ chaos tests pass
- [x] Formal state machine with allowed transitions
- [x] All planner tests pass (45 tests)
