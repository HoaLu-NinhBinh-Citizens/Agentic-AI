# Phase 5B - Enterprise Planner & Task Decomposition (v9)

**Status**: Implementation In Progress
**Date**: 2026-05-17
**Version**: v9
**Prerequisite**: Phase 5A (Durable Workflow Runtime)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core Concepts](#3-core-concepts)
4. [Data Schemas](#4-data-schemas)
5. [Components](#5-components)
6. [API Reference](#6-api-reference)
7. [Configuration](#7-configuration)
8. [Done Criteria](#8-done-criteria)

---

## 1. Overview

Phase 5B implements an enterprise-grade planner and task decomposition engine with production reliability guarantees:

| Feature | Description |
|---------|-------------|
| **Deterministic Replay** | Branch decisions recorded; replay uses recorded decisions, not re-evaluation |
| **Expression Sandbox** | AST-based evaluation with whitelist operators, no eval() |
| **Schema Versioning** | Input/output schema versioning with migration layer |
| **Resume Idempotency** | Exactly-once resume via token + atomic update |
| **Snapshot Isolation** | Full state rollback before retry |
| **Cost Forecast** | Correlation-aware with explicit independence disclaimer |
| **Semantic Retrieval** | Quality-weighted retrieval with anti-corruption filters |
| **Interrupt Expiration** | Policy-based expiration (auto_cancel, escalate, fallback) |
| **Join Policy** | ALL_SUCCESS, ANY_SUCCESS, QUORUM, ALL_COMPLETED |
| **Expansion Guard** | Limits on nodes, branches, depth, search states |
| **Deadlock Detection** | Cycle, orphan, and reachability validation |
| **Event Sourcing** | Full planner state recovery from event log |
| **Immutable Snapshots** | Plan snapshots independent of code version |
| **Audit Trail** | Human-in-the-loop action logging |

---

## 2. Architecture

```
EnterprisePlanner
+-- PlannerFacade           # Main entry point
+-- ConditionEvaluator     # AST sandbox expression evaluator
+-- SchemaValidator         # Versioned schema validation + migration
+-- BranchDecisionRecorder  # Records branch decisions for replay
+-- ResumeIdempotency       # Token-based resume with atomic updates
+-- PlanRetryManager        # Snapshot isolation for retry
+-- SemanticPlanRetriever   # Quality-weighted plan retrieval
+-- InterruptHandler        # Expiration, escalation, fallback
+-- JoinPolicyEngine       # Parallel branch join policies
+-- PlannerExpansionGuard  # Complexity limits
+-- DeadlockDetector       # DAG validation
+-- EventSourcedPlannerState  # Crash recovery
+-- PlanSnapshotManager     # Immutable snapshots
+-- HumanAuditTrail        # HITL audit logging
+-- CostForecastEngine     # Correlation-aware cost estimation
+-- PlannerMetrics         # Extended metrics
```

---

## 3. Core Concepts

### 3.1 Recorded Branch Decision

Every conditional branch decision is recorded:

```python
BranchDecision(
    workflow_id="wf_123",
    task_id="task_5",
    selected_branch="branch_a",
    condition_expr="context.get('status') == 'approved'",
    evaluated_at=1715961600,
)
```

During replay:
1. Check `branch_decisions` table for recorded decision
2. If found: use recorded `selected_branch`
3. If not found: evaluate expression (new branch)

### 3.2 Expression Sandbox

Safe subset of Python expressions via AST:

**Allowed:**
- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Boolean: `and`, `or`, `not`
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Literals: `True`, `False`, `None`, `int`, `float`, `str`
- Dict access: `context['key']` or `context.get('key')`

**Prohibited:**
- Function calls
- Attribute access (`obj.attr`)
- Lambda expressions
- List/dict comprehensions
- Any `eval()` usage

### 3.3 Schema Versioning

Each task specifies schema versions:

```python
Task(
    task_id="task_1",
    input_schema_version="2.0",
    output_schema_version="1.0",
)
```

Migration chain:
```
v1.0 --migrate_v1_to_v2--> v2.0 --migrate_v2_to_v3--> v3.0
```

### 3.4 Resume Idempotency

```
Resume Request:
  interrupt_id: "int_123"
  resume_token: "tok_abc"
  user_input: {...}

Atomic Update:
  UPDATE plan_interrupts 
  SET status='resumed', resumed_at=now() 
  WHERE interrupt_id=? AND resume_token=? AND status='pending'
```

### 3.5 Snapshot Isolation

Before first run:
1. Create `plan_retry_snapshot` with full state
2. Store serialized context, task statuses, branch decisions

On retry:
1. Load snapshot
2. Restore all state
3. Replay only orchestration (skip completed activities)

---

## 4. Data Schemas

### 4.1 planner_events

```sql
CREATE TABLE planner_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data JSON NOT NULL,
    timestamp INTEGER NOT NULL,
    INDEX idx_session (session_id),
    INDEX idx_event_type (event_type)
);
```

Event types: `decompose_start`, `beam_search_step`, `candidate_evaluated`, `retrieved_template`, `plan_selected`, `branch_decided`, `interrupt_created`, `interrupt_resumed`, `interrupt_expired`, `retry_snapshot_created`, `retry_snapshot_restored`

### 4.2 plan_snapshots

```sql
CREATE TABLE plan_snapshots (
    plan_id TEXT PRIMARY KEY,
    definition_version TEXT NOT NULL,
    serialized_graph JSON NOT NULL,
    snapshot_events JSON NOT NULL,
    created_at INTEGER NOT NULL
);
```

### 4.3 branch_decisions

```sql
CREATE TABLE branch_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    selected_branch TEXT NOT NULL,
    evaluated_at INTEGER NOT NULL,
    condition_expr TEXT NOT NULL,
    UNIQUE(workflow_id, task_id)
);
```

### 4.4 plan_retry_snapshots

```sql
CREATE TABLE plan_retry_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL,
    snapshot JSON NOT NULL,
    created_at INTEGER NOT NULL,
    INDEX idx_plan (plan_id)
);
```

### 4.5 plan_interrupts

```sql
CREATE TABLE plan_interrupts (
    interrupt_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    resume_token TEXT NOT NULL,
    user_input JSON,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    expired_at INTEGER,
    resumed_at INTEGER,
    INDEX idx_plan (plan_id),
    INDEX idx_status (status)
);
```

### 4.6 human_audit_log

```sql
CREATE TABLE human_audit_log (
    action_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    interrupt_id TEXT,
    action TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at INTEGER NOT NULL,
    reason TEXT,
    source_ip TEXT,
    INDEX idx_plan (plan_id)
);
```

### 4.7 schema_registry

```sql
CREATE TABLE schema_registry (
    schema_id TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_def JSON NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(schema_id, version)
);
```

### 4.8 plan_history

```sql
CREATE TABLE plan_history (
    plan_id TEXT PRIMARY KEY,
    session_id TEXT,
    goal_text TEXT,
    plan_graph JSON,
    quality_score REAL,
    human_verified INTEGER,
    failure_rate REAL,
    created_at INTEGER NOT NULL,
    completed_at INTEGER
);
```

---

## 5. Components

### 5.1 ConditionEvaluator

AST-based sandbox expression evaluator:

```python
class ConditionEvaluator:
    def __init__(
        self,
        max_ast_depth: int = 10,
        max_expression_length: int = 500,
    ):
        self._whitelist_operators = {
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.And, ast.Or, ast.Not,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
        }
    
    async def evaluate(self, expr: str, context: dict) -> tuple[bool, str]:
        """Evaluate expression safely. Returns (result, error)."""
```

### 5.2 SchemaValidator

Versioned schema validation:

```python
class SchemaValidator:
    async def validate_input(
        self, 
        task_id: str, 
        schema_version: str,
        data: dict,
    ) -> ValidationResult:
        ...
    
    async def migrate_input(
        self,
        task_id: str,
        from_version: str,
        to_version: str,
        data: dict,
    ) -> dict:
        ...
```

### 5.3 BranchDecisionRecorder

Records and retrieves branch decisions:

```python
class BranchDecisionRecorder:
    async def record(
        self,
        workflow_id: str,
        task_id: str,
        selected_branch: str,
        condition_expr: str,
    ) -> None:
        ...
    
    async def get_decision(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[BranchDecision]:
        ...
```

### 5.4 ResumeIdempotency

Token-based idempotent resume:

```python
class ResumeIdempotency:
    def __init__(self, store: PlanInterruptStore):
        self._store = store
    
    async def create_interrupt(
        self,
        plan_id: str,
        task_id: str,
        timeout_seconds: int = 300,
    ) -> PlanInterrupt:
        ...
    
    async def resume(
        self,
        interrupt_id: str,
        user_input: dict,
        token: str,
    ) -> ResumeResult:
        ...
```

### 5.5 PlanRetryManager

Snapshot isolation for plan retry:

```python
class PlanRetryManager:
    async def create_snapshot(self, plan_id: str, state: PlanState) -> None:
        """Create snapshot before first run."""
    
    async def restore_snapshot(self, plan_id: str) -> PlanState:
        """Restore state for retry."""
    
    async def should_skip_activity(
        self, 
        activity_id: str,
        completed_activities: set[str],
    ) -> bool:
        """Check if activity should be skipped on retry."""
```

### 5.6 SemanticPlanRetriever

Quality-weighted plan retrieval:

```python
class SemanticPlanRetriever:
    def __init__(
        self,
        min_quality_score: float = 0.8,
        require_human_verified: bool = True,
        max_failure_rate: float = 0.2,
    ):
        ...
    
    async def retrieve_similar(
        self,
        goal: str,
        limit: int = 5,
    ) -> list[RetrievedPlan]:
        ...
```

### 5.7 InterruptHandler

Expiration and escalation:

```python
class InterruptHandler:
    def __init__(
        self,
        expiration_policy: str = "auto_cancel",
        escalation_channel: Optional[str] = None,
    ):
        ...

    async def check_expiration(self, interrupt_id: str) -> ExpirationResult:
        ...

    async def execute_policy(
        self,
        interrupt_id: str,
        policy: ExpirationPolicy,
    ) -> None:
        ...
```

### 5.8 JoinPolicyEngine

Parallel branch join logic:

```python
class JoinPolicyEngine:
    async def evaluate_join(
        self,
        join_task_id: str,
        policy: JoinPolicy,
        branch_results: dict[str, BranchResult],
    ) -> JoinResult:
        """Evaluate join condition based on policy."""
```

Join policies:
- `ALL_SUCCESS`: All branches must succeed
- `ANY_SUCCESS`: At least one branch succeeds
- `QUORUM(n)`: At least n branches succeed
- `ALL_COMPLETED`: All branches complete (use partial results on failure)

### 5.9 PlannerExpansionGuard

Complexity limits:

```python
class PlannerExpansionGuard:
    def __init__(
        self,
        max_plan_nodes: int = 500,
        max_branch_factor: int = 5,
        max_search_states: int = 10000,
        max_generation_depth: int = 10,
        planning_timeout_seconds: float = 30.0,
    ):
        ...

    def validate_plan(self, plan: PlanGraph) -> ValidationResult:
        ...

    def validate_decomposition(
        self,
        parent_task: str,
        child_count: int,
        depth: int,
    ) -> ValidationResult:
        ...
```

### 5.10 DeadlockDetector

DAG validation:

```python
class DeadlockDetector:
    async def detect_deadlock(self, plan: PlanGraph) -> DeadlockReport:
        """Run all deadlock checks."""
    
    async def validate_acyclic(self, plan: PlanGraph) -> bool:
        """Check for cycles in conditional DAG."""
    
    async def validate_join_reachability(self, plan: PlanGraph) -> bool:
        """Check all join nodes are reachable from start."""
    
    async def detect_orphan_tasks(self, plan: PlanGraph) -> list[str]:
        """Find tasks not reachable from start or end."""
```

### 5.11 EventSourcedPlannerState

Planner event sourcing:

```python
class EventSourcedPlannerState:
    def __init__(self, event_store: PlannerEventStore):
        self._event_store = event_store
    
    async def create_session(self) -> str:
        """Create new planning session."""
    
    async def emit(self, session_id: str, event: PlannerEvent) -> None:
        """Emit planning event."""
    
    async def replay_session(self, session_id: str) -> list[PlannerEvent]:
        """Replay all events for crash recovery."""
```

### 5.12 PlanSnapshotManager

Immutable plan snapshots:

```python
class PlanSnapshotManager:
    async def create_snapshot(
        self,
        plan_id: str,
        definition_version: str,
        plan_graph: PlanGraph,
        planner_state: dict,
    ) -> PlanSnapshot:
        """Create immutable snapshot."""
    
    async def get_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanSnapshot]:
        """Retrieve snapshot."""
```

### 5.13 HumanAuditTrail

HITL audit logging:

```python
class HumanAuditTrail:
    async def log_action(
        self,
        plan_id: str,
        interrupt_id: Optional[str],
        action: HumanAction,
        approved_by: str,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> str:
        """Log human action with full context."""
```

### 5.14 CostForecastEngine

Correlation-aware cost estimation:

```python
class CostForecastEngine:
    async def forecast(
        self,
        plan: PlanGraph,
        historical_data: Optional[dict] = None,
    ) -> CostForecastReport:
        """Generate cost forecast with disclaimer."""
```

Report includes:
- Total estimated cost
- Task-level breakdown
- Critical path analysis
- Independence assumption disclaimer
- Optional: covariance matrix (Phase 5C)

### 5.15 PlannerMetrics

Extended metrics collection:

```python
PLANNER_METRICS = {
    # Branch decisions
    "branch_decision_count": Counter,
    "branch_decision_cache_hit": Counter,
    
    # Semantic retrieval
    "semantic_retrieval_hit_rate": Gauge,
    "retrieved_plan_quality": Histogram,
    
    # Retry
    "plan_retry_success_rate": Gauge,
    "plan_retry_count": Counter,
    
    # Interrupt
    "interrupt_resume_latency": Histogram,
    "interrupt_expiration_count": Counter,
    
    # Schema validation
    "schema_validation_failures": Counter,
    "schema_migrations_performed": Counter,
    
    # Replay determinism
    "replay_determinism_failures": Counter,
    "replay_success_count": Counter,
    
    # Planner search
    "planner_search_states": Gauge,
    "planner_expansion_rejections": Counter,
    
    # Checkpoint
    "checkpoint_count": Counter,
    "checkpoint_size_bytes": Histogram,
}
```

---

## 6. API Reference

### 6.1 PlannerFacade

```python
class PlannerFacade:
    """Main planner entry point."""
    
    async def plan(
        self,
        goal: str,
        context: dict,
        options: PlanOptions = None,
    ) -> Plan:
        """Create execution plan from goal."""
    
    async def resume_plan(
        self,
        interrupt_id: str,
        user_input: dict,
        token: str,
    ) -> None:
        """Resume interrupted plan with user input."""
    
    async def get_planner_events(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Get events for a planning session."""
    
    async def validate_plan_graph(
        self,
        plan_graph: PlanGraph,
    ) -> ValidationReport:
        """Validate plan for deadlocks and expansion limits."""
    
    async def get_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanSnapshot]:
        """Get immutable plan snapshot."""
    
    async def forecast_cost(
        self,
        plan: PlanGraph,
    ) -> CostForecastReport:
        """Generate cost forecast."""
```

### 6.2 Types

```python
@dataclass
class PlanOptions:
    max_nodes: int = 500
    max_branch_factor: int = 5
    max_depth: int = 10
    timeout_seconds: float = 30.0
    join_policy: JoinPolicy = JoinPolicy.ALL_SUCCESS
    schema_version: str = "1.0"

@dataclass
class BranchDecision:
    workflow_id: str
    task_id: str
    selected_branch: str
    evaluated_at: int
    condition_expr: str

@dataclass
class PlanInterrupt:
    interrupt_id: str
    plan_id: str
    task_id: str
    status: InterruptStatus
    resume_token: str
    expires_at: int

@dataclass
class HumanAuditEntry:
    action_id: str
    plan_id: str
    action: HumanAction
    approved_by: str
    approved_at: int
    reason: Optional[str]
    source_ip: Optional[str]

@dataclass
class CostForecastReport:
    total_cost: float
    task_costs: dict[str, float]
    critical_path: list[str]
    independence_disclaimer: str
    covariance_available: bool = False
```

---

## 7. Configuration

```yaml
planner:
  # Expression sandbox
  conditional_branching:
    record_decisions: true
    sandbox:
      max_ast_depth: 10
      max_expression_length: 500
      whitelist_operators:
        - "and"
        - "or"
        - "not"
        - "=="
        - "!="
        - "<"
        - ">"
        - "<="
        - ">="
        - "+"
        - "-"
        - "*"
        - "/"
        - "%"

  # Schema validation
  schema_validation:
    versioned: true
    migration_enabled: true

  # Resume
  resume:
    idempotency: true
    token_required: true
    default_timeout_seconds: 300

  # Plan retry
  plan_retry:
    snapshot_isolation: true
    snapshot_before_first_run: true

  # Cost forecast
  cost_forecast:
    independence_assumption: true
    disclaimer_in_report: true

  # Semantic retrieval
  semantic_retrieval:
    min_quality_score: 0.8
    require_human_verified: true
    max_failure_rate: 0.2

  # Interrupt
  interrupt:
    expiration_policy: "auto_cancel"
    escalation_channel: "event_bus"

  # Join policy
  join_policy:
    default: "ALL_SUCCESS"

  # Expansion guard
  expansion_guard:
    max_plan_nodes: 500
    max_branch_factor: 5
    max_search_states: 10000
    max_generation_depth: 10
    planning_timeout_seconds: 30

  # Deadlock detection
  deadlock_detection:
    enabled: true
    auto_reject: true

  # Event sourcing
  planner_event_sourcing:
    enabled: true
    retention_days: 30

  # Audit
  audit:
    log_human_actions: true
    include_source_ip: true

  # Metrics
  metrics:
    enabled: true
    export_interval_seconds: 60
```

---

## 8. Done Criteria

### Functional Requirements

- [x] Deterministic replay: branch decisions recorded and reused
- [x] Sandbox expression evaluator (no eval, whitelist, depth limits)
- [x] Schema versioning + migration layer
- [x] Resume idempotency with token + atomic update
- [x] Snapshot isolation for plan retry
- [x] Cost forecast with independence disclaimer
- [x] Semantic retrieval with quality filter
- [x] Interrupt expiration policy, escalation, fallback
- [x] Join policy for conditional parallel DAG
- [x] Expansion guard (complexity limits)
- [x] Deadlock detection and reject
- [x] Event-sourced planner state
- [x] Human audit trail
- [x] Immutable plan snapshot

### Metrics

- [ ] `branch_decision_count` - total recorded
- [ ] `branch_decision_cache_hit` - replay hits
- [ ] `semantic_retrieval_hit_rate` - retrieval efficiency
- [ ] `retrieved_plan_quality` - quality distribution
- [ ] `plan_retry_success_rate` - retry effectiveness
- [ ] `plan_retry_count` - retry attempts
- [ ] `interrupt_resume_latency` - resume timing
- [ ] `interrupt_expiration_count` - expirations
- [ ] `schema_validation_failures` - validation errors
- [ ] `schema_migrations_performed` - migrations
- [ ] `replay_determinism_failures` - determinism errors
- [ ] `replay_success_count` - successful replays
- [ ] `planner_search_states` - beam search states
- [ ] `planner_expansion_rejections` - rejected plans
- [ ] `checkpoint_count` - snapshots created

### Testing

- [ ] All unit tests pass
- [ ] Chaos scenarios simulated:
  - Planner crash and recovery
  - Double-click resume prevention
  - Deadline/expiration handling
  - Deadlock detection
  - Expired snapshot recovery

---

## File Structure

```
src/application/planner/
+-- __init__.py                  # Module exports
+-- types.py                     # Core types and enums
+-- planner_facade.py            # Main entry point
+-- condition_evaluator.py       # AST sandbox
+-- schema_validator.py          # Versioned validation
+-- branch_recorder.py           # Branch decision recording
+-- resume_idempotency.py         # Token-based resume
+-- retry_manager.py             # Snapshot isolation retry
+-- semantic_retriever.py         # Quality-weighted retrieval
+-- interrupt_handler.py          # Expiration/escalation
+-- join_policy.py               # Join policy engine
+-- expansion_guard.py           # Complexity limits
+-- deadlock_detector.py          # DAG validation
+-- event_sourced_state.py        # Planner event sourcing
+-- snapshot_manager.py           # Immutable snapshots
+-- audit_trail.py                # Human audit logging
+-- cost_forecast.py              # Cost estimation
+-- metrics.py                    # Extended metrics
+-- events.py                    # Planner event types
```

---

## Appendix A: Sandbox Expression Examples

### Valid Expressions

```python
context['status'] == 'approved'
context.get('priority', 0) >= 5
x > 10 and y < 20
not context['disabled']
status == 'ready' or status == 'pending'
count % 10 == 0
```

### Invalid Expressions (Blocked)

```python
# Function call - BLOCKED
len(context['items']) > 5

# Attribute access - BLOCKED
context['user'].name == 'admin'

# Lambda - BLOCKED
lambda x: x > 5

# Import - BLOCKED
__import__('os')

# Subscript chain - BLOCKED
data['a']['b']
```

---

## Appendix B: Migration Chain Example

```python
# Register schema v1.0
validator.register_schema(
    schema_id="task_input",
    version="1.0",
    schema={"type": "object", "properties": {"user_id": {"type": "string"}}},
)

# Register migration v1.0 -> v2.0
validator.register_migration(
    schema_id="task_input",
    from_version="1.0",
    to_version="2.0",
    migrate_fn=lambda data: {"user_id": data["user_id"], "tenant_id": "default"},
)

# Register schema v2.0
validator.register_schema(
    schema_id="task_input",
    version="2.0",
    schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "tenant_id": {"type": "string"},
        },
    },
)

# Validate and migrate
result = await validator.validate_input(
    task_id="task_1",
    schema_version="2.0",
    data={"user_id": "u123"},  # v1.0 format
)
# Result: {"user_id": "u123", "tenant_id": "default"}
```
