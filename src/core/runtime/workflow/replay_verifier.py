"""Replay Verifier - Phase 5A (v7).

Command sequence verification for deterministic replay contract.
Verifies that workflow produces identical commands during replay.

Full Fidelity Comparison:
- Activity: name + input_hash + options + retry_policy
- Child: type + input_hash + options + close_policy
- Signal: name + timeout + payload_hash
- Timer: id + duration (idempotent by nature)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict
from enum import Enum

logger = logging.getLogger(__name__)


def _compute_input_hash(input_data: Any) -> str:
    """Compute deterministic hash of input data."""
    if input_data is None:
        return "null"
    try:
        serialized = json.dumps(input_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return hashlib.sha256(str(input_data).encode()).hexdigest()[:16]


class CommandType(str, Enum):
    """Types of workflow commands."""
    SCHEDULE_ACTIVITY = "schedule_activity"
    START_CHILD = "start_child"
    WAIT_SIGNAL = "wait_signal"
    START_TIMER = "start_timer"
    CANCEL_TIMER = "cancel_timer"
    UPSERT_SEARCH_ATTRIBUTES = "upsert_search_attributes"
    MODIFY_WORKFLOW_PROPERTIES = "modify_workflow_properties"


@dataclass
class RetryPolicy:
    """Retry policy for activity/child commands."""
    max_attempts: int = 1
    initial_interval_ms: int = 1000
    backoff_multiplier: float = 2.0
    max_interval_ms: int = 60000
    retry_on_errors: List[str] = field(default_factory=list)
    
    def to_hash_key(self) -> str:
        """Convert to hashable key for comparison."""
        return json.dumps({
            "max_attempts": self.max_attempts,
            "initial_interval_ms": self.initial_interval_ms,
            "backoff_multiplier": self.backoff_multiplier,
            "max_interval_ms": self.max_interval_ms,
            "retry_on_errors": sorted(self.retry_on_errors),
        }, sort_keys=True)


@dataclass
class ActivityOptions:
    """Options for activity execution."""
    timeout_seconds: Optional[float] = None
    retry_policy: Optional[RetryPolicy] = None
    idempotency_key: Optional[str] = None
    heartbeat_interval_seconds: float = 10.0
    schedule_to_start_timeout_seconds: float = 60.0
    
    def to_hash_key(self) -> str:
        """Convert to hashable key for comparison."""
        retry_key = self.retry_policy.to_hash_key() if self.retry_policy else "none"
        return json.dumps({
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": retry_key,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "schedule_to_start_timeout_seconds": self.schedule_to_start_timeout_seconds,
        }, sort_keys=True)


@dataclass
class ChildOptions:
    """Options for child workflow."""
    close_policy: str = "terminate"
    retry_policy: Optional[RetryPolicy] = None
    parent_close_policy: Optional[str] = None
    workflow_execution_timeout_seconds: Optional[float] = None
    run_timeout_seconds: Optional[float] = None
    
    def to_hash_key(self) -> str:
        """Convert to hashable key for comparison."""
        retry_key = self.retry_policy.to_hash_key() if self.retry_policy else "none"
        return json.dumps({
            "close_policy": self.close_policy,
            "retry_policy": retry_key,
            "parent_close_policy": self.parent_close_policy,
            "workflow_execution_timeout_seconds": self.workflow_execution_timeout_seconds,
            "run_timeout_seconds": self.run_timeout_seconds,
        }, sort_keys=True)


@dataclass
class Command:
    """A command emitted during workflow execution.
    
    Commands are the fundamental unit of deterministic replay verification.
    Each command must match exactly during replay.
    
    Full Fidelity Fields:
    - command_id: Unique identifier for idempotency
    - sequence: Order in execution
    - input_hash: SHA256 of input for verification
    - options_hash: Hash of all execution options
    - version_marker: For workflow code versioning
    """
    command_type: str  # CommandType value
    command_id: str = ""  # Unique command ID for idempotency
    sequence: int = 0  # Order in which command was emitted
    
    # Full fidelity input tracking
    input_hash: str = ""  # SHA256 hash of input for verification
    
    # Command specifics - Activity
    activity_name: Optional[str] = None
    activity_input: Optional[dict] = None
    activity_options: Optional[ActivityOptions] = None
    activity_options_hash: str = ""  # Pre-computed hash for fast comparison
    
    # Command specifics - Child Workflow
    child_workflow_type: Optional[str] = None
    child_input: Optional[dict] = None
    child_options: Optional[ChildOptions] = None
    child_options_hash: str = ""
    
    # Command specifics - Signal
    signal_name: Optional[str] = None
    signal_payload: Optional[dict] = None
    signal_payload_hash: str = ""
    signal_timeout_seconds: Optional[float] = None
    
    # Command specifics - Timer
    timer_duration_seconds: Optional[float] = None
    timer_id: Optional[str] = None  # For idempotent timer cancellation
    
    # Version patching
    change_id: Optional[str] = None
    version: Optional[int] = None
    
    # Side effect tracking
    side_effect_marker: Optional[str] = None
    
    # Metadata
    created_at: float = 0.0
    
    def __post_init__(self):
        """Compute hashes after initialization."""
        # Compute input hash if not set
        if not self.input_hash:
            if self.activity_input is not None:
                self.input_hash = _compute_input_hash(self.activity_input)
            elif self.child_input is not None:
                self.input_hash = _compute_input_hash(self.child_input)
            elif self.signal_payload is not None:
                self.input_hash = _compute_input_hash(self.signal_payload)
            else:
                self.input_hash = "none"
        
        # Compute options hash if not set
        if not self.activity_options_hash and self.activity_options:
            self.activity_options_hash = hashlib.sha256(
                self.activity_options.to_hash_key().encode()
            ).hexdigest()
        
        if not self.child_options_hash and self.child_options:
            self.child_options_hash = hashlib.sha256(
                self.child_options.to_hash_key().encode()
            ).hexdigest()
        
        if not self.signal_payload_hash and self.signal_payload:
            self.signal_payload_hash = _compute_input_hash(self.signal_payload)
    
    def to_event_data(self) -> dict:
        """Convert command to event data for storage."""
        return {
            "command_type": self.command_type,
            "command_id": self.command_id,
            "input_hash": self.input_hash,
            "activity_name": self.activity_name,
            "activity_input_hash": self.input_hash if self.activity_input else None,
            "activity_options_hash": self.activity_options_hash,
            "child_workflow_type": self.child_workflow_type,
            "child_input_hash": self.input_hash if self.child_input else None,
            "child_options_hash": self.child_options_hash,
            "signal_name": self.signal_name,
            "signal_payload_hash": self.signal_payload_hash,
            "signal_timeout_seconds": self.signal_timeout_seconds,
            "timer_duration_seconds": self.timer_duration_seconds,
            "timer_id": self.timer_id,
            "change_id": self.change_id,
            "version": self.version,
            "side_effect_marker": self.side_effect_marker,
        }
    
    def get_full_fidelity_key(self) -> str:
        """Get full fidelity comparison key.
        
        This is the CRITICAL method for production replay.
        Must include ALL attributes that affect execution behavior.
        """
        parts = [self.command_type]
        
        if self.command_type == CommandType.SCHEDULE_ACTIVITY:
            parts.extend([
                self.activity_name or "",
                self.input_hash,
                self.activity_options_hash,
            ])
        elif self.command_type == CommandType.START_CHILD:
            parts.extend([
                self.child_workflow_type or "",
                self.input_hash,
                self.child_options_hash,
            ])
        elif self.command_type == CommandType.WAIT_SIGNAL:
            parts.extend([
                self.signal_name or "",
                str(self.signal_timeout_seconds or ""),
                self.signal_payload_hash,
            ])
        elif self.command_type == CommandType.START_TIMER:
            parts.extend([
                str(self.timer_duration_seconds or ""),
                self.timer_id or "",
            ])
        
        return "|".join(parts)
    
    def __eq__(self, other: Any) -> bool:
        """Full fidelity command comparison for production replay."""
        if not isinstance(other, Command):
            return False
        
        if self.command_type != other.command_type:
            return False
        
        return self.get_full_fidelity_key() == other.get_full_fidelity_key()
    
    def __hash__(self) -> int:
        """Hash based on full fidelity key."""
        return hash(self.get_full_fidelity_key())


@dataclass
class MismatchDetail:
    """Details of a command mismatch during replay."""
    position: int
    expected: Optional[Command]
    actual: Optional[Command]
    reason: str


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
        workflow_version: Optional[str] = None,
        tool_version: Optional[str] = None,
    ):
        self.workflow_id = workflow_id
        self.expected_sequence = expected_sequence
        self.actual_sequence = actual_sequence
        self.mismatch_at = mismatch_at
        self.reason = reason
        self.workflow_version = workflow_version
        self.tool_version = tool_version
        
        # Build detailed message for forensics
        expected_cmd = expected_sequence[mismatch_at] if mismatch_at < len(expected_sequence) else None
        actual_cmd = actual_sequence[mismatch_at] if mismatch_at < len(actual_sequence) else None
        
        # Build expected vs actual comparison
        expected_detail = self._format_command(expected_cmd)
        actual_detail = self._format_command(actual_cmd)
        
        msg_parts = [
            f"Non-deterministic workflow detected: {workflow_id}",
            f"Version: workflow={workflow_version or 'unknown'}, tool={tool_version or 'unknown'}",
            f"Mismatch at command position {mismatch_at}",
            f"Reason: {reason}",
            f"",
            f"Expected command:",
            expected_detail,
            f"",
            f"Actual command:",
            actual_detail,
            f"",
            f"Full replay state:",
            self._format_replay_state(),
            f"",
            f"Fix: Use ctx.get_version() or ctx.patched() for replay-safe code upgrades.",
            f"See: https://docs.temporal.io/encyclopedia/versioning",
        ]
        
        super().__init__("\n".join(msg_parts))
    
    def _format_command(self, cmd: Optional[Command]) -> str:
        """Format command for display."""
        if cmd is None:
            return "  (no command)"
        
        parts = [
            f"  type: {cmd.command_type}",
            f"  id: {cmd.command_id or '(none)'}",
        ]
        
        if cmd.command_type == CommandType.SCHEDULE_ACTIVITY:
            parts.append(f"  activity: {cmd.activity_name}")
            parts.append(f"  input_hash: {cmd.input_hash}")
            parts.append(f"  options_hash: {cmd.activity_options_hash}")
        elif cmd.command_type == CommandType.START_CHILD:
            parts.append(f"  child_type: {cmd.child_workflow_type}")
            parts.append(f"  input_hash: {cmd.input_hash}")
            parts.append(f"  options_hash: {cmd.child_options_hash}")
        elif cmd.command_type == CommandType.WAIT_SIGNAL:
            parts.append(f"  signal: {cmd.signal_name}")
            parts.append(f"  timeout: {cmd.signal_timeout_seconds}s")
            parts.append(f"  payload_hash: {cmd.signal_payload_hash}")
        elif cmd.command_type == CommandType.START_TIMER:
            parts.append(f"  duration: {cmd.timer_duration_seconds}s")
            parts.append(f"  timer_id: {cmd.timer_id}")
        
        return "\n".join(parts)
    
    def _format_replay_state(self) -> str:
        """Format replay state for display."""
        return (
            f"  expected_count: {len(self.expected_sequence)}, "
            f"actual_count: {len(self.actual_sequence)}, "
            f"mismatch_at: {self.mismatch_at}"
        )
    
    @property
    def suggested_fix(self) -> str:
        return (
            f"Workflow {self.workflow_id} became non-deterministic at position {self.mismatch_at}. "
            f"Command differs: {self.reason}. "
            f"Use get_version() or patched() for safe code upgrades."
        )


class ReplayVerifier:
    """Verifier for deterministic replay contract.
    
    Verifies that workflow produces identical command sequence
    during replay as during original execution.
    
    Command Verification Protocol (Full Fidelity):
    1. Load event history: [E1, E2, E3, ..., En]
    2. Load current workflow code
    3. Reset workflow state to initial
    4. Replay events in order:
       FOR each event Ei:
         - Apply event to state
         - Continue workflow execution
         - Collect emitted commands
         - Verify command matches next historical command
           using FULL FIDELITY comparison:
           - Activity: name + input_hash + options_hash
           - Child: type + input_hash + options_hash
           - Signal: name + timeout + payload_hash
           - Timer: duration + timer_id
    5. IF mismatch:
       - HALT replay
       - Throw NonDeterministicWorkflowError
       - Log divergence point with FULL DETAIL
    6. IF complete match:
       - Continue normal execution
       - New commands appended to history
    """
    
    def __init__(self, event_store: Any = None):
        self._event_store = event_store
        
        # Historical commands (from event log)
        self._historical_commands: List[Command] = []
        self._historical_index: int = 0
        
        # Emitted commands during replay
        self._emitted_commands: List[Command] = []
        
        # State
        self._is_replay: bool = False
        self._workflow_id: Optional[str] = None
        self._workflow_version: Optional[str] = None
        self._tool_version: Optional[str] = None
    
    def start_replay(
        self,
        workflow_id: str,
        workflow_version: Optional[str] = None,
        tool_version: Optional[str] = None,
    ) -> None:
        """Start replay mode for a workflow.
        
        Args:
            workflow_id: Workflow ID being replayed.
            workflow_version: Version of workflow code for diagnostics.
            tool_version: Version of runtime tool for diagnostics.
        """
        self._is_replay = True
        self._workflow_id = workflow_id
        self._workflow_version = workflow_version
        self._tool_version = tool_version
        self._historical_commands = []
        self._emitted_commands = []
        self._historical_index = 0
    
    def end_replay(self) -> None:
        """End replay mode."""
        self._is_replay = False
        self._workflow_id = None
        self._workflow_version = None
        self._tool_version = None
        self._historical_commands = []
        self._emitted_commands = []
        self._historical_index = 0
    
    def load_historical_commands(
        self,
        commands: List[Command],
    ) -> None:
        """Load historical commands from event log.
        
        Args:
            commands: List of commands from original execution.
        """
        self._historical_commands = commands.copy()
        self._historical_index = 0
    
    async def verify_command(
        self,
        command: Command,
    ) -> bool:
        """Verify a single command matches expected (full fidelity).
        
        Args:
            command: Command emitted during replay.
            
        Returns:
            True if command matches, False otherwise.
            
        Raises:
            NonDeterministicWorkflowError: If command doesn't match.
        """
        if not self._is_replay:
            return True
        
        # Check if we have expected commands
        if self._historical_index >= len(self._historical_commands):
            raise NonDeterministicWorkflowError(
                workflow_id=self._workflow_id,
                expected_sequence=self._historical_commands,
                actual_sequence=self._emitted_commands + [command],
                mismatch_at=self._historical_index,
                reason="Extra command during replay - no expected command",
                workflow_version=self._workflow_version,
                tool_version=self._tool_version,
            )
        
        expected = self._historical_commands[self._historical_index]
        
        # Full fidelity comparison
        if not self._commands_match(expected, command):
            raise NonDeterministicWorkflowError(
                workflow_id=self._workflow_id,
                expected_sequence=self._historical_commands,
                actual_sequence=self._emitted_commands + [command],
                mismatch_at=self._historical_index,
                reason=self._get_mismatch_reason(expected, command),
                workflow_version=self._workflow_version,
                tool_version=self._tool_version,
            )
        
        # Record and advance
        self._emitted_commands.append(command)
        self._historical_index += 1
        
        logger.debug(
            f"Command verified at position {self._historical_index}: "
            f"{command.command_type}"
        )
        
        return True
    
    def _commands_match(
        self,
        expected: Command,
        actual: Command,
    ) -> bool:
        """Full fidelity command comparison.
        
        Compares ALL attributes that affect execution behavior:
        - Command type
        - Input hash
        - Options hash
        - Timeout values
        - Timer IDs
        """
        return expected == actual
    
    def _get_mismatch_reason(
        self,
        expected: Command,
        actual: Command,
    ) -> str:
        """Get detailed human-readable mismatch reason for forensics."""
        reasons = []
        
        # Command type check
        if expected.command_type != actual.command_type:
            reasons.append(
                f"Command type: expected '{expected.command_type}', "
                f"got '{actual.command_type}'"
            )
        
        # Full fidelity key comparison
        expected_key = expected.get_full_fidelity_key()
        actual_key = actual.get_full_fidelity_key()
        
        if expected_key != actual_key:
            # Parse which specific fields differ
            if expected.command_type == CommandType.SCHEDULE_ACTIVITY:
                field_diffs = []
                if expected.activity_name != actual.activity_name:
                    field_diffs.append(
                        f"activity_name: '{expected.activity_name}' != '{actual.activity_name}'"
                    )
                if expected.input_hash != actual.input_hash:
                    field_diffs.append(
                        f"activity_input: hash mismatch "
                        f"(expected: {expected.input_hash}, "
                        f"got: {actual.input_hash})"
                    )
                if expected.activity_options_hash != actual.activity_options_hash:
                    field_diffs.append(
                        f"activity_options: hash mismatch "
                        f"(expected: {expected.activity_options_hash}, "
                        f"got: {actual.activity_options_hash})"
                    )
                reasons.append("; ".join(field_diffs) if field_diffs else "Activity fields differ")
            
            elif expected.command_type == CommandType.START_CHILD:
                field_diffs = []
                if expected.child_workflow_type != actual.child_workflow_type:
                    field_diffs.append(
                        f"child_workflow_type: '{expected.child_workflow_type}' != '{actual.child_workflow_type}'"
                    )
                if expected.input_hash != actual.input_hash:
                    field_diffs.append(
                        f"child_input: hash mismatch "
                        f"(expected: {expected.input_hash}, "
                        f"got: {actual.input_hash})"
                    )
                if expected.child_options_hash != actual.child_options_hash:
                    field_diffs.append(
                        f"child_options: hash mismatch "
                        f"(expected: {expected.child_options_hash}, "
                        f"got: {actual.child_options_hash})"
                    )
                reasons.append("; ".join(field_diffs) if field_diffs else "Child workflow fields differ")
            
            elif expected.command_type == CommandType.WAIT_SIGNAL:
                field_diffs = []
                if expected.signal_name != actual.signal_name:
                    field_diffs.append(
                        f"signal_name: '{expected.signal_name}' != '{actual.signal_name}'"
                    )
                if expected.signal_timeout_seconds != actual.signal_timeout_seconds:
                    field_diffs.append(
                        f"timeout: {expected.signal_timeout_seconds}s != {actual.signal_timeout_seconds}s"
                    )
                if expected.signal_payload_hash != actual.signal_payload_hash:
                    field_diffs.append(
                        f"signal_payload: hash mismatch"
                    )
                reasons.append("; ".join(field_diffs) if field_diffs else "Signal fields differ")
            
            elif expected.command_type == CommandType.START_TIMER:
                field_diffs = []
                if expected.timer_duration_seconds != actual.timer_duration_seconds:
                    field_diffs.append(
                        f"duration: {expected.timer_duration_seconds}s != {actual.timer_duration_seconds}s"
                    )
                if expected.timer_id != actual.timer_id:
                    field_diffs.append(
                        f"timer_id: '{expected.timer_id}' != '{actual.timer_id}'"
                    )
                reasons.append("; ".join(field_diffs) if field_diffs else "Timer fields differ")
        
        return " | ".join(reasons) if reasons else "Unknown mismatch"
    
    def get_mismatch_detail(
        self,
        workflow_id: str,
    ) -> Optional[MismatchDetail]:
        """Get details of mismatch if verification failed."""
        if self._historical_index < len(self._historical_commands):
            return MismatchDetail(
                position=self._historical_index,
                expected=self._historical_commands[self._historical_index],
                actual=None,
                reason="Missing command during replay",
            )
        
        if self._historical_index < len(self._emitted_commands):
            return MismatchDetail(
                position=self._historical_index,
                expected=None,
                actual=self._emitted_commands[self._historical_index],
                reason="Extra command during replay",
            )
        
        return None
    
    def is_replay_complete(self) -> bool:
        """Check if replay is complete."""
        return self._historical_index >= len(self._historical_commands)
    
    def get_replay_state(self) -> dict:
        """Get current replay state for debugging."""
        return {
            "workflow_id": self._workflow_id,
            "workflow_version": self._workflow_version,
            "tool_version": self._tool_version,
            "is_replay": self._is_replay,
            "historical_count": len(self._historical_commands),
            "historical_index": self._historical_index,
            "emitted_count": len(self._emitted_commands),
            "remaining_commands": len(self._historical_commands) - self._historical_index,
            "is_complete": self.is_replay_complete(),
        }


class CommandRecorder:
    """Records commands emitted during workflow execution.
    
    Used both for original execution (to store) and
    replay verification (to compare).
    """
    
    def __init__(self, workflow_id: str):
        self._workflow_id = workflow_id
        self._commands: List[Command] = []
        self._lock = asyncio.Lock()
    
    async def record(
        self,
        command_type: str,
        **kwargs,
    ) -> Command:
        """Record a command.
        
        Args:
            command_type: Type of command.
            **kwargs: Command-specific attributes.
            
        Returns:
            Created Command.
        """
        import uuid
        
        command = Command(
            command_type=command_type,
            command_id=str(uuid.uuid4()),
            sequence=len(self._commands),
            **kwargs,
        )
        
        async with self._lock:
            self._commands.append(command)
        
        return command
    
    async def record_activity(
        self,
        activity_name: str,
        input: dict,
        options: dict = None,
    ) -> Command:
        """Record schedule activity command."""
        return await self.record(
            CommandType.SCHEDULE_ACTIVITY,
            activity_name=activity_name,
            activity_input=input,
            activity_options=options,
        )
    
    async def record_child_workflow(
        self,
        workflow_type: str,
        input: dict,
        options: dict = None,
    ) -> Command:
        """Record start child command."""
        return await self.record(
            CommandType.START_CHILD,
            child_workflow_type=workflow_type,
            child_input=input,
            child_options=options,
        )
    
    async def record_signal_wait(
        self,
        signal_name: str,
        timeout_seconds: float = None,
    ) -> Command:
        """Record wait signal command."""
        return await self.record(
            CommandType.WAIT_SIGNAL,
            signal_name=signal_name,
            signal_timeout_seconds=timeout_seconds,
        )
    
    async def record_timer(
        self,
        duration_seconds: float,
        timer_id: str = None,
    ) -> Command:
        """Record start timer command."""
        import uuid
        return await self.record(
            CommandType.START_TIMER,
            timer_duration_seconds=duration_seconds,
            timer_id=timer_id or str(uuid.uuid4()),
        )
    
    def get_commands(self) -> List[Command]:
        """Get all recorded commands."""
        return self._commands.copy()
    
    def clear(self) -> None:
        """Clear all recorded commands."""
        self._commands.clear()


class IllegalOperationError(Exception):
    """Raised when workflow code uses non-deterministic operations."""
    
    def __init__(
        self,
        operation: str,
        suggestion: str,
    ):
        self.operation = operation
        self.suggestion = suggestion
        
        msg = (
            f"Illegal non-deterministic operation detected: {operation}\n"
            f"Suggestion: {suggestion}"
        )
        super().__init__(msg)


# Registry of illegal operations
ILLEGAL_OPERATIONS = {
    "time.time()": "Use ctx.now() instead",
    "time.monotonic()": "Use ctx.now() instead",
    "datetime.now()": "Use ctx.now() instead",
    "random.random()": "Use ctx.random() instead",
    "random.randint()": "Use ctx.random() instead",
    "uuid.uuid4()": "Use ctx.uuid() instead",
    "asyncio.sleep()": "Use ctx.sleep() instead",
    "file.read()": "Use activity for file I/O",
    "file.write()": "Use activity for file I/O",
    "requests.get()": "Use activity for HTTP",
    "requests.post()": "Use activity for HTTP",
    "http.client": "Use activity for HTTP",
    "urllib.request": "Use activity for HTTP",
}


def check_illegal_operations(code: str) -> List[str]:
    """Check code for illegal non-deterministic operations.
    
    Args:
        code: Workflow code to check.
        
    Returns:
        List of violations found.
    """
    violations = []
    
    for operation, suggestion in ILLEGAL_OPERATIONS.items():
        if operation in code:
            violations.append(f"{operation}: {suggestion}")
    
    return violations
