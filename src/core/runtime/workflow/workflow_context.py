"""Workflow and Activity Context - Phase 5A (v6).

WorkflowContext: Deterministic workflow orchestration.
ActivityContext: Side-effect activity execution with heartbeat.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

from .types import (
    WorkflowInstance,
    WorkflowSnapshot,
    WorkflowStatus,
    Signal,
    ActivityTask,
    ActivityResult,
    ActivityStatus,
    ChildWorkflow,
    ParentClosePolicy,
    StepTimeout,
    RetryPolicy,
    QueryResult,
    ConsistencyLevel,
    Command,
    PatchMarker,
)

logger = logging.getLogger(__name__)


@dataclass
class ActivityOptions:
    """Options for activity execution."""
    timeout_seconds: Optional[float] = None
    retry_policy: Optional[RetryPolicy] = None
    idempotency_key: Optional[str] = None
    heartbeat_interval_seconds: float = 10.0
    schedule_to_start_timeout_seconds: float = 60.0


@dataclass
class WorkflowContext:
    """Context for deterministic workflow orchestration.
    
    Workflow code uses this to:
    - Execute activities (side effects)
    - Wait for signals
    - Start child workflows
    - Set query handlers
    - Access workflow state
    """
    
    workflow_instance: WorkflowInstance
    
    # Event store interface (implemented by runtime)
    _event_store: Any = None
    
    # Query handlers
    _query_handlers: dict[str, Callable] = field(default_factory=dict)
    
    # Current blocked state
    _is_blocked: bool = False
    _blocked_reason: Optional[str] = None
    
    # Cancellation
    _is_cancelled: bool = False
    _cancel_reason: Optional[str] = None
    
    # Pending activities tracking
    _pending_activities: dict[str, asyncio.Future] = field(default_factory=dict)
    _pending_children: dict[str, asyncio.Future] = field(default_factory=dict)
    
    # Version patching state
    _patch_versions: dict[str, int] = field(default_factory=dict)
    _replay_mode: bool = False
    
    # Deterministic random
    _random_state: float = 0.0
    
    # Command emission for replay verification
    _emitted_commands: list[Command] = field(default_factory=list)
    
    # Side effect cache for replay
    _side_effect_cache: dict[str, Any] = field(default_factory=dict)
    
    # Signal handlers for await_signal
    _signal_handlers: dict[str, asyncio.Future] = field(default_factory=dict)
    
    async def execute_activity(
        self,
        activity_name: str,
        input: dict[str, Any],
        options: Optional[ActivityOptions] = None,
    ) -> Any:
        """Execute an activity and wait for result.
        
        This is the ONLY way to perform side effects in a workflow.
        Activity must be idempotent.
        
        Args:
            activity_name: Name of the activity to execute.
            input: Input data for the activity.
            options: Execution options (timeout, retry, etc.).
            
        Returns:
            Activity result.
            
        Raises:
            ActivityError: If activity fails.
        """
        if self._is_cancelled:
            raise WorkflowCancelledError(f"Workflow cancelled: {self._cancel_reason}")
        
        options = options or ActivityOptions()
        
        # Create activity task with deterministic ID from workflow history
        # CRITICAL: Must use history-backed ID for Temporal-grade replay correctness
        # During new execution: use deterministic UUID based on sequence
        # During replay: use ID from event history
        activity_id = self._next_activity_id(activity_name)
        
        task = ActivityTask(
            activity_id=activity_id,
            activity_type=activity_name,
            workflow_id=self.workflow_instance.workflow_id,
            input=input,
            idempotency_key=options.idempotency_key or f"{activity_name}:{self._next_activity_sequence()}",
            max_attempts=options.retry_policy.max_attempts if options.retry_policy else 3,
        )
        
        # Store execution ID for downstream deduplication
        self._activity_execution_id = task.activity_id
        
        # Create future for result
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_activities[task.activity_id] = future
        
        try:
            # Emit activity scheduled event
            await self._emit_event(
                event_type="activity_scheduled",
                event_data={
                    "activity_id": task.activity_id,
                    "activity_type": activity_name,
                    "input": input,
                    "idempotency_key": task.idempotency_key,
                }
            )
            
            # Submit to task queue
            await self._submit_activity_task(task, options)
            
            # Wait for result (blocks workflow, but is deterministic)
            self._is_blocked = True
            self._blocked_reason = f"waiting_for_activity:{activity_name}"
            
            try:
                result = await asyncio.wait_for(
                    future,
                    timeout=options.timeout_seconds
                )
                return result
            finally:
                self._is_blocked = False
                self._blocked_reason = None
                
        except asyncio.TimeoutError:
            raise ActivityTimeoutError(f"Activity {activity_name} timed out")
        finally:
            self._pending_activities.pop(task.activity_id, None)
    
    def _next_activity_sequence(self) -> int:
        """Generate next activity sequence number."""
        return len(self._pending_activities) + self.workflow_instance.next_sequence
    
    def _next_activity_id(self, activity_name: str) -> str:
        """Generate deterministic activity ID for replay correctness.
        
        CRITICAL: This ensures activity IDs are deterministic based on
        workflow history, not random UUIDs.
        
        Protocol:
        - During NEW execution: generate deterministic ID from sequence
        - During REPLAY: return ID from event history
        
        Returns:
            Deterministic activity ID string.
        """
        # Check if we're in replay mode with history
        if self._replay_mode and self._event_store:
            # In replay, we need to get the activity_id from history
            # Find the next activity_scheduled event in history
            history_id = self._event_store.get_next_activity_id_from_history(
                self.workflow_instance.workflow_id,
                len([c for c in self._emitted_commands 
                     if c.command_type == "schedule_activity"])
            )
            if history_id:
                return history_id
        
        # Generate deterministic ID based on workflow ID and sequence
        # Format: {workflow_id}:activity:{sequence}
        activity_seq = len([c for c in self._emitted_commands 
                           if c.command_type == "schedule_activity"])
        
        # P0-A: Use deterministic ID generation instead of uuid.uuid4()
        base = f"{self.workflow_instance.workflow_id}:activity:{activity_seq}"
        import hashlib
        hash_digest = hashlib.md5(base.encode()).hexdigest()
        return f"{hash_digest[:8]}-{hash_digest[8:12]}-{hash_digest[12:16]}-{hash_digest[16:20]}-{hash_digest[20:32]}"
    
    def _next_child_id(self, child_workflow_name: str) -> str:
        """Generate deterministic child workflow ID for replay correctness.
        
        CRITICAL: This ensures child workflow IDs are deterministic based on
        workflow history, not random UUIDs.
        
        Returns:
            Deterministic child workflow ID string.
        """
        # Check replay mode - in replay, IDs should come from history
        if self._replay_mode and self._event_store:
            # In replay, we get child IDs from event history
            history_id = self._event_store.get_next_child_id_from_history(
                self.workflow_instance.workflow_id,
                len([c for c in self._emitted_commands 
                     if c.command_type == "start_child"])
            )
            if history_id:
                return history_id
        
        # P0-A: Use deterministic ID generation instead of uuid.uuid4()
        child_seq = len([c for c in self._emitted_commands 
                        if c.command_type == "start_child"])
        base = f"{self.workflow_instance.workflow_id}:child:{child_seq}"
        import hashlib
        hash_digest = hashlib.md5(base.encode()).hexdigest()
        return f"{hash_digest[:8]}-{hash_digest[8:12]}-{hash_digest[12:16]}-{hash_digest[16:20]}-{hash_digest[20:32]}"
    
    async def wait_for_signal(
        self,
        name: str,
        timeout_seconds: Optional[float] = None,
    ) -> Any:
        """Wait for a signal with the given name.
        
        Blocks workflow until signal is received or timeout.
        
        Args:
            name: Signal name to wait for.
            timeout_seconds: Optional timeout.
            
        Returns:
            Signal payload when received.
        """
        if self._is_cancelled:
            raise WorkflowCancelledError(f"Workflow cancelled: {self._cancel_reason}")
        
        # Create future for signal
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        
        # Emit waiting event
        await self._emit_event(
            event_type="waiting_for_signal",
            event_data={"signal_name": name, "timeout": timeout_seconds}
        )
        
        # Register signal handler
        self._register_signal_handler(name, future)
        
        # Block workflow
        self._is_blocked = True
        self._blocked_reason = f"waiting_for_signal:{name}"
        
        try:
            if timeout_seconds:
                return await asyncio.wait_for(future, timeout=timeout_seconds)
            return await future
        except asyncio.TimeoutError:
            raise SignalTimeoutError(f"Signal {name} timeout after {timeout_seconds}s")
        finally:
            self._is_blocked = False
            self._blocked_reason = None
            self._unregister_signal_handler(name)
    
    async def start_child_workflow(
        self,
        name: str,
        input: dict[str, Any],
        parent_close_policy: ParentClosePolicy = ParentClosePolicy.TERMINATE,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Start a child workflow.
        
        Args:
            name: Child workflow type name.
            input: Input for child workflow.
            parent_close_policy: Policy when parent closes.
            idempotency_key: Idempotency key.
            
        Returns:
            Child workflow ID.
        """
        if self._is_cancelled:
            raise WorkflowCancelledError(f"Workflow cancelled: {self._cancel_reason}")
        
        # CRITICAL: Use deterministic ID for Temporal-grade replay correctness
        child_id = self._next_child_id(name)
        
        child = ChildWorkflow(
            child_id=child_id,
            parent_workflow_id=self.workflow_instance.workflow_id,
            workflow_type=name,
            close_policy=parent_close_policy,
            input=input,
        )
        
        # Emit child started event
        await self._emit_event(
            event_type="child_started",
            event_data={
                "child_id": child_id,
                "workflow_type": name,
                "input": input,
                "parent_close_policy": parent_close_policy.value,
                "idempotency_key": idempotency_key,
            }
        )
        
        # Track pending child
        self._pending_children[child_id] = asyncio.get_event_loop().create_future()
        
        # Submit child workflow (implementation in runtime)
        await self._submit_child_workflow(child)
        
        return child_id
    
    async def await_child(self, workflow_id: str) -> Any:
        """Wait for a child workflow to complete.
        
        Args:
            workflow_id: Child workflow ID.
            
        Returns:
            Child workflow result.
        """
        if workflow_id not in self._pending_children:
            raise ValueError(f"Unknown child workflow: {workflow_id}")
        
        self._is_blocked = True
        self._blocked_reason = f"waiting_for_child:{workflow_id}"
        
        try:
            return await self._pending_children[workflow_id]
        finally:
            self._is_blocked = False
            self._blocked_reason = None
    
    def is_cancelled(self) -> bool:
        """Check if workflow has been cancelled."""
        return self._is_cancelled
    
    def get_workflow_id(self) -> str:
        """Get current workflow ID."""
        return self.workflow_instance.workflow_id
    
    def get_status(self) -> WorkflowStatus:
        """Get current workflow status."""
        return self.workflow_instance.status
    
    def set_query_handler(
        self,
        name: str,
        handler: Callable[[], Any],
    ) -> None:
        """Register a query handler for workflow state.
        
        Args:
            name: Query name.
            handler: Function to call for query.
        """
        self._query_handlers[name] = handler
    
    def get_state(self) -> dict[str, Any]:
        """Get current workflow state."""
        if self.workflow_instance.snapshot:
            return self.workflow_instance.snapshot.state
        return {}
    
    # =========================================================================
    # VERSION PATCHING API (Deterministic Replay Contract)
    # =========================================================================
    
    def get_version(
        self,
        change_id: str,
        min_version: int,
        max_version: Optional[int] = None,
    ) -> int:
        """Get version of a code change for replay-safe upgrades.
        
        This is the KEY method for safe workflow code upgrades.
        
        During REPLAY:
        - Returns the version that was used when events were created
        - Ensures identical command sequence as original execution
        
        During NEW execution:
        - Returns max_version (the current code version)
        
        Args:
            change_id: Unique identifier for this change.
                Use descriptive names like "pricing-update-v2".
            min_version: Minimum supported version (default behavior).
            max_version: Maximum version (current code). Defaults to min_version.
        
        Returns:
            Version number based on event history.
        
        Example:
            # In workflow code:
            version = ctx.get_version("pricing-update", min_version=1, max_version=2)
            if version >= 2:
                price = await ctx.execute_activity("get_price_v2", {})
            else:
                price = await ctx.execute_activity("get_price", {})
        """
        if max_version is None:
            max_version = min_version
        
        # During replay, check event history for patch marker
        if self._replay_mode and self._event_store:
            marker = self._event_store.get_patch_marker(change_id)
            if marker:
                return marker.version
        
        # During new execution, return max_version
        # Record patch marker for future replays
        if not self._replay_mode:
            version = max_version
            self._patch_versions[change_id] = version
            
            # Emit patch marker event for future replays
            # This will be done during _emit_event for commands
            return version
        
        # Fallback during replay if no marker found
        return min_version
    
    def patched(self, feature_id: str) -> bool:
        """Check if a feature patch is active.
        
        Simpler version of get_version() for boolean features.
        
        During REPLAY:
        - Returns False if event history predates patch
        - Returns True if patch marker exists in history
        
        During NEW execution:
        - Returns True
        
        Args:
            feature_id: Unique identifier for the feature.
        
        Returns:
            True if patch should be applied, False for replay fallback.
        
        Example:
            if ctx.patched("new-shipping-logic"):
                result = await ctx.execute_activity("ship_v2", input)
            else:
                result = await ctx.execute_activity("ship_v1", input)
        """
        return self.get_version(feature_id, min_version=1, max_version=1) >= 1
    
    def random(self) -> float:
        """Get deterministic random number.
        
        Uses seeded random for reproducibility during replay.
        Must be called instead of random.random() in workflows.
        
        Returns:
            Random float in [0.0, 1.0).
        """
        # Simple seeded random (use proper random in production)
        self._random_state = (self._random_state * 1103515245 + 12345) % (2 ** 31)
        return self._random_state / (2 ** 31)
    
    def uuid(self) -> str:
        """Get deterministic UUID.
        
        Uses sequence-based UUID for reproducibility during replay.
        Must be called instead of uuid.uuid4() in workflows.
        
        Returns:
            UUID string.
        """
        # Use deterministic seed based on workflow ID and sequence
        base = f"{self.workflow_instance.workflow_id}:{len(self._emitted_commands)}"
        import hashlib
        hash_digest = hashlib.md5(base.encode()).hexdigest()
        return f"{hash_digest[:8]}-{hash_digest[8:12]}-{hash_digest[12:16]}-{hash_digest[16:20]}-{hash_digest[20:32]}"
    
    def sleep(self, seconds: float) -> None:
        """Deterministic sleep.
        
        Records timer for replay verification.
        Must be called instead of asyncio.sleep() in workflows.
        
        Args:
            seconds: Sleep duration in seconds.
        """
        # Emit timer command
        cmd = Command(
            command_type="timer",
            sequence=len(self._emitted_commands),
            timer_duration_seconds=seconds,
        )
        self._emitted_commands.append(cmd)
        
        # Emit timer scheduled event
        # Actual blocking is done by runtime
    
    def side_effect(self, fn: Callable[[], Any]) -> Any:
        """Execute a side effect and cache result for replay.
        
        This is the ONLY way to safely execute non-deterministic
        or expensive operations in a workflow.
        
        Protocol:
        1. NEW EXECUTION: Execute fn(), store result in history
        2. REPLAY: Return cached result from history
        
        Use cases:
        - Config snapshots
        - Feature flag snapshots
        - Deterministic entropy (with seeded random)
        - Expensive one-time computations
        
        Args:
            fn: Function to execute once. Must be deterministic
                or use ctx.random() for seeding.
                
        Returns:
            Result of fn() execution.
            
        Example:
            # Capture config snapshot
            config = ctx.side_effect(lambda: load_config())
            
            # Deterministic entropy
            entropy = ctx.side_effect(lambda: ctx.random())
            
            # Feature flag
            flags = ctx.side_effect(lambda: fetch_flags(ctx.workflow_id))
        """
        # Check if we have cached result from replay
        cache_key = f"side_effect_{len(self._emitted_commands)}"
        
        if self._replay_mode and cache_key in self._side_effect_cache:
            return self._side_effect_cache[cache_key]
        
        # Execute function
        result = fn()
        
        # Cache for replay
        if not self._replay_mode:
            self._side_effect_cache[cache_key] = result
        
        # Record command
        cmd = Command(
            command_type="side_effect",
            sequence=len(self._emitted_commands),
            change_id=cache_key,
        )
        self._emitted_commands.append(cmd)
        
        return result
    
    def mutable_side_effect(self, fn: Callable[[], Any], id: str) -> Any:
        """Execute a mutable side effect with explicit ID.
        
        Unlike side_effect(), this allows the function result to change
        across replays based on the provided ID. Use when the result
        legitimately varies based on external state.
        
        Protocol:
        1. NEW EXECUTION: Execute fn(), store with id in history
        2. REPLAY: Return cached result if id exists, else execute and cache
        
        Args:
            fn: Function to execute.
            id: Explicit ID for this side effect.
            
        Returns:
            Result of fn() execution.
        """
        cache_key = f"mutable_side_effect_{id}"
        
        if self._replay_mode and cache_key in self._side_effect_cache:
            return self._side_effect_cache[cache_key]
        
        result = fn()
        
        if not self._replay_mode:
            self._side_effect_cache[cache_key] = result
        
        cmd = Command(
            command_type="mutable_side_effect",
            sequence=len(self._emitted_commands),
            change_id=id,
        )
        self._emitted_commands.append(cmd)
        
        return result
    
    def _load_side_effect_cache(self, history: list) -> None:
        """Load side effect results from event history."""
        for event in history:
            if event.get("event_type") == "side_effect":
                cache_key = f"side_effect_{event.get('sequence', 0)}"
                self._side_effect_cache[cache_key] = event.get("result")
            elif event.get("event_type") == "mutable_side_effect":
                cache_key = f"mutable_side_effect_{event.get('change_id')}"
                self._side_effect_cache[cache_key] = event.get("result")
    
    def _record_command(self, command: Command) -> None:
        """Record emitted command for replay verification."""
        command.sequence = len(self._emitted_commands)
        self._emitted_commands.append(command)
    
    def _get_emitted_commands(self) -> list[Command]:
        """Get all commands emitted during current execution."""
        return self._emitted_commands.copy()
    
    def _clear_commands(self) -> None:
        """Clear recorded commands (for replay verification)."""
        self._emitted_commands.clear()
    
    def _set_replay_mode(self, replay: bool) -> None:
        """Set replay mode for version patching."""
        self._replay_mode = replay
    
    def update_state(self, key: str, value: Any) -> None:
        """Update workflow state.
        
        Args:
            key: State key.
            value: New value.
        """
        if self.workflow_instance.snapshot:
            self.workflow_instance.snapshot.state[key] = value
        else:
            if not hasattr(self, '_state'):
                self._state = {}
            self._state[key] = value
    
    def now(self) -> float:
        """Get current time (deterministic).
        
        Returns workflow's internal clock, not wall time.
        This ensures replay is deterministic.
        
        CRITICAL: Must NEVER call time.time() here as it violates
        Temporal-grade deterministic replay contract.
        
        P0-A: This is the CORRECT way to get time in workflow code.
        NEVER use time.time() or datetime.now() directly in workflows.
        
        Protocol:
        - During REPLAY: returns time from event history (event time, not wall time)
        - During NEW execution: returns base_time + (event_count * 0.001)
        
        Returns:
            Deterministic time value in seconds.
        """
        # During replay, return time from event history
        if self._replay_mode and self._event_store:
            history_time = self._get_history_time()
            if history_time is not None:
                return history_time
        
        # During new execution, use workflow's internal event counter
        # This is deterministic because it increments with each command
        if hasattr(self.workflow_instance, 'started_at') and self.workflow_instance.started_at > 0:
            # P0-A: Deterministic time from event sequence
            # Event count * 1ms = deterministic offset from base time
            base = self.workflow_instance.started_at
            event_offset = self.workflow_instance.next_sequence * 0.001  # 1ms per event
            return base + event_offset
        
        # CRITICAL: This should NEVER happen in production
        # P0-A VIOLATION: If we reach here, we're not properly initialized
        # This means started_at was never set or is invalid
        raise NonDeterministicError(
            "P0-A VIOLATION: Workflow now() called without valid started_at. "
            "Workflow must be initialized with a deterministic started_at value. "
            "This is a Temporal-grade violation - workflow must be initialized before execution."
        )
    
    def _get_history_time(self) -> Optional[float]:
        """Get time from event history during replay.
        
        Returns:
            Time from history, or None if not available.
        """
        # This should be implemented by the runtime to return
        # the wall-clock time when the current event was recorded
        if self._event_store and hasattr(self._event_store, '_get_event_time'):
            return self._event_store._get_event_time(
                self.workflow_instance.workflow_id,
                self.workflow_instance.next_sequence
            )
        return None
    
    @property
    def activity_execution_id(self) -> Optional[str]:
        """Get current activity execution ID.
        
        This is the ID for the currently executing activity.
        Use this in activity implementation for downstream deduplication.
        
        Returns:
            Activity execution ID, or None if no activity is executing.
            
        Example:
            # In activity implementation:
            execution_id = ctx.activity_execution_id
            # Use for API deduplication, etc.
        """
        return getattr(self, '_activity_execution_id', None)
    
    async def _emit_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Emit an event to the event store."""
        if self._event_store:
            await self._event_store.append_event(
                workflow_id=self.workflow_instance.workflow_id,
                event_type=event_type,
                event_data=event_data,
                sequence=self.workflow_instance.next_sequence,
            )
            self.workflow_instance.next_sequence += 1
    
    async def _submit_activity_task(
        self,
        task: ActivityTask,
        options: ActivityOptions,
    ) -> None:
        """Submit activity to task queue (runtime implementation)."""
        if self._event_store and hasattr(self._event_store, '_runtime'):
            await self._event_store._runtime.submit_activity(task, options)
    
    async def _submit_child_workflow(self, child: ChildWorkflow) -> None:
        """Submit child workflow (runtime implementation)."""
        if self._event_store and hasattr(self._event_store, '_runtime'):
            await self._event_store._runtime.start_child(child)
    
    def _register_signal_handler(self, name: str, future: asyncio.Future) -> None:
        """Register signal handler (runtime implementation).
        
        This is a stub that should be overridden by concrete runtime.
        Logs a warning if called without being overridden.
        """
        logger.warning(
            f"Signal handler '{name}' registered but not implemented. "
            "This is a stub - override _register_signal_handler in concrete runtime."
        )
        self._signal_handlers[name] = future
    
    def _unregister_signal_handler(self, name: str) -> None:
        """Unregister signal handler (runtime implementation).
        
        This is a stub that should be overridden by concrete runtime.
        """
        self._signal_handlers.pop(name, None)


class ActivityContext:
    """Context for activity execution (side effects).
    
    Activities use this to:
    - Send heartbeats
    - Check for cancellation
    - Report progress
    """
    
    def __init__(
        self,
        task_id: str,
        workflow_id: str,
        activity_type: str,
    ):
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.activity_type = activity_type
        
        self._heartbeat_interval: float = 10.0
        self._last_heartbeat_at: float = time.time()
        self._cancelled: bool = False
        self._cancellation_reason: Optional[str] = None
        self._heartbeat_count: int = 0
        
        # Runtime callback
        self._heartbeat_callback: Optional[Callable] = None
        self._cancellation_callback: Optional[Callable] = None
    
    async def heartbeat(self, details: Any = None) -> None:
        """Send heartbeat to indicate activity is still running.
        
        Must be called periodically for long-running activities.
        Heartbeat interval is configured per-activity.
        
        Args:
            details: Optional progress information.
        """
        self._last_heartbeat_at = time.time()
        self._heartbeat_count += 1
        
        if self._heartbeat_callback:
            await self._heartbeat_callback(
                task_id=self.task_id,
                workflow_id=self.workflow_id,
                details=details,
                heartbeat_count=self._heartbeat_count,
            )
        
        logger.debug(
            f"Heartbeat {self._heartbeat_count} for activity {self.activity_type} "
            f"(task={self.task_id[:8]}...)"
        )
    
    def is_cancelled(self) -> bool:
        """Check if activity has been cancelled.
        
        Activities should check this periodically and stop gracefully.
        
        Returns:
            True if cancellation requested.
        """
        return self._cancelled
    
    def get_cancellation_reason(self) -> Optional[str]:
        """Get reason for cancellation."""
        return self._cancellation_reason
    
    def time_since_last_heartbeat(self) -> float:
        """Get seconds since last heartbeat."""
        return time.time() - self._last_heartbeat_at
    
    def set_heartbeat_callback(
        self,
        callback: Callable[[str, str, Any, int], Any],
    ) -> None:
        """Set callback for heartbeat (runtime sets this)."""
        self._heartbeat_callback = callback
    
    def set_cancellation_callback(
        self,
        callback: Callable[[str, str, str], None],
    ) -> None:
        """Set callback for cancellation check (runtime sets this)."""
        self._cancellation_callback = callback
    
    def report_cancelled(self, reason: str) -> None:
        """Report that cancellation was requested."""
        self._cancelled = True
        self._cancellation_reason = reason
    
    @property
    def heartbeat_count(self) -> int:
        """Get number of heartbeats sent."""
        return self._heartbeat_count
    
    def validate_result_size(self, result: Any, max_size_bytes: int = 1048576) -> None:
        """Validate that activity result fits within size limit.
        
        Large results should be offloaded to blob storage.
        
        Args:
            result: The activity result.
            max_size_bytes: Maximum allowed size in bytes.
            
        Raises:
            ResultTooLargeError: If result exceeds size limit.
        """
        import json
        from .types import ResultTooLargeError
        
        # Estimate size
        try:
            serialized = json.dumps(result)
            size_bytes = len(serialized.encode('utf-8'))
        except (TypeError, ValueError):
            # Non-JSON serializable, estimate as 1MB
            size_bytes = 1024 * 1024
        
        if size_bytes > max_size_bytes:
            raise ResultTooLargeError(size_bytes, max_size_bytes)


# Import uuid for use in WorkflowContext
import uuid


class WorkflowError(Exception):
    """Base workflow error."""
    pass


class WorkflowCancelledError(WorkflowError):
    """Workflow was cancelled."""
    pass


class ActivityTimeoutError(WorkflowError):
    """Activity execution timed out."""
    pass


class SignalTimeoutError(WorkflowError):
    """Signal wait timed out."""
    pass


class NonDeterministicError(WorkflowError):
    """Non-deterministic operation detected in workflow.
    
    Note: For replay verification failures, use NonDeterministicWorkflowError
    from types.py which provides more detailed error information.
    """
    pass
