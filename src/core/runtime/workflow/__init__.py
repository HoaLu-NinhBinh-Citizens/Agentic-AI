"""Workflow Runtime Module - Phase 5A (v6).

Durable workflow runtime with:
- Event sourcing + checkpoint
- Saga pattern with compensation state machine
- At-least-once + idempotent activities
- Heartbeat & lease for long-running activities
- Parent close policy
- Signal sequencing & idempotency
- Distributed lock with fencing token
- Query consistency (eventual/strong)
- Workflow migration hooks
- Fair scheduling (deficit round robin)
- Admission control
- Sticky worker (optional)
- Cooperative cancellation
- Deterministic replay contract (NonDeterministicWorkflowError)
- Version patching API (get_version, patched)
- Signal backpressure
- Deep cancellation semantics
"""

from .types import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowEvent,
    WorkflowStatus,
    ActivityType,
    ActivityResult,
    ActivityStatus,
    Signal,
    ChildWorkflow,
    ParentClosePolicy,
    RetryPolicy,
    StepTimeout,
    Compensation,
    CompensationStatus,
    QueryResult,
    ConsistencyLevel,
    WorkflowSnapshot,
    LockFenceToken,
    HeartbeatRecord,
    MigrationRecord,
    # New v6 types
    Command,
    PatchMarker,
    NonDeterministicWorkflowError,
    SignalBackpressureError,
    ResultTooLargeError,
    StickyBinding,
    StickyWorkerCache,
)
from .workflow_context import WorkflowContext, ActivityContext
from .activity_executor import ActivityExecutor
from .compensation import CompensationStateMachine
from .signal_manager import SignalManager, SequencedSignal
from .child_workflow import ChildWorkflowManager, ClosePolicy
from .lock_manager import LockManager, FencedLock
from .fair_scheduler import FairScheduler, DeficitRoundRobin
from .admission_controller import AdmissionController, ResourceLimits
from .compaction import EventCompactor
from .retention import RetentionManager
from .migration import MigrationHook
# New v6 modules
from .sticky_cache import StickyWorkerCache, StickyBinding, StickyCacheInterface
from .strong_query import StrongQueryExecutor, QueryResult as StrongQueryResult, QueryConsistency
from .cancellation import CancellationManager, CancellationResult, CancellationReason, CancellationToken
from .version_patcher import VersionPatcher, PatchMarker as VPPatchMarker, VersionedCodeChange
from .replay_verifier import ReplayVerifier, CommandRecorder, Command as ReplayCommand, NonDeterministicWorkflowError as ReplayNDError
from .event_ordering import EventOrdering, EventSerializer, EventWaiter, WorkflowEvent as EOEvent
# New v6 modules (additional)
from .replay_optimizer import ReplayOptimizer, ReplayCheckpoint, StateChecksum
from .archival import ArchiveRetriever, ArchiveIndex, ArchiveMetadata

__all__ = [
    # Types
    "WorkflowDefinition",
    "WorkflowInstance",
    "WorkflowEvent",
    "WorkflowStatus",
    "ActivityType",
    "ActivityResult",
    "ActivityStatus",
    "Signal",
    "ChildWorkflow",
    "ParentClosePolicy",
    "RetryPolicy",
    "StepTimeout",
    "Compensation",
    "CompensationStatus",
    "QueryResult",
    "ConsistencyLevel",
    "WorkflowSnapshot",
    "LockFenceToken",
    "HeartbeatRecord",
    "MigrationRecord",
    # New v6 types
    "Command",
    "PatchMarker",
    "NonDeterministicWorkflowError",
    "SignalBackpressureError",
    "ResultTooLargeError",
    "StickyBinding",
    "StickyWorkerCache",
    # Core
    "WorkflowContext",
    "ActivityContext",
    "ActivityExecutor",
    "CompensationStateMachine",
    "SignalManager",
    "SequencedSignal",
    "ChildWorkflowManager",
    "ClosePolicy",
    "LockManager",
    "FencedLock",
    "FairScheduler",
    "DeficitRoundRobin",
    "AdmissionController",
    "ResourceLimits",
    "EventCompactor",
    "RetentionManager",
    "MigrationHook",
    # New v6 modules
    "StickyCacheInterface",
    "StrongQueryExecutor",
    "StrongQueryResult",
    "QueryConsistency",
    "CancellationManager",
    "CancellationResult",
    "CancellationReason",
    "CancellationToken",
    "VersionPatcher",
    "VersionedCodeChange",
    "ReplayVerifier",
    "CommandRecorder",
    "ReplayNDError",
    "EventOrdering",
    "EventSerializer",
    "EventWaiter",
    "EOEvent",
    # Additional v6 modules
    "ReplayOptimizer",
    "ReplayCheckpoint",
    "StateChecksum",
    "ArchiveRetriever",
    "ArchiveIndex",
    "ArchiveMetadata",
]
