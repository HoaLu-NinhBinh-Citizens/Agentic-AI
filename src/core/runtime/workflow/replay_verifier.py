"""Replay Verifier - Phase 5A (v6).

Command sequence verification for deterministic replay contract.
Verifies that workflow produces identical commands during replay.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


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
class Command:
    """A command emitted during workflow execution.
    
    Commands are the fundamental unit of deterministic replay verification.
    Each command must match exactly during replay.
    """
    command_type: str  # CommandType value
    command_id: str = ""  # Unique command ID
    sequence: int = 0  # Order in which command was emitted
    
    # Command specifics
    activity_name: Optional[str] = None
    activity_input: Optional[dict] = None
    activity_options: Optional[dict] = None
    
    child_workflow_type: Optional[str] = None
    child_input: Optional[dict] = None
    child_options: Optional[dict] = None
    
    signal_name: Optional[str] = None
    signal_payload: Optional[dict] = None
    signal_timeout_seconds: Optional[float] = None
    
    timer_duration_seconds: Optional[float] = None
    timer_id: Optional[str] = None
    
    # Version patching
    change_id: Optional[str] = None
    version: Optional[int] = None
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    
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
    
    def __eq__(self, other: Any) -> bool:
        """Commands are equal if they have same type and key attributes."""
        if not isinstance(other, Command):
            return False
        
        if self.command_type != other.command_type:
            return False
        
        # Compare key attributes based on command type
        if self.command_type == CommandType.SCHEDULE_ACTIVITY:
            return self.activity_name == other.activity_name
        elif self.command_type == CommandType.START_CHILD:
            return self.child_workflow_type == other.child_workflow_type
        elif self.command_type == CommandType.WAIT_SIGNAL:
            return self.signal_name == other.signal_name
        elif self.command_type == CommandType.START_TIMER:
            return self.timer_duration_seconds == other.timer_duration_seconds
        
        return True
    
    def __hash__(self) -> int:
        """Hash based on command type and key attributes."""
        key = (self.command_type,)
        
        if self.command_type == CommandType.SCHEDULE_ACTIVITY:
            key = (self.command_type, self.activity_name)
        elif self.command_type == CommandType.START_CHILD:
            key = (self.command_type, self.child_workflow_type)
        elif self.command_type == CommandType.WAIT_SIGNAL:
            key = (self.command_type, self.signal_name)
        elif self.command_type == CommandType.START_TIMER:
            key = (self.command_type, self.timer_duration_seconds)
        
        return hash(key)


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


class ReplayVerifier:
    """Verifier for deterministic replay contract.
    
    Verifies that workflow produces identical command sequence
    during replay as during original execution.
    
    Command Verification Protocol:
    1. Load event history: [E1, E2, E3, ..., En]
    2. Load current workflow code
    3. Reset workflow state to initial
    4. Replay events in order:
       FOR each event Ei:
         - Apply event to state
         - Continue workflow execution
         - Collect emitted commands
         - Verify command matches next historical command
    5. IF mismatch:
       - HALT replay
       - Throw NonDeterministicWorkflowError
       - Log divergence point
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
    
    def start_replay(self, workflow_id: str) -> None:
        """Start replay mode for a workflow.
        
        Args:
            workflow_id: Workflow ID being replayed.
        """
        self._is_replay = True
        self._workflow_id = workflow_id
        self._historical_commands = []
        self._emitted_commands = []
        self._historical_index = 0
    
    def end_replay(self) -> None:
        """End replay mode."""
        self._is_replay = False
        self._workflow_id = None
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
        """Verify a single command matches expected.
        
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
            )
        
        expected = self._historical_commands[self._historical_index]
        
        # Compare commands
        if not self._commands_match(expected, command):
            raise NonDeterministicWorkflowError(
                workflow_id=self._workflow_id,
                expected_sequence=self._historical_commands,
                actual_sequence=self._emitted_commands + [command],
                mismatch_at=self._historical_index,
                reason=self._get_mismatch_reason(expected, command),
            )
        
        # Record and advance
        self._emitted_commands.append(command)
        self._historical_index += 1
        
        return True
    
    def _commands_match(
        self,
        expected: Command,
        actual: Command,
    ) -> bool:
        """Check if commands match.
        
        Commands match if they have same type and essential attributes.
        """
        return expected == actual
    
    def _get_mismatch_reason(
        self,
        expected: Command,
        actual: Command,
    ) -> str:
        """Get human-readable mismatch reason."""
        if expected.command_type != actual.command_type:
            return (
                f"Command type mismatch: expected {expected.command_type}, "
                f"got {actual.command_type}"
            )
        
        if expected.command_type == CommandType.SCHEDULE_ACTIVITY:
            return (
                f"Activity mismatch: expected '{expected.activity_name}', "
                f"got '{actual.activity_name}'"
            )
        
        if expected.command_type == CommandType.START_CHILD:
            return (
                f"Child workflow mismatch: expected '{expected.child_workflow_type}', "
                f"got '{actual.child_workflow_type}'"
            )
        
        if expected.command_type == CommandType.WAIT_SIGNAL:
            return (
                f"Signal mismatch: expected '{expected.signal_name}', "
                f"got '{actual.signal_name}'"
            )
        
        if expected.command_type == CommandType.START_TIMER:
            return (
                f"Timer mismatch: expected duration {expected.timer_duration_seconds}s, "
                f"got {actual.timer_duration_seconds}s"
            )
        
        return "Unknown command mismatch"
    
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
            "is_replay": self._is_replay,
            "historical_count": len(self._historical_commands),
            "historical_index": self._historical_index,
            "emitted_count": len(self._emitted_commands),
            "remaining_commands": len(self._historical_commands) - self._historical_index,
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
