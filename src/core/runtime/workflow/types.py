"""Core type definitions for Workflow Runtime - Phase 5A (v6).

Defines all data structures for durable workflow execution.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable, List


# =============================================================================
# DETERMINISTIC ID/TIME GENERATION
# =============================================================================
# P0-A: CRITICAL - These must be used for deterministic replay

def deterministic_uuid(seed: str) -> str:
    """Generate deterministic UUID from seed string.
    
    Uses MD5 hash of seed to generate a reproducible UUID.
    Use this instead of uuid.uuid4() for workflow/event IDs.
    
    Args:
        seed: A deterministic string (e.g., "workflow_id:sequence")
        
    Returns:
        Deterministic UUID string.
    """
    hash_digest = hashlib.md5(seed.encode()).hexdigest()
    return f"{hash_digest[:8]}-{hash_digest[8:12]}-{hash_digest[12:16]}-{hash_digest[16:20]}-{hash_digest[20:32]}"


def deterministic_event_id(workflow_id: str, sequence: int) -> str:
    """Generate deterministic event ID from workflow_id and sequence."""
    return deterministic_uuid(f"{workflow_id}:event:{sequence}")


def deterministic_activity_id(workflow_id: str, sequence: int) -> str:
    """Generate deterministic activity ID from workflow_id and sequence."""
    return deterministic_uuid(f"{workflow_id}:activity:{sequence}")


def deterministic_child_id(workflow_id: str, sequence: int) -> str:
    """Generate deterministic child workflow ID from workflow_id and sequence."""
    return deterministic_uuid(f"{workflow_id}:child:{sequence}")


def deterministic_token_id(lock_id: str, sequence: int) -> str:
    """Generate deterministic fence token ID."""
    return deterministic_uuid(f"{lock_id}:token:{sequence}")


# =============================================================================
# FACTORY FUNCTIONS FOR DETERMINISTIC OBJECTS
# =============================================================================
# P0-A: CRITICAL - Use these factory functions instead of default_factory


def create_workflow_event(
    workflow_id: str,
    sequence: int,
    event_type: EventType,
    event_data: dict[str, Any] = None,
) -> "WorkflowEvent":
    """Create workflow event with deterministic ID.
    
    Args:
        workflow_id: The workflow ID
        sequence: Event sequence number
        event_type: Type of event
        event_data: Optional event data
        
    Returns:
        WorkflowEvent with deterministic ID
    """
    return WorkflowEvent(
        event_id=deterministic_event_id(workflow_id, sequence),
        workflow_id=workflow_id,
        event_type=event_type,
        sequence=sequence,
        event_data=event_data or {},
    )


def create_workflow_instance(
    workflow_id: str,
    workflow_type: str,
    input: dict[str, Any] = None,
) -> "WorkflowInstance":
    """Create workflow instance with deterministic ID.
    
    Args:
        workflow_id: The workflow ID (should be deterministic)
        workflow_type: Type of workflow
        input: Optional input data
        
    Returns:
        WorkflowInstance with deterministic ID
    """
    return WorkflowInstance(
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        input=input or {},
        next_sequence=1,
    )


def create_activity_task(
    workflow_id: str,
    sequence: int,
    activity_type: str,
    input: dict[str, Any] = None,
    idempotency_key: str = None,
) -> "ActivityTask":
    """Create activity task with deterministic ID.
    
    P0-A: This function ensures activity tasks have deterministic IDs
    for Temporal-grade replay correctness.
    
    Args:
        workflow_id: The workflow ID
        sequence: Task sequence number
        activity_type: Type of activity
        input: Optional input data
        idempotency_key: Optional idempotency key
        
    Returns:
        ActivityTask with deterministic ID
    """
    return ActivityTask(
        task_id=deterministic_activity_id(workflow_id, sequence),
        activity_id=f"{workflow_id}:{activity_type}:{sequence}",
        workflow_id=workflow_id,
        activity_type=activity_type,
        input=input or {},
        idempotency_key=idempotency_key or f"{workflow_id}:{activity_type}:{sequence}",
    )


# =============================================================================
# DEPRECATION WARNINGS FOR NON-DETERMINISTIC DEFAULTS
# =============================================================================
# P0-A: WARNING - These default_factory values are NOT deterministic!
# 
# WARNING: Using default_factory for IDs and timestamps will cause
# non-deterministic replay failures. These defaults are provided ONLY
# for backward compatibility and simple use cases.
#
# FOR PRODUCTION: Use the factory functions above:
#   - create_workflow_instance() instead of direct instantiation
#   - create_activity_task() instead of direct instantiation
#   - create_workflow_event() instead of direct instantiation
#
# The only acceptable use of time.time() and uuid.uuid4() defaults
# is for INFRASTRUCTURE objects (not workflow state):
#   - Dead letter queue items (DLQ)
#   - Audit logs (external)
#   - Metrics/counters (aggregated)
#
# Workflow state objects MUST use deterministic IDs/timestamps.


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"


class ActivityStatus(str, Enum):
    """Activity execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CompensationStatus(str, Enum):
    """Compensation (Saga) execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParentClosePolicy(str, Enum):
    """Policy when parent workflow closes."""
    TERMINATE = "terminate"       # Child is terminated immediately
    ABANDON = "abandon"          # Child continues independently
    REQUEST_CANCEL = "request_cancel"  # Child receives cancellation signal


class ConsistencyLevel(str, Enum):
    """Query consistency level."""
    EVENTUAL = "eventual"  # Fast, may not reflect latest state
    STRONG = "strong"      # Replay to current state


class EventType(str, Enum):
    """Workflow event types."""
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_TERMINATED = "workflow_terminated"
    ACTIVITY_SCHEDULED = "activity_scheduled"
    ACTIVITY_STARTED = "activity_started"
    ACTIVITY_COMPLETED = "activity_completed"
    ACTIVITY_FAILED = "activity_failed"
    ACTIVITY_CANCELLED = "activity_cancelled"
    SIGNAL_RECEIVED = "signal_received"
    CHILD_STARTED = "child_started"
    CHILD_COMPLETED = "child_completed"
    CHILD_FAILED = "child_failed"
    CHILD_CANCELLED = "child_cancelled"
    TIMER_FIRED = "timer_fired"
    QUERY_REQUESTED = "query_requested"
    SNAPSHOT_CREATED = "snapshot_created"
    COMPENSATION_SCHEDULED = "compensation_scheduled"
    COMPENSATION_STARTED = "compensation_started"
    COMPENSATION_COMPLETED = "compensation_completed"
    COMPENSATION_FAILED = "compensation_failed"
    MIGRATION_STARTED = "migration_started"
    MIGRATION_COMPLETED = "migration_completed"


@dataclass
class RetryPolicy:
    """Retry configuration for activities."""
    max_attempts: int = 3
    initial_interval_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_interval_seconds: float = 60.0
    retry_on_errors: list[str] = field(default_factory=list)

    def get_next_delay(self, attempt: int) -> float:
        """Calculate delay for next retry with exponential backoff."""
        delay = self.initial_interval_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_interval_seconds)


@dataclass
class StepTimeout:
    """Timeout for a single step/activity execution."""
    timeout_seconds: float = 300.0
    heartbeat_interval_seconds: float = 10.0
    lease_duration_seconds: float = 30.0


@dataclass
class WorkflowDefinition:
    """Definition of a workflow type."""
    name: str
    version: str = "1.0"
    description: str = ""
    
    # Workflow entry point
    entry_point: Optional[Callable] = None
    
    # Timeouts
    default_timeout_seconds: int = 86400  # 24 hours
    
    # Retry config for workflow itself
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    
    # Version history
    previous_versions: list[str] = field(default_factory=list)
    
    def workflow_id(self) -> str:
        """Return unique ID for this definition."""
        return f"{self.name}:{self.version}"


@dataclass
class WorkflowEvent:
    """An event in the workflow event log."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    event_type: EventType = EventType.WORKFLOW_STARTED
    sequence: int = 0  # Monotonically increasing
    
    # Event data
    event_data: dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    
    # Source tracking
    source_worker_id: str = ""
    
    # Archival
    is_archived: bool = False
    
    @property
    def idempotency_key(self) -> str:
        """Generate idempotency key for this event."""
        return f"{self.workflow_id}:{self.event_type}:{self.event_id}"


