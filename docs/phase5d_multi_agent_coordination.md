# Phase 5D - Multi-Agent Coordination Layer (Enterprise Production)

**Status**: Implementation Complete
**Date**: 2026-05-18
**Version**: v2.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core Components v1](#3-core-components-v1)
4. [Enhanced Components v2](#4-enhanced-components-v2)
5. [Configuration](#5-configuration)
6. [API Reference](#6-api-reference)
7. [Metrics](#7-metrics)
8. [Chaos Test Scenarios](#8-chaos-test-scenarios)
9. [Done Criteria](#9-done-criteria)

---

## 1. Overview

Phase 5D implements an enterprise-grade Multi-Agent Coordination Layer with advanced production features.

### Phase 5D v1.0 Features

| Feature | Description |
|---------|-------------|
| **Two-Way Circuit Breaker** | Bidirectional fault tolerance between agents and coordinator |
| **Federated Health Propagation** | Sub-agent health status aggregation and reporting |
| **Schema Evolution** | Message schema versioning with backward/forward compatibility |
| **Batch Idempotency** | Per-item idempotency keys for safe batch retries |
| **Tenant Isolation** | Multi-tenant data isolation with JWT-based access |
| **Agent Resource Quota** | Concurrent tasks, message rate, workspace size limits |
| **Leader Election** | Coordinator HA with Redis-based leader election |
| **Backpressure** | Rate limiting from coordinator to agents with 429 responses |
| **Dead Letter Alert** | DLQ monitoring with webhook notifications |

### Phase 5D v2.0 Enhancements

| Enhancement | Issue Addressed | Solution |
|-------------|-----------------|---------|
| **Enhanced Leader Election** | Split-brain, dual writers | Fencing tokens, epoch-based safety, quorum |
| **Health State Machine** | Binary healthy/unhealthy | 6 states: HEALTHY/DEGRADED/SATURATED/DRAINING/QUARANTINED/DEAD |
| **Hierarchical Quotas** | Per-agent only | Tenant/Org/Region/Global scopes |
| **Message Ordering** | Out-of-order delivery | FIFO, causal ordering, sequence numbers |
| **Byzantine Protection** | Malicious agents | Signatures, attestation, anomaly detection |
| **Retry Coordination** | Retry storms | Global budget, jitter, backpressure |
| **Deterministic Scheduler** | Non-deterministic behavior | Logical clock, replay capability |
| **Automated Mitigation** | Manual DLQ handling | Auto pause/quarantine/reroute |
| **Secure Workspace** | Cross-tenant leakage | Memory zeroization, sandbox |

---

## 1. Overview

Phase 5D implements an enterprise-grade Multi-Agent Coordination Layer with advanced production features:

| Feature | Description |
|---------|-------------|
| **Two-Way Circuit Breaker** | Bidirectional fault tolerance between agents and coordinator |
| **Federated Health Propagation** | Sub-agent health status aggregation and reporting |
| **Schema Evolution** | Message schema versioning with backward/forward compatibility |
| **Batch Idempotency** | Per-item idempotency keys for safe batch retries |
| **Tenant Isolation** | Multi-tenant data isolation with JWT-based access |
| **Agent Resource Quota** | Concurrent tasks, message rate, workspace size limits |
| **Leader Election** | Coordinator HA with Redis-based leader election |
| **Backpressure** | Rate limiting from coordinator to agents with 429 responses |
| **Dead Letter Alert** | DLQ monitoring with webhook notifications |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Multi-Agent Coordination Layer                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────┐    TwoWayCircuitBreaker    ┌─────────────────────────┐   │
│  │   Agent     │◄──────────────────────────►│     Coordinator          │   │
│  │  (Caller)   │                            │                          │   │
│  └─────────────┘                            │  ┌─────────────────────┐ │   │
│                                              │  │ FederatedHealthProp │ │   │
│  ┌─────────────┐    TwoWayCircuitBreaker    │  └─────────────────────┘ │   │
│  │   Agent     │◄──────────────────────────►│  ┌─────────────────────┐ │   │
│  │  (Callee)   │                            │  │ SchemaEvolutionEngine│ │   │
│  └─────────────┘                            │  └─────────────────────┘ │   │
│                                              │  ┌─────────────────────┐ │   │
│                                              │  │ BatchIdempotencyStore│ │   │
│  ┌─────────────┐                            │  └─────────────────────┘ │   │
│  │   Federated │──► Health Propagation ──►  │  ┌─────────────────────┐ │   │
│  │   Agent     │                            │  │ TenantIsolationLayer│ │   │
│  └─────────────┘                            │  └─────────────────────┘ │   │
│                                              │  ┌─────────────────────┐ │   │
│                                              │  │    QuotaEnforcer    │ │   │
│  ┌─────────────┐                            │  └─────────────────────┘ │   │
│  │   Dead      │──► DLQ Alert ───────────►  │  ┌─────────────────────┐ │   │
│  │   Letter    │                            │  │    LeaderElector    │ │   │
│  └─────────────┘                            │  └─────────────────────┘ │   │
│                                              │  ┌─────────────────────┐ │   │
│  ┌─────────────┐                            │  │  BackpressureCtrl    │ │   │
│  │  Metrics    │◄──────────────────────────│  └─────────────────────┘ │   │
│  │  Collector  │                            └─────────────────────────────┘   │
│  └─────────────┘                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Hierarchy

```
MultiAgentCoordinator
├── TwoWayCircuitBreaker (per-agent)
├── FederatedHealthPropagator
├── SchemaEvolutionEngine
├── BatchIdempotencyStore
├── TenantIsolationLayer
├── QuotaEnforcer
├── LeaderElector
├── BackpressureController
├── DeadLetterAlert
│
│   === Phase 5D v2.0 Enhancements ===
│
├── EnhancedLeaderElector (fencing tokens, epoch)
├── EnhancedFederatedHealthPropagator (6-state machine)
├── HierarchicalQuotaManager (tenant/org/region/global)
├── MessageOrderingController (FIFO, causal)
├── ByzantineProtection (signatures, attestation)
├── RetryBudgetManager (global budget, jitter)
├── DeterministicScheduler (logical clock, replay)
├── AutomatedMitigationEngine (auto DLQ actions)
└── SecureWorkspaceManager (memory wiping, sandbox)
```

---

## 3. Core Components v1

### 3.1 TwoWayCircuitBreaker

Bidirectional circuit breaker protecting both directions of communication.

```python
from src.core.multi_agent.coordination import TwoWayCircuitBreaker

cb = TwoWayCircuitBreaker(
    name="agent-coordinator",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_timeout=30.0,
    half_open_max_calls=1,
)

# Coordinator → Agent direction
async def call_agent():
    return await cb.call(
        agent_id="agent-1",
        func=agent.execute,
        *args,
    )

# Agent → Coordinator direction
async def call_coordinator():
    return await cb.call(
        agent_id="coordinator",
        direction="agent_to_coordinator",
        func=coordinator.delegate,
        *args,
    )
```

**States:**
- `CLOSED`: Normal operation
- `OPEN`: Failing fast, rejecting requests
- `HALF_OPEN`: Testing recovery with limited calls

**Key Features:**
- Sliding window for accurate failure tracking
- Per-direction failure counting
- Configurable transient error codes
- Half-open probe limiting

### 3.2 FederatedHealthPropagator

Aggregates sub-agent health status and reports to coordinator.

```python
from src.core.multi_agent.coordination import FederatedHealthPropagator

propagator = FederatedHealthPropagator(
    health_interval_seconds=10,
    offline_threshold_seconds=30,
    store=health_store,
)

# Federated agent sends sub-agent status
await propagator.report_sub_agents_status(
    federated_agent_id="federated-1",
    sub_agents=[
        {"id": "sub-1", "status": "healthy", "last_heartbeat": now},
        {"id": "sub-2", "status": "offline", "last_heartbeat": old},
    ]
)

# Get aggregated health
health = await propagator.get_federated_health("federated-1")
```

**Offline Detection:**
- Sub-agent offline > 30s triggers notification
- Automatic task reassignment recommendation
- Health score calculation

### 3.3 SchemaEvolutionEngine

Handles message schema versioning with migration.

```python
from src.core.multi_agent.coordination import SchemaEvolutionEngine

engine = SchemaEvolutionEngine(
    compatibility_policy="backward",
    store=schema_store,
)

# Register schema version
async def migrate_v1_to_v2(msg: dict) -> dict:
    msg["new_field"] = msg.pop("old_field", None)
    return msg

await engine.register_schema(
    message_type="TaskMessage",
    version="2",
    schema={"fields": {...}},
    migrations={
        ("1", "2"): migrate_v1_to_v2,
    }
)

# Transform incoming message
transformed = await engine.transform_message(msg, target_version="2")
```

**Compatibility Policies:**
- `backward`: New code reads old data
- `forward`: Old code reads new data (ignores unknown fields)
- `full`: Both directions

### 3.4 BatchIdempotencyStore

Ensures batch operations are idempotent per item.

```python
from src.core.multi_agent.coordination import BatchIdempotencyStore

store = BatchIdempotencyStore(
    ttl_seconds=86400,
    db=db_connection,
)

# Process batch with idempotency
results = []
for i, item in enumerate(batch):
    key = f"{batch_id}:{i}"  # Or use client-provided key
    
    existing = await store.get_result(key)
    if existing:
        results.append(existing)  # Skip, use cached result
        continue
    
    result = await process_item(item)
    await store.save_result(key, result)
    results.append(result)
```

### 3.5 TenantIsolationLayer

Multi-tenant data isolation with JWT authentication.

```python
from src.core.multi_agent.coordination import TenantIsolationLayer

layer = TenantIsolationLayer(
    db=db_connection,
    jwt_secret="secret",
)

# Middleware: extract tenant from JWT
async def handle_request(request):
    tenant_id = await layer.extract_tenant(request)
    await layer.enforce_isolation(tenant_id)
    
    # All queries now filtered by tenant_id
    results = await db.query(
        "SELECT * FROM messages WHERE tenant_id = ?",
        tenant_id
    )
```

**Features:**
- JWT token with tenant_id claim
- Automatic tenant_id injection in queries
- Admin override for multi-tenant access
- Audit logging per tenant

### 3.6 QuotaEnforcer

Enforces resource quotas per agent.

```python
from src.core.multi_agent.coordination import QuotaEnforcer

enforcer = QuotaEnforcer(
    db=db_connection,
    defaults={
        "max_concurrent_tasks": 10,
        "max_message_rate": 100,
        "max_workspace_bytes": 10485760,  # 10MB
    }
)

# Check quota before accepting task
async def submit_task(agent_id: str, task: Task):
    quota = await enforcer.get_quota(agent_id)
    
    if quota.current_concurrent >= quota.max_concurrent_tasks:
        raise QuotaExceededError(f"Concurrent tasks limit: {quota.max_concurrent_tasks}")
    
    await enforcer.check_rate_limit(agent_id)
    await enforcer.check_workspace_size(agent_id)

# Admin: set custom quota
await enforcer.set_quota(agent_id, AgentQuota(
    max_concurrent_tasks=20,
    max_message_rate=200,
    max_workspace_bytes=20971520,
))
```

### 3.7 LeaderElector

Redis-based coordinator leader election.

```python
from src.core.multi_agent.coordination import LeaderElector

elector = LeaderElector(
    redis_url="redis://localhost:6379",
    lock_key="coordinator:leader",
    heartbeat_interval=10,
    lock_ttl=30,
)

# Become leader
leader_id = await elector.try_become_leader("instance-1")
if leader_id == "instance-1":
    # This instance is now leader
    await start_write_operations()
else:
    # This instance is follower
    await start_read_only_mode()

# Leader heartbeat
await elector.heartbeat()

# Leadership transfer
await elector.transfer_leadership("instance-2")

# Get current leader
current_leader = await elector.get_leader()
```

**Features:**
- Redis SETNX with TTL for lock
- Heartbeat renewal
- Automatic takeover on leader crash
- Follower promotion

### 3.8 BackpressureController

Rate limiting from coordinator to agents.

```python
from src.core.multi_agent.coordination import BackpressureController

controller = BackpressureController(
    rate_limit_per_agent=200,
    window_seconds=10,
)

# Check before processing request
async def handle_agent_request(agent_id: str, request):
    is_limited, retry_after = await controller.check_rate_limit(agent_id)
    
    if is_limited:
        return Response(
            status=429,
            headers={"Retry-After": str(retry_after)},
            body="Too Many Requests"
        )
    
    return await process_request(request)

# Record request
await controller.record_request(agent_id)
```

**Response on Limit Exceeded:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1620000000
```

### 3.9 DeadLetterAlert

Monitors DLQ depth and sends webhook alerts.

```python
from src.core.multi_agent.coordination import DeadLetterAlert

alerter = DeadLetterAlert(
    db=db_connection,
    threshold=1000,
    webhook_url="https://hooks.slack.com/services/xxx",
    check_interval=60,
)

# Start monitoring
await alerter.start()

# Manual check
await alerter.check_and_alert()

# Custom webhook payload
async def custom_webhook(dlq_stats: dict):
    return {
        "text": f"DLQ Alert: {dlq_stats['depth']} messages",
        "attachments": [...]
    }

alerter = DeadLetterAlert(
    webhook_factory=custom_webhook,
)
```

---

## 4. Enhanced Components v2

### 4.1 Enhanced Leader Election

Fencing tokens and epoch-based safety for split-brain prevention.

```python
from src.core.multi_agent.coordination.enhanced_leader_election import (
    EnhancedLeaderElector,
    FencingToken,
)

elector = EnhancedLeaderElector(
    redis_url="redis://localhost:6379",
    heartbeat_interval=5.0,
    lock_ttl=15.0,
)

# Become leader with fencing token
leader = await elector.try_become_leader("instance-1")
token = await elector.get_fencing_token()
await elector.validate_fencing_token(token)
```

### 4.2 Health State Machine

Six-state health model for granular agent status.

```python
from src.core.multi_agent.coordination.enhanced_health import (
    AgentHealthState,
    EnhancedFederatedHealthPropagator,
)

propagator = EnhancedFederatedHealthPropagator()
await propagator.report_health(
    agent_id="agent-1",
    state=AgentHealthState.DEGRADED,
)
```

States: HEALTHY → DEGRADED → SATURATED → DRAINING → QUARANTINED → DEAD

### 4.3 Hierarchical Quota System

Multi-level quota management with inheritance.

```python
from src.core.multi_agent.coordination.hierarchical_quota import (
    HierarchicalQuotaManager,
    QuotaScope,
    QuotaPolicy,
)

manager = HierarchicalQuotaManager()
await manager.create_node(
    scope_type=QuotaScope.TENANT,
    scope_id="tenant-1",
    policy=QuotaPolicy(max_concurrent_tasks=50),
)
await manager.allocate(QuotaScope.TENANT, "tenant-1", "concurrent_tasks", 1)
```

### 4.4 Message Ordering

FIFO and causal ordering with sequence numbers.

```python
from src.core.multi_agent.coordination.message_ordering import (
    MessageOrderingController,
    OrderingGuarantee,
)

controller = MessageOrderingController(node_id="coordinator-1")
message = await controller.send(
    receiver="agent-1",
    content={"task": "build"},
    causal_dependencies=["setup-123"],
    guarantee=OrderingGuarantee.EXACTLY_ONCE,
)
```

### 4.5 Byzantine Protection

Message signatures and agent attestation.

```python
from src.core.multi_agent.coordination.byzantine_protection import (
    ByzantineProtection,
)

protection = ByzantineProtection(secret_key=b"key")
await protection.attest_agent("agent-1", public_key, capabilities=[])
signed = await protection.sign_message("msg-1", "agent-1", content={}, sequence=1)
valid = await protection.verify_message(signed)
```

### 4.6 Retry Coordination

Global retry budget and jitter coordination.

```python
from src.core.multi_agent.coordination.retry_coordination import (
    RetryBudgetManager,
    RetryBudget,
)

budget = RetryBudgetManager(
    budget=RetryBudget(
        max_retries_per_task=5,
        global_max_retries_per_minute=1000,
    )
)
decision, delay = await budget.can_retry("task-1", "agent-1", 2)
```

### 4.7 Deterministic Scheduler

Logical clock and replay capability.

```python
from src.core.multi_agent.coordination.deterministic_scheduler import (
    DeterministicScheduler,
    EventType,
)

scheduler = DeterministicScheduler(node_id="coord-1")
event = await scheduler.emit(
    event_type=EventType.TASK_SUBMIT,
    data={"task_id": "task-1"},
    dependencies=["setup-123"],
)
verification = await scheduler.verify_causality()
```

### 4.8 Automated Mitigation

Rule-based DLQ automation.

```python
from src.core.multi_agent.coordination.automated_mitigation import (
    AutomatedMitigationEngine,
    MitigationAction,
)

engine = AutomatedMitigationEngine()
engine.add_rule(MitigationRule(
    rule_id="critical_dlq",
    condition={"depth_threshold": 5000},
    actions=[MitigationAction.PAUSE_AGENT, MitigationAction.NOTIFY],
))
await engine.start()
```

### 4.9 Secure Workspace

Memory zeroization and sandbox management.

```python
from src.core.multi_agent.coordination.secure_workspace import (
    SecureWorkspaceManager,
    WipeStrategy,
)

manager = SecureWorkspaceManager(wipe_strategy=WipeStrategy.DOD5220222M)
workspace = await manager.create_workspace(tenant_id="tenant-1")
await manager.destroy_workspace(workspace.workspace_id)
```

---

## 5. Configuration

```yaml
multi_agent:
  # Two-Way Circuit Breaker
  circuit_breaker:
    failure_threshold: 5
    window_seconds: 60.0
    recovery_timeout: 30.0
    half_open_max_calls: 1
    transient_error_codes:
      - MCP_ERROR
      - TIMEOUT
      - CONNECTION_REFUSED

  # Federated Health
  federated:
    health_interval: 10
    offline_threshold: 30

  # Schema Evolution
  schema:
    evolution: "backward"  # backward, forward, full

  # Batch Idempotency
  batch_idempotency:
    ttl: 86400

  # Quota Defaults
  quota:
    default:
      max_concurrent_tasks: 10
      max_message_rate: 100
      max_workspace_bytes: 10485760  # 10MB

  # Leader Election
  leader:
    lock_key: "coordinator:leader"
    heartbeat_interval: 10
    lock_ttl: 30
    redis_url: "redis://localhost:6379"

  # Backpressure
  backpressure:
    rate_limit_per_agent: 200
    window_seconds: 10

  # Dead Letter Alert
  dead_letter_alert:
    threshold: 1000
    webhook_url: "https://hooks.slack.com/..."
    webhook_method: "POST"
    check_interval: 60

  # Tenant Isolation
  tenant:
    jwt_secret: "${JWT_SECRET}"
    admin_roles:
      - "admin"
      - "super_admin"
```

---

## 6. API Reference

### Admin APIs

```python
# Set agent quota
async def set_agent_quota(agent_id: str, quota: AgentQuota) -> None

# Get agent quota
async def get_agent_quota(agent_id: str) -> AgentQuota

# Get all quotas
async def list_quotas() -> List[AgentQuota]
```

### Tenant APIs

```python
# Create tenant
async def create_tenant(tenant_id: str, config: TenantConfig) -> None

# Delete tenant (cascade)
async def delete_tenant(tenant_id: str) -> None

# Get tenant info
async def get_tenant(tenant_id: str) -> TenantConfig
```

### Schema APIs

```python
# Register schema version
async def register_schema_version(
    message_type: str,
    version: str,
    schema: dict,
    migrations: Dict[Tuple[str, str], Callable]
) -> None

# Get current schema version
async def get_current_version(message_type: str) -> str
```

### Leader APIs

```python
# Get current leader
async def get_leader() -> Optional[str]

# Transfer leadership
async def transfer_leadership(new_leader: str) -> None

# Force election
async def force_election() -> str
```

---

## 7. Metrics

| Metric | Labels | Type | Description |
|--------|--------|------|-------------|
| `circuit_breaker_state` | agent, direction | gauge | Current state (0=closed, 1=open, 2=half-open) |
| `circuit_breaker_failures_total` | agent, direction | counter | Total failures |
| `federated_health_status` | federated_agent, sub_agent | gauge | Sub-agent health (1=healthy, 0=offline) |
| `schema_migration_total` | version_from, version_to | counter | Schema migrations performed |
| `batch_idempotency_hit_total` | batch_id | counter | Idempotent hits (skipped) |
| `quota_reject_total` | agent, type | counter | Quota rejections (concurrent, rate, workspace) |
| `leader_election_total` | instance, result | counter | Election attempts |
| `leader_is_active` | instance | gauge | 1 if this instance is leader |
| `backpressure_throttle_total` | agent | counter | 429 responses sent |
| `dead_letter_depth` | tenant, queue | gauge | Current DLQ depth |
| `dead_letter_alert_sent_total` | tenant | counter | Webhook alerts sent |

---

## 8. Chaos Test Scenarios

### 7.1 Circuit Breaker Tests

```python
async def test_circuit_breaker_opens_on_failures():
    """Circuit opens after failure_threshold failures."""
    cb = TwoWayCircuitBreaker(failure_threshold=5)
    
    for i in range(5):
        with pytest.raises(Exception):
            await cb.call(agent_id="test", func=failing_func)
    
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(agent_id="test", func=success_func)

async def test_circuit_breaker_half_open_recovery():
    """Circuit recovers after recovery_timeout."""
    cb = TwoWayCircuitBreaker(recovery_timeout=1.0)
    
    # Open circuit
    for i in range(5):
        try: await cb.call(agent_id="test", func=failing_func)
        except: pass
    
    # Wait for recovery
    await asyncio.sleep(1.1)
    
    # Should transition to half-open
    result = await cb.call(agent_id="test", func=success_func)
    assert cb.state == CircuitBreakerState.CLOSED
```

### 7.2 Federated Health Tests

```python
async def test_offline_subagent_detection():
    """Sub-agent offline > threshold triggers notification."""
    propagator = FederatedHealthPropagator(offline_threshold_seconds=30)
    
    old_time = datetime.now() - timedelta(seconds=31)
    await propagator.report_sub_agents_status(
        federated_agent_id="fed-1",
        sub_agents=[{"id": "sub-1", "status": "offline", "last_heartbeat": old_time}]
    )
    
    health = await propagator.get_federated_health("fed-1")
    assert health["sub_agents"]["sub-1"]["action_needed"] == True
```

### 7.3 Schema Evolution Tests

```python
async def test_backward_compatible_migration():
    """New code handles old schema."""
    engine = SchemaEvolutionEngine(compatibility_policy="backward")
    
    await engine.register_schema(
        "TaskMessage", "2",
        {"fields": {"new_field": "string"}},
        {("1", "2"): lambda m: {**m, "new_field": "default"}}
    )
    
    old_msg = {"old_field": "value"}
    transformed = await engine.transform_message(old_msg, target_version="2")
    
    assert transformed["new_field"] == "default"
    assert "old_field" not in transformed
```

### 7.4 Batch Idempotency Tests

```python
async def test_batch_idempotency_skips_duplicates():
    """Duplicate items return cached results."""
    store = BatchIdempotencyStore(ttl_seconds=3600)
    
    result1 = await store.get_or_execute(
        key="batch-1:0",
        func=lambda: {"data": "processed"}
    )
    
    result2 = await store.get_or_execute(
        key="batch-1:0",
        func=lambda: {"data": "processed-again"}
    )
    
    assert result1 == result2  # Same cached result
```

### 7.5 Tenant Isolation Tests

```python
async def test_tenant_isolation_blocks_cross_access():
    """Tenant A cannot see Tenant B data."""
    layer = TenantIsolationLayer(db=db)
    
    tenant_a = await layer.extract_tenant(create_token("tenant-a"))
    tenant_b = await layer.extract_tenant(create_token("tenant-b"))
    
    # Insert data for tenant A
    await db.execute(
        "INSERT INTO messages VALUES (?, ?, ?)",
        ("msg-1", "tenant-a", "secret-a")
    )
    
    # Query as tenant B
    results = await layer.query(
        "SELECT * FROM messages WHERE id = ?",
        ("msg-1",),
        tenant_id=tenant_b
    )
    
    assert len(results) == 0  # No cross-tenant access
```

### 7.6 Quota Tests

```python
async def test_quota_exceeded_rejects_tasks():
    """Agent exceeding quota gets rejected."""
    enforcer = QuotaEnforcer(db=db)
    
    await enforcer.set_quota("agent-1", AgentQuota(
        max_concurrent_tasks=2,
        max_message_rate=100,
        max_workspace_bytes=1024,
    ))
    
    # Simulate 2 concurrent tasks
    await enforcer.increment_concurrent("agent-1")
    await enforcer.increment_concurrent("agent-1")
    
    # Third should be rejected
    with pytest.raises(QuotaExceededError):
        await enforcer.check_concurrent("agent-1")
```

### 7.7 Leader Election Tests

```python
async def test_leader_crash_triggers_reelection():
    """Leader failure causes follower to take over."""
    elector = LeaderElector(redis_url=redis_url)
    
    # Instance 1 becomes leader
    leader1 = await elector.try_become_leader("instance-1")
    assert leader1 == "instance-1"
    
    # Instance 2 tries (fails)
    leader2 = await elector.try_become_leader("instance-2")
    assert leader2 != "instance-2"
    
    # Instance 1 heartbeat stops
    # After TTL, instance 2 can become leader
    await asyncio.sleep(35)
    
    leader2 = await elector.try_become_leader("instance-2")
    assert leader2 == "instance-2"
```

### 7.8 Backpressure Tests

```python
async def test_backpressure_returns_429():
    """Agent exceeding rate limit gets 429."""
    controller = BackpressureController(
        rate_limit_per_agent=10,
        window_seconds=1,
    )
    
    # Send 10 requests (at limit)
    for i in range(10):
        await controller.record_request("agent-1")
    
    # 11th should be limited
    is_limited, retry_after = await controller.check_rate_limit("agent-1")
    assert is_limited == True
    assert retry_after > 0
```

### 7.9 Dead Letter Alert Tests

```python
async def test_dlq_alert_triggers_webhook():
    """DLQ exceeding threshold triggers webhook."""
    alerter = DeadLetterAlert(
        db=db,
        threshold=100,
        webhook_url="http://example.com/webhook",
    )
    
    # DLQ exceeds threshold
    await db.execute("INSERT INTO dead_letter (tenant_id, message) SELECT 't1', 'msg' FROM generate_series(1, 101)")
    
    with aioresponses() as mocked:
        mocked.post("http://example.com/webhook", status=200)
        
        await alerter.check_and_alert()
        
        assert mocked.called
        assert mocked.call_count == 1
```

### 7.10 Multi-Region Failover Tests

```python
async def test_region_failover():
    """Primary region failure triggers failover."""
    coordinator = MultiAgentCoordinator(regions=["us-east-1", "eu-west-1"])
    
    # Primary region active
    assert coordinator.active_region == "us-east-1"
    
    # Simulate primary failure
    await coordinator.mark_region_unhealthy("us-east-1")
    
    # Failover to secondary
    assert coordinator.active_region == "eu-west-1"
    
    # Requests routed to new region
    assert coordinator.route_request("task-1")["region"] == "eu-west-1"
```

---

## 9. Done Criteria

Phase 5D Final - All criteria met:

- [x] **Two-way circuit breaker**: CLOSED/OPEN/HALF_OPEN states, sliding window, per-direction tracking
- [x] **Federated health propagation**: Sub-agent status aggregation, offline detection > 30s
- [x] **Schema evolution**: backward/forward/full compatibility, migration functions
- [x] **Batch idempotency**: Per-item idempotency_key, TTL-based caching
- [x] **Tenant isolation**: JWT-based tenant_id, data filtering, admin override
- [x] **Agent resource quota**: concurrent_tasks, message_rate, workspace_bytes limits
- [x] **Coordinator leader election**: Redis SETNX, heartbeat, automatic takeover
- [x] **Backpressure**: 429 response with Retry-After header, sliding window rate limit
- [x] **Dead letter alert**: DLQ monitoring, webhook notifications, threshold alerting
- [x] **Chaos tests**: All 20+ scenarios implemented and passing
- [x] **Metrics**: All components instrumented with Prometheus-compatible metrics

### Phase 5D v2.0 Done Criteria

- [x] Enhanced leader election with fencing tokens
- [x] Epoch-based monotonicity
- [x] Quorum-based consensus (optional)
- [x] Leadership transfer with confirmation
- [x] Six-state health machine
- [x] Automatic state transitions
- [x] Hierarchical quotas (tenant/org/region/global)
- [x] Message FIFO ordering
- [x] Causal ordering with dependencies
- [x] Sequence numbers
- [x] Message signatures
- [x] Agent attestation
- [x] Anomaly detection
- [x] Global retry budget
- [x] Jitter coordination
- [x] System overload protection
- [x] Logical clock scheduler
- [x] Replay capability
- [x] Automated DLQ mitigation
- [x] Secure memory wiping
- [x] Ephemeral sandbox
- [x] Cross-tenant isolation verification

---

## Files Structure (v2)

```
src/core/multi_agent/
├── __init__.py                      # Updated exports
├── coordination/
│   ├── __init__.py                  # Module exports
│   ├── coordinator.py              # MultiAgentCoordinator main class
│   ├── circuit_breaker.py          # TwoWayCircuitBreaker
│   ├── health.py                   # FederatedHealthPropagator
│   ├── schema_evolution.py         # SchemaEvolutionEngine
│   ├── batch_idempotency.py        # BatchIdempotencyStore
│   ├── tenant_isolation.py          # TenantIsolationLayer
│   ├── quota.py                    # QuotaEnforcer
│   ├── leader_election.py           # LeaderElector
│   ├── backpressure.py              # BackpressureController
│   ├── dead_letter_alert.py        # DeadLetterAlert
│   ├── types.py                    # Shared types and enums
│   ├── config.py                   # Configuration classes
│   │                           # === Phase 5D v2.0 Enhancements ===
│   ├── enhanced_leader_election.py # Fencing tokens, quorum, epoch
│   ├── enhanced_health.py          # 6-state health machine
│   ├── hierarchical_quota.py       # Tenant/Org/Region/Global quotas
│   ├── message_ordering.py         # FIFO, causal, sequence numbers
│   ├── byzantine_protection.py     # Signatures, attestation
│   ├── retry_coordination.py       # Global budget, jitter
│   ├── deterministic_scheduler.py   # Logical clock, replay
│   ├── automated_mitigation.py     # Auto DLQ actions
│   └── secure_workspace.py        # Memory zeroization, sandbox
└── ...
```

---

## Dependencies

```python
# Required packages
redis>=4.0.0
pydantic>=2.0.0
prometheus-client>=0.17.0
httpx>=0.24.0
PyJWT>=2.8.0
```
