"""Enterprise workflow runtime extensions - Phase 5B v10.

This module extends the Phase 5A workflow runtime with enterprise features:
- Deterministic time, random, and UUID generation
- Exactly-once side effects via idempotency
- Activity heartbeat and lease management
- Cancellation tree with policies
- Compensation/Saga with retry and dead letter
- Workflow sharding and partitioning
- History compaction (Continue-As-New)
- Sticky execution
- Multi-tenant isolation and quotas
- Poison tool defense
- Lifecycle retention and archival
- RBAC approval
- Event log integrity
- Planner determinism versioning
- Formal state machines
- Chaos testing (18+ scenarios)
"""

from .deterministic_values import DeterministicValueGenerator
from .exactly_once import (
    IdempotencyKeyGenerator,
    SideEffectRegistry,
    ExactlyOnceActivityExecutor,
)
from .heartbeat_lease import (
    ActivityHeartbeatManager,
    LeaseManager,
)
from .cancellation_tree import (
    CancellationPolicy,
    CancellationTree,
    CancellationExecutor,
)
from .compensation_saga import (
    SagaCoordinator,
    CompensationTask,
    DeadLetterQueue,
)
from .workflow_sharding import (
    ConsistentHashRing,
    WorkflowPartitioner,
)
from .history_compaction import (
    ContinueAsNewManager,
    HistoryCompactor,
)
from .sticky_execution import (
    StickyWorkerCache,
    StickyExecutionManager,
)
from .multi_tenant import (
    TenantQuota,
    MultiTenantQuotaManager,
    WeightedFairScheduler,
)
from .poison_defense import (
    ToolOutputSanitizer,
    TrustScoreManager,
    PoisonToolDefense,
)
from .lifecycle_retention import (
    WorkflowLifecycle,
    LifecycleManager,
    RetentionPolicy,
)
from .rbac_approval import (
    Role,
    RBACEngine,
    RBACApprovalEngine,
)
from .event_integrity import (
    HashChainValidator,
    EventIntegrityManager,
)
from .planner_versioning import (
    PlannerArtifacts,
    DeterminismVersionManager,
)
from .state_machine import (
    StateMachine,
    WorkflowStateMachine,
    ActivityStateMachine,
    CompensationStateMachine,
)
from .chaos_tests import (
    ChaosScenario,
    ChaosTestSuite,
)

__all__ = [
    # Deterministic values
    "DeterministicValueGenerator",
    # Exactly-once
    "IdempotencyKeyGenerator",
    "SideEffectRegistry",
    "ExactlyOnceActivityExecutor",
    # Heartbeat & Lease
    "ActivityHeartbeatManager",
    "LeaseManager",
    # Cancellation Tree
    "CancellationPolicy",
    "CancellationTree",
    "CancellationExecutor",
    # Compensation / Saga
    "SagaCoordinator",
    "CompensationTask",
    "DeadLetterQueue",
    # Sharding
    "ConsistentHashRing",
    "WorkflowPartitioner",
    # History Compaction
    "ContinueAsNewManager",
    "HistoryCompactor",
    # Sticky Execution
    "StickyWorkerCache",
    "StickyExecutionManager",
    # Multi-tenant
    "TenantQuota",
    "MultiTenantQuotaManager",
    "WeightedFairScheduler",
    # Poison Defense
    "ToolOutputSanitizer",
    "TrustScoreManager",
    "PoisonToolDefense",
    # Lifecycle
    "WorkflowLifecycle",
    "LifecycleManager",
    "RetentionPolicy",
    # RBAC
    "Role",
    "RBACEngine",
    "RBACApprovalEngine",
    # Event Integrity
    "HashChainValidator",
    "EventIntegrityManager",
    # Planner Versioning
    "PlannerArtifacts",
    "DeterminismVersionManager",
    # State Machine
    "StateMachine",
    "WorkflowStateMachine",
    "ActivityStateMachine",
    "CompensationStateMachine",
    # Chaos Testing
    "ChaosScenario",
    "ChaosTestSuite",
]
