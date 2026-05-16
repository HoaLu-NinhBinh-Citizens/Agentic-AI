"""
Runtime Kernel Module

Provides the core runtime infrastructure for Phase 15 P0:

Core Components:
- RuntimeController: State machine lifecycle management
- EventJournal: Persistent event logging with replay
- DeadLetterQueue: Failed event quarantine
- EventReplayer: Replay events from journal

Phase 15 P0 - Runtime Collapse Prevention:
- TaskScheduler: Priority-based task scheduling
- CircuitBreaker: Fault isolation for dependencies
- AdmissionController: Queue and capacity management
- CancellationScope: Hierarchical cancellation propagation
- BackpressureManager: Cascade failure prevention
- ResourceGovernor: Resource budget management
- IdempotencyStore: Safe retries with deduplication
- IsolatedExecutor: Process-based tool isolation
- RuntimeIntrospector: Live debugging capabilities
- Kernel boundary definitions

Usage:
    from src.domains.runtime import (
        RuntimeController,
        RuntimeState,
        TaskScheduler,
        CircuitBreaker,
        AdmissionController,
        CancellationScope,
        BackpressureManager,
    )

Phase 15 P0 Modules:
    scheduler/task_scheduler.py  - Priority-based scheduling
    runtime/circuit_breaker.py - Fault isolation
    runtime/admission.py       - Queue admission control
    runtime/cancellation.py    - Cancellation propagation
    runtime/backpressure.py     - Backpressure management
    runtime/resource_governor.py - Resource budgets
    runtime/idempotency.py     - Idempotency store
    runtime/tool_isolation.py  - Tool process isolation
    runtime/introspector.py    - Runtime debugging
    runtime/kernel.py          - Kernel boundary

Phase 15 P1 Modules:
    runtime/execution_tracker.py - DAG-based task tracking
"""

# Core runtime components
from src.domains.runtime.controller import RuntimeController, RuntimeState, LifecycleEvent
from src.domains.runtime.journal import EventJournal, JournalEntry, JournalPartition, PartitionStrategy
from src.domains.runtime.dlq import DeadLetterQueue, DLQEntry, DLQReason, DLQStatus
from src.domains.runtime.replayer import EventReplayer, ReplayResult, ReplayFilter

# Phase 15 P0: Runtime collapse prevention
from src.core.scheduler import TaskScheduler, Priority, ScheduledTask, QueueFullError
from src.domains.runtime.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    get_circuit,
    circuit_registry,
)
from src.domains.runtime.admission import (
    AdmissionController,
    AdmissionDecision,
    AdmissionRequest,
    get_admission_controller,
)
from src.domains.runtime.cancellation import (
    CancellationScope,
    CancellationToken,
    CancelledError,
    cancellation_token,
    get_current_cancellation,
)
from src.domains.runtime.backpressure import (
    BackpressureManager,
    BackpressureSignal,
    PressureState,
    backpressure_manager,
    get_backpressure_manager,
)
from src.domains.runtime.resource_governor import (
    ResourceGovernor,
    ResourceBudget,
    ResourceAcquired,
    get_governor,
)
from src.domains.runtime.idempotency import (
    IdempotencyStore,
    IdempotencyKey,
    idempotent,
    idempotency_store,
)
from src.domains.runtime.tool_isolation import (
    IsolatedExecutor,
    IsolationConfig,
    ToolTimeoutError,
    ToolExecutionError,
    get_executor,
)
from src.domains.runtime.introspector import (
    RuntimeIntrospector,
    RuntimeSnapshot,
    TaskSnapshot,
    QueueSnapshot,
    get_introspector,
)
from src.domains.runtime.kernel import (
    KernelBoundary,
    classify,
    is_kernel,
    validate_kernel,
)

# Phase 15 P1: Execution Tracking
from src.domains.runtime.execution_tracker import (
    ExecutionTracker,
    ExecutionGraph,
    TaskState,
    TaskNode,
    get_tracker,
)

__all__ = [
    # Controller
    "RuntimeController",
    "RuntimeState",
    "LifecycleEvent",
    # Journal
    "EventJournal",
    "JournalEntry",
    "JournalPartition",
    "PartitionStrategy",
    # DLQ
    "DeadLetterQueue",
    "DLQEntry",
    "DLQReason",
    "DLQStatus",
    # Replayer
    "EventReplayer",
    "ReplayResult",
    "ReplayFilter",
    # Phase 15 P0
    # Scheduler
    "TaskScheduler",
    "Priority",
    "ScheduledTask",
    "QueueFullError",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "get_circuit",
    "circuit_registry",
    # Admission
    "AdmissionController",
    "AdmissionDecision",
    "AdmissionRequest",
    "get_admission_controller",
    # Cancellation
    "CancellationScope",
    "CancellationToken",
    "CancelledError",
    "cancellation_token",
    "get_current_cancellation",
    # Backpressure
    "BackpressureManager",
    "BackpressureSignal",
    "PressureState",
    "backpressure_manager",
    "get_backpressure_manager",
    # Resource
    "ResourceGovernor",
    "ResourceBudget",
    "ResourceAcquired",
    "get_governor",
    # Idempotency
    "IdempotencyStore",
    "IdempotencyKey",
    "idempotent",
    "idempotency_store",
    # Tool Isolation
    "IsolatedExecutor",
    "IsolationConfig",
    "ToolTimeoutError",
    "ToolExecutionError",
    "get_executor",
    # Introspector
    "RuntimeIntrospector",
    "RuntimeSnapshot",
    "TaskSnapshot",
    "QueueSnapshot",
    "get_introspector",
    # Kernel
    "KernelBoundary",
    "classify",
    "is_kernel",
    "validate_kernel",
    # Phase 15 P1 - Execution Tracking
    "ExecutionTracker",
    "ExecutionGraph",
    "TaskState",
    "TaskNode",
    "get_tracker",
]