@dataclass
class WorkflowSnapshot:
    """Snapshot of workflow state for replay optimization."""
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    version: str = ""
    
    # State
    status: WorkflowStatus = WorkflowStatus.RUNNING
    state: dict[str, Any] = field(default_factory=dict)
    
    # Position in event log
    last_event_sequence: int = 0
    
    # Pending items
    pending_activities: list[str] = field(default_factory=list)
    pending_children: list[str] = field(default_factory=list)
    pending_signals: list[str] = field(default_factory=list)
    
    # Execution state
    current_blocked_on: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    created_by: str = ""
    
    # Retention
    is_terminal_snapshot: bool = False  # True for completed/failed workflows


@dataclass
class WorkflowInstance:
    """Instance of a running or completed workflow."""
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str = ""
    version: str = "1.0"
    
    # Status
    status: WorkflowStatus = WorkflowStatus.RUNNING
    
    # Input/Output
    input: dict[str, Any] = field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    
    # Identity
    parent_workflow_id: Optional[str] = None
    parent_close_policy: ParentClosePolicy = ParentClosePolicy.TERMINATE
    
    # Event sourcing
    next_sequence: int = 1
    snapshot: Optional[WorkflowSnapshot] = None
    
    # Timing
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    # Retry state
    retry_count: int = 0
    last_failure: Optional[str] = None
    
    # Idempotency
    idempotency_key: Optional[str] = None
    
    # Priority for scheduling
    priority: int = 5
    
    # Query handler state
    query_state: dict[str, Any] = field(default_factory=dict)
    
    def is_terminal(self) -> bool:
        """Check if workflow is in terminal state."""
        return self.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TERMINATED,
        }


@dataclass
class ActivityType:
    """Definition of an activity type."""
    name: str
    version: str = "1.0"
    
    # Handler
    handler: Optional[Callable] = None
    
    # Timeouts
    start_to_close_timeout: float = 300.0
    schedule_to_start_timeout: float = 60.0
    schedule_to_close_timeout: float = 360.0
    
    # Retry
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    
    def activity_id(self) -> str:
        return f"{self.name}:{self.version}"


@dataclass
class ActivityTask:
    """A task to execute an activity."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    activity_id: str = ""
    workflow_id: str = ""
    activity_type: str = ""
    
    # Input
    input: dict[str, Any] = field(default_factory=dict)
    
    # Execution state
    status: ActivityStatus = ActivityStatus.PENDING
    
    # Identity for idempotency
    idempotency_key: str = ""
    
    # Claim/lease
    claimed_by: Optional[str] = None
    claim_expires_at: float = 0
    
    # Heartbeat
    last_heartbeat_at: float = field(default_factory=time.time)
    heartbeat_details: Optional[Any] = None
    
    # Retry
    attempt: int = 1
    max_attempts: int = 3
    
    # Timing
    scheduled_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ActivityResult:
    """Result of activity execution."""
    task_id: str = ""
    status: ActivityStatus = ActivityStatus.COMPLETED
    
    # Output
    output: Optional[Any] = None
    error: Optional[str] = None
    
    # Timing
    started_at: float = 0
    completed_at: float = 0
    
    # Retry info
    attempt: int = 1
    retry_count: int = 0
    
    # Heartbeat during execution
    heartbeat_count: int = 0


@dataclass
class Signal:
    """A signal sent to a workflow."""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    name: str = ""
    
    # Payload
    payload: dict[str, Any] = field(default_factory=dict)
    
    # Sequencing
    sequence: int = 0
    
    # Idempotency
    idempotency_key: str = ""
    
    # Status
    received: bool = False
    processed: bool = False
    processed_at: Optional[float] = None
    
    # Timing
    received_at: float = field(default_factory=time.time)


@dataclass
class SequencedSignal:
    """Signal with sequence number for ordering."""
    signal: Signal
    sequence: int
    
    @property
    def idempotency_key(self) -> str:
        return f"{self.signal.workflow_id}:signal:{self.signal.name}:{self.sequence}"


@dataclass
class ChildWorkflow:
    """A child workflow instance."""
    child_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_workflow_id: str = ""
    
    # Definition
    workflow_type: str = ""
    version: str = "1.0"
    
    # Close policy
    close_policy: ParentClosePolicy = ParentClosePolicy.TERMINATE
    
    # Input
    input: dict[str, Any] = field(default_factory=dict)
    
    # Status
    status: WorkflowStatus = WorkflowStatus.RUNNING
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # Timing
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class Compensation:
    """Compensation action for Saga pattern."""
    compensation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = ""  # The activity step that was compensated
    
    # What to undo
    activity_name: str = ""
    original_input: dict[str, Any] = field(default_factory=dict)
    original_output: Optional[Any] = None
    
    # Status
    status: CompensationStatus = CompensationStatus.PENDING
    
    # Retry state
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: float = 0
    
    # Idempotency
    idempotency_key: str = ""
    
    # Compensation handler
    handler: Optional[Callable] = None
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


@dataclass
class QueryResult:
    """Result of a workflow query."""
    workflow_id: str = ""
    query_name: str = ""
    
    # Consistency
    consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # State at query time
    state_snapshot: Optional[WorkflowSnapshot] = None
    
    # Timing
    queried_at: float = field(default_factory=time.time)


@dataclass
class LockFenceToken:
    """Token for distributed lock fencing.

    Production safety requirements:
    - token MUST be monotonic for a given lock_id (fencing epoch)
    - under coordination uncertainty (Redis unavailable), dangerous ops must fail-closed
    """

    # Monotonic fencing epoch for this lock_id (from Redis INCR)
    epoch: int = 0

    lock_id: str = ""

    # Owner
    owner_id: str = ""

    # Validity
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0

    # State
    is_revoked: bool = False


@dataclass
class HeartbeatRecord:
    """Heartbeat record for long-running activities."""
    activity_id: str = ""
    task_id: str = ""
    workflow_id: str = ""
    
    # Timing
    last_heartbeat_at: float = field(default_factory=time.time)
    lease_expiry: float = 0
    
    # Details
    details: Optional[Any] = None
    
    # Worker
    worker_id: str = ""


@dataclass
class MigrationRecord:
    """Record of workflow migration."""
    workflow_id: str = ""
    old_version: str = ""
    new_version: str = ""
    
    # State
    status: str = "pending"  # pending, in_progress, completed, failed
    
    # Result
    old_snapshot: Optional[WorkflowSnapshot] = None
    new_snapshot: Optional[WorkflowSnapshot] = None
    
    # Error
    error: Optional[str] = None
    
    # Timing
    migrated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class DeadLetterItem:
    """Item in dead letter queue."""
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Source
    workflow_id: str = ""
    task_id: Optional[str] = None
    source_type: str = ""  # "activity", "compensation", "child"
    
    # Content
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    
    # Failure info
    failure_count: int = 0
    last_failure_at: float = field(default_factory=time.time)
    last_worker_id: Optional[str] = None
    
    # Retention
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    
    # Resolution
    resolved: bool = False
    resolved_at: Optional[float] = None
    resolution: Optional[str] = None  # "requeued", "discarded", "manual"


# =============================================================================
# DETERMINISTIC REPLAY TYPES
# =============================================================================


@dataclass
class Command:
    """A command emitted during workflow execution.
    
    Commands are the fundamental unit of deterministic replay verification.
    Each command must match exactly during replay.
    """
    command_type: str  # "schedule_activity", "start_child", "timer", "signal", etc.
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0  # Order in which command was emitted
    
    # Command specifics
    activity_name: Optional[str] = None
    activity_input: Optional[dict] = None
    child_workflow_type: Optional[str] = None
    child_input: Optional[dict] = None
    signal_name: Optional[str] = None
    signal_payload: Optional[dict] = None
    timer_duration_seconds: Optional[float] = None
    
    # Version patching
    change_id: Optional[str] = None
    version: Optional[int] = None
    
    def to_event_data(self) -> dict:
        """Convert command to event data for storage."""
        return {
            "command_type": self.command_type,
            "command_id": self.command_id,
            "activity_name": self.activity_name,
            "activity_input": self.activity_input,
            "child_workflow_type": self.child_workflow_type,
            "child_input": self.child_input,
            "signal_name": self.signal_name,
            "signal_payload": self.signal_payload,
            "timer_duration_seconds": self.timer_duration_seconds,
            "change_id": self.change_id,
            "version": self.version,
        }


@dataclass
class PatchMarker:
    """Event marker for version patching (get_version/patched).
    
    When workflow code uses ctx.get_version() or ctx.patched(),
    a PatchMarker event is recorded to track which version
    was used during replay.
    """
    patch_id: str
    workflow_id: str
    
    # Created during original execution
    created_event_id: str = ""
    created_sequence: int = 0
    
    # Version info
    version: int = 1
    is_replay: bool = False
    
    # Metadata
    created_at: float = field(default_factory=time.time)


class NonDeterministicWorkflowError(Exception):
    """Raised when workflow produces different commands during replay.
    
    This is the CRITICAL error for durable execution correctness.
    If commands don't match during replay, the workflow state is corrupt.
    
    The workflow must be terminated and restarted from a clean state
    or the code must be fixed to be deterministic.
    """
    
    def __init__(
        self,
        workflow_id: str,
        expected_sequence: List[Command],
        actual_sequence: List[Command],
        mismatch_at: int,
        reason: str,
    ):
        self.workflow_id = workflow_id
        self.expected_sequence = expected_sequence
        self.actual_sequence = actual_sequence
        self.mismatch_at = mismatch_at
        self.reason = reason
        
        # Build detailed message
        expected_cmd = expected_sequence[mismatch_at] if mismatch_at < len(expected_sequence) else None
        actual_cmd = actual_sequence[mismatch_at] if mismatch_at < len(actual_sequence) else None
        
        msg = (
            f"Non-deterministic workflow detected: {workflow_id}\n"
            f"Mismatch at command position {mismatch_at}\n"
            f"Reason: {reason}\n"
            f"Expected: {expected_cmd}\n"
            f"Actual: {actual_cmd}\n"
            f"\n"
            f"Fix: Use ctx.get_version() or ctx.patched() for replay-safe code upgrades.\n"
            f"See: https://docs.temporal.io/encyclopedia/versioning"
        )
        super().__init__(msg)
    
    @property
    def suggested_fix(self) -> str:
        return (
            f"Workflow {self.workflow_id} became non-deterministic. "
            f"Command at position {self.mismatch_at} differs. "
            f"Use get_version() or patched() for safe code upgrades."
        )


class SignalBackpressureError(Exception):
    """Raised when signal queue exceeds limit.
    
    Prevents workflow from being overwhelmed by signals.
    """
    
    def __init__(
        self,
        workflow_id: str,
        pending_count: int,
        max_pending: int,
    ):
        self.workflow_id = workflow_id
        self.pending_count = pending_count
        self.max_pending = max_pending
        
        msg = (
            f"Signal backpressure: workflow {workflow_id} has "
            f"{pending_count} pending signals (max: {max_pending})"
        )
        super().__init__(msg)


class ResultTooLargeError(Exception):
    """Raised when activity result exceeds size limit.
    
    Large payloads should be offloaded to blob storage.
    """
    
    def __init__(
        self,
        result_size_bytes: int,
        max_size_bytes: int,
    ):
        self.result_size_bytes = result_size_bytes
        self.max_size_bytes = max_size_bytes
        
        msg = (
            f"Activity result too large: {result_size_bytes} bytes "
            f"(max: {max_size_bytes} bytes). "
            f"Consider offloading to blob storage."
        )
        super().__init__(msg)


# =============================================================================
# STICKY WORKER CACHE TYPES
# =============================================================================


@dataclass
class StickyBinding:
    """Binding between workflow and worker for sticky execution."""
    workflow_id: str
    worker_id: str
    
    # Lease
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    last_heartbeat_at: float = field(default_factory=time.time)
    
    # State
    is_stale: bool = False


class StickyWorkerCache:
    """Cache for sticky workflow execution.
    
    Sticky execution improves performance by running workflow
    on the same worker that handled it before.
    """
    
    def __init__(
        self,
        sticky_enabled: bool = True,
        sticky_timeout_seconds: int = 10,
        max_cache_size: int = 10000,
        eviction_policy: str = "lru",
    ):
        self.sticky_enabled = sticky_enabled
        self.sticky_timeout_seconds = sticky_timeout_seconds
        self.max_cache_size = max_cache_size
        self.eviction_policy = eviction_policy
        
        # In-memory cache
        self._bindings: dict[str, StickyBinding] = {}
        self._access_order: list[str] = []  # For LRU
    
    def get_binding(self, workflow_id: str) -> Optional[StickyBinding]:
        """Get sticky binding for workflow."""
        binding = self._bindings.get(workflow_id)
        if binding and not binding.is_stale and binding.expires_at > time.time():
            self._update_lru(workflow_id)
            return binding
        return None
    
    def set_binding(self, workflow_id: str, worker_id: str) -> StickyBinding:
        """Create sticky binding for workflow to worker."""
        binding = StickyBinding(
            workflow_id=workflow_id,
            worker_id=worker_id,
            expires_at=time.time() + self.sticky_timeout_seconds,
        )
        self._bindings[workflow_id] = binding
        self._update_lru(workflow_id)
        self._evict_if_needed()
        return binding
    
    def invalidate(self, workflow_id: str) -> None:
        """Invalidate cache entry for workflow."""
        if workflow_id in self._bindings:
            del self._bindings[workflow_id]
    
    def invalidate_all(self, worker_id: str) -> List[str]:
        """Invalidate all bindings for worker (e.g., worker death)."""
        invalidated = []
        for workflow_id, binding in list(self._bindings.items()):
            if binding.worker_id == worker_id:
                binding.is_stale = True
                invalidated.append(workflow_id)
        return invalidated
    
    def handle_worker_death(self, worker_id: str) -> List[str]:
        """Handle worker death: invalidate bindings, return affected workflows."""
        invalidated = self.invalidate_all(worker_id)
        # Return workflow IDs for re-scheduling
        return list(self._bindings.keys())  # Caller should filter stale
    
    def _update_lru(self, workflow_id: str) -> None:
        """Update LRU order."""
        if workflow_id in self._access_order:
            self._access_order.remove(workflow_id)
        self._access_order.append(workflow_id)
    
    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is full."""
        while len(self._bindings) > self.max_cache_size:
            if self._access_order:
                oldest = self._access_order.pop(0)
                if oldest in self._bindings:
                    del self._bindings[oldest]
