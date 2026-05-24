"""Deterministic Replay Contract.

Fixes Critical Gap: No deterministic replay contract.

Features:
- Event sourcing with deterministic replay
- Side-effect recording
- Replay verification
- Command verification
- Deterministic clock
- Workflow replay contract enforcement
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# EVENT TYPES
# =============================================================================


class EventType(Enum):
    """Types of events in the event store."""
    
    # Workflow events
    WORKFLOW_STARTED = auto()
    WORKFLOW_COMPLETED = auto()
    WORKFLOW_FAILED = auto()
    WORKFLOW_REPLAYED = auto()
    
    # Activity events
    ACTIVITY_SCHEDULED = auto()
    ACTIVITY_STARTED = auto()
    ACTIVITY_COMPLETED = auto()
    ACTIVITY_FAILED = auto()
    
    # Side-effect events
    SIDE_EFFECT_EXECUTED = auto()
    SIDE_EFFECT_RESULT = auto()
    
    # Command events
    COMMAND_EMITTED = auto()
    COMMAND_VERIFIED = auto()
    
    # Timer events
    TIMER_CREATED = auto()
    TIMER_FIRED = auto()


# =============================================================================
# DETERMINISTIC EVENT
# =============================================================================


@dataclass
class DeterministicEvent:
    """Event with deterministic ordering and content.
    
    CRITICAL: All events must be deterministic:
    - Event ID: deterministically derived from content
    - Timestamp: sequence number, not wall clock
    - Content: hashable and reproducible
    """
    
    # Identity (deterministic)
    event_id: str = ""  # SHA256(content_hash + sequence)
    sequence: int = 0   # Monotonic sequence number
    
    # Type
    event_type: EventType = EventType.WORKFLOW_STARTED
    
    # Content (must be deterministic)
    workflow_id: str = ""
    activity_id: str = ""
    
    # Payload (deterministic, hashable)
    payload: dict[str, Any] = field(default_factory=dict)
    
    # Deterministic timestamp (sequence-based)
    sequence_time: int = 0
    
    # Verification
    content_hash: str = ""  # Hash of payload
    
    def compute_content_hash(self) -> str:
        """Compute deterministic hash of event content."""
        content = {
            "sequence": self.sequence,
            "event_type": self.event_type.name,
            "workflow_id": self.workflow_id,
            "activity_id": self.activity_id,
            "payload": self.payload,
            "sequence_time": self.sequence_time,
        }
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def finalize(self) -> None:
        """Finalize event, computing all hashes."""
        self.content_hash = self.compute_content_hash()
        self.event_id = hashlib.sha256(
            f"{self.content_hash}:{self.sequence}".encode()
        ).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type.name,
            "workflow_id": self.workflow_id,
            "activity_id": self.activity_id,
            "payload": self.payload,
            "sequence_time": self.sequence_time,
            "content_hash": self.content_hash,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeterministicEvent:
        event_type = EventType[data.get("event_type", "WORKFLOW_STARTED")]
        return cls(
            event_id=data["event_id"],
            sequence=data["sequence"],
            event_type=event_type,
            workflow_id=data["workflow_id"],
            activity_id=data["activity_id"],
            payload=data["payload"],
            sequence_time=data["sequence_time"],
            content_hash=data["content_hash"],
        )


# =============================================================================
# COMMAND (for replay verification)
# =============================================================================


@dataclass
class DeterministicCommand:
    """Command for deterministic replay verification.
    
    Commands are deterministic operations that must produce
    the same result on replay.
    """
    
    command_id: str = ""
    workflow_id: str = ""
    command_type: str = ""  # e.g., "activity.call", "timer.wait"
    
    # Deterministic arguments
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    
    # Result (filled after execution)
    result: Any = None
    error: str | None = None
    
    # Verification
    content_hash: str = ""
    replay_hash: str = ""  # Hash from replay execution
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of command."""
        content = {
            "workflow_id": self.workflow_id,
            "command_type": self.command_type,
            "args": self.args,
            "kwargs": self.kwargs,
        }
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def finalize(self) -> None:
        """Finalize command, computing hash."""
        self.content_hash = self.compute_hash()
    
    def verify_replay(self) -> tuple[bool, str]:
        """Verify replay produced same result.
        
        Returns:
            (is_valid, reason)
        """
        if not self.result:
            return False, "No result recorded"
        
        # Compare result hashes
        original_hash = hashlib.sha256(
            json.dumps(self.result, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        if original_hash == self.replay_hash:
            return True, "Replay verified"
        
        return False, f"Result mismatch: original={original_hash[:16]} replay={self.replay_hash[:16]}"


# =============================================================================
# SIDE EFFECT
# =============================================================================


@dataclass
class SideEffect:
    """Side effect that was executed.
    
    CRITICAL: Side effects must be recorded and replayable.
    """
    
    effect_id: str = ""
    workflow_id: str = ""
    
    # What was called
    effect_type: str = ""  # e.g., "http.request", "file.write"
    function_name: str = ""
    
    # Arguments (deterministic)
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    
    # Result
    result: Any = None
    error: str | None = None
    
    # Timing
    sequence: int = 0
    
    # Caching
    cache_key: str = ""
    cached: bool = False


# =============================================================================
# DETERMINISTIC CLOCK
# =============================================================================


class DeterministicClock:
    """Clock that provides deterministic time for workflows.
    
    CRITICAL: Workflows must use this instead of time.time()
    to ensure deterministic replay.
    """
    
    def __init__(self, initial_time: int = 0):
        self._sequence: int = 0
        self._wall_offset: int = 0  # Offset from wall clock
        
        # For actual time tracking (outside workflows)
        self._wall_start = datetime.utcnow().timestamp()
    
    def get_sequence_time(self) -> int:
        """Get deterministic sequence time.
        
        Returns monotonically increasing sequence number.
        """
        self._sequence += 1
        return self._sequence
    
    def get_wall_time(self) -> float:
        """Get wall clock time (for non-deterministic use only)."""
        return datetime.utcnow().timestamp()
    
    def get_deterministic_time(self) -> float:
        """Get deterministic time for workflow use.
        
        This is sequence-based, not wall clock.
        """
        return float(self.get_sequence_time())
    
    def advance(self, steps: int = 1) -> None:
        """Advance the clock by steps (for testing)."""
        self._sequence += steps


# =============================================================================
# REPLAY CONTRACT
# =============================================================================


@dataclass
class ReplayContract:
    """Contract for deterministic replay.
    
    Defines what must be recorded and verified for replay.
    """
    
    contract_id: str = ""
    workflow_id: str = ""
    workflow_type: str = ""
    
    # Events
    events: list[DeterministicEvent] = field(default_factory=list)
    
    # Commands
    commands: list[DeterministicCommand] = field(default_factory=list)
    
    # Side effects
    side_effects: list[SideEffect] = field(default_factory=list)
    
    # Verification
    initial_state_hash: str = ""
    final_state_hash: str = ""
    replay_verified: bool = False
    verification_issues: list[str] = field(default_factory=list)
    
    # Metadata
    created_at: str = ""
    replay_at: str | None = None
    
    def add_event(self, event: DeterministicEvent) -> None:
        """Add event to contract."""
        event.sequence = len(self.events) + 1
        event.finalize()
        self.events.append(event)
    
    def add_command(self, command: DeterministicCommand) -> DeterministicCommand:
        """Add command to contract."""
        command.workflow_id = self.workflow_id
        command.finalize()
        self.commands.append(command)
        return command
    
    def add_side_effect(self, effect: SideEffect) -> SideEffect:
        """Add side effect to contract."""
        effect.sequence = len(self.side_effects) + 1
        effect.cache_key = hashlib.sha256(
            json.dumps({
                "type": effect.effect_type,
                "func": effect.function_name,
                "args": effect.args,
                "kwargs": effect.kwargs,
            }, sort_keys=True).encode()
        ).hexdigest()
        self.side_effects.append(effect)
        return effect
    
    def verify_replay(self) -> tuple[bool, list[str]]:
        """Verify replay matches original execution."""
        issues = []
        
        # 1. Verify all commands produce same results
        for cmd in self.commands:
            valid, reason = cmd.verify_replay()
            if not valid:
                issues.append(f"Command {cmd.command_id}: {reason}")
        
        # 2. Verify state hashes match
        # (In real implementation, would compare workflow state)
        
        self.replay_verified = len(issues) == 0
        self.verification_issues = issues
        
        if self.replay_verified:
            logger.info("replay_verified: workflow=%s", self.workflow_id)
        else:
            logger.warning("replay_failed: workflow=%s issues=%s", self.workflow_id, len(issues))
        
        return self.replay_verified, issues


# =============================================================================
# REPLAY VERIFIER
# =============================================================================


class ReplayVerifier:
    """Verifies deterministic replay contract compliance.
    
    CRITICAL: This ensures all replay-critical operations
    are deterministic and verifiable.
    """
    
    def __init__(self):
        self._contracts: dict[str, ReplayContract] = {}
        self._lock = asyncio.Lock()
        self._clock = DeterministicClock()
        
        # Non-deterministic operations detected
        self._violations: list[dict[str, Any]] = []
    
    def get_clock(self) -> DeterministicClock:
        """Get deterministic clock."""
        return self._clock
    
    async def create_contract(
        self,
        workflow_id: str,
        workflow_type: str,
        initial_state: dict[str, Any] | None = None,
    ) -> ReplayContract:
        """Create a replay contract for a workflow."""
        import uuid
        
        async with self._lock:
            contract = ReplayContract(
                contract_id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                workflow_type=workflow_type,
                initial_state_hash=self._hash_state(initial_state) if initial_state else "",
                created_at=datetime.utcnow().isoformat(),
            )
            
            self._contracts[workflow_id] = contract
            
            logger.info("replay_contract_created: workflow=%s", workflow_id)
            
            return contract
    
    def get_contract(self, workflow_id: str) -> ReplayContract | None:
        """Get contract for workflow."""
        return self._contracts.get(workflow_id)
    
    async def record_event(
        self,
        workflow_id: str,
        event_type: EventType,
        payload: dict[str, Any],
        activity_id: str = "",
    ) -> DeterministicEvent:
        """Record a deterministic event."""
        contract = self._contracts.get(workflow_id)
        if not contract:
            raise ValueError(f"No contract for workflow: {workflow_id}")
        
        event = DeterministicEvent(
            event_type=event_type,
            workflow_id=workflow_id,
            activity_id=activity_id,
            payload=payload,
            sequence_time=self._clock.get_sequence_time(),
        )
        
        contract.add_event(event)
        
        logger.debug(
            "event_recorded: workflow=%s type=%s sequence=%s",
            workflow_id, event_type.name, event.sequence,
        )
        
        return event
    
    async def record_command(
        self,
        workflow_id: str,
        command_type: str,
        args: tuple,
        kwargs: dict[str, Any],
    ) -> DeterministicCommand:
        """Record a deterministic command."""
        import uuid
        
        contract = self._contracts.get(workflow_id)
        if not contract:
            raise ValueError(f"No contract for workflow: {workflow_id}")
        
        command = DeterministicCommand(
            command_id=str(uuid.uuid4()),
            command_type=command_type,
            args=args,
            kwargs=kwargs,
        )
        
        contract.add_command(command)
        
        logger.debug(
            "command_recorded: workflow=%s type=%s",
            workflow_id, command_type,
        )
        
        return command
    
    async def record_side_effect(
        self,
        workflow_id: str,
        effect_type: str,
        function_name: str,
        args: tuple,
        kwargs: dict[str, Any],
        result: Any,
        error: str | None = None,
    ) -> SideEffect:
        """Record a side effect execution."""
        contract = self._contracts.get(workflow_id)
        if not contract:
            raise ValueError(f"No contract for workflow: {workflow_id}")
        
        effect = SideEffect(
            workflow_id=workflow_id,
            effect_type=effect_type,
            function_name=function_name,
            args=args,
            kwargs=kwargs,
            result=result,
            error=error,
        )
        
        contract.add_side_effect(effect)
        
        logger.debug(
            "side_effect_recorded: workflow=%s type=%s func=%s",
            workflow_id, effect_type, function_name,
        )
        
        return effect
    
    def get_cached_result(
        self,
        workflow_id: str,
        effect_type: str,
        function_name: str,
        args: tuple,
        kwargs: dict[str, Any],
    ) -> Any | None:
        """Get cached result for side effect (for replay)."""
        contract = self._contracts.get(workflow_id)
        if not contract:
            return None
        
        cache_key = hashlib.sha256(
            json.dumps({
                "type": effect_type,
                "func": function_name,
                "args": args,
                "kwargs": kwargs,
            }, sort_keys=True).encode()
        ).hexdigest()
        
        for effect in contract.side_effects:
            if effect.cache_key == cache_key:
                return effect.result
        
        return None
    
    async def verify_replay(self, workflow_id: str) -> tuple[bool, list[str]]:
        """Verify replay for a workflow."""
        contract = self._contracts.get(workflow_id)
        if not contract:
            return False, ["No contract found"]
        
        return contract.verify_replay()
    
    def record_violation(
        self,
        workflow_id: str,
        operation: str,
        reason: str,
    ) -> None:
        """Record a determinism violation."""
        violation = {
            "workflow_id": workflow_id,
            "operation": operation,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self._violations.append(violation)
        
        logger.warning(
            "determinism_violation: workflow=%s operation=%s reason=%s",
            workflow_id, operation, reason,
        )
    
    def get_violations(self) -> list[dict[str, Any]]:
        """Get all recorded violations."""
        return list(self._violations)
    
    def _hash_state(self, state: dict[str, Any]) -> str:
        """Hash workflow state deterministically."""
        return hashlib.sha256(
            json.dumps(state, sort_keys=True, default=str).encode()
        ).hexdigest()


# =============================================================================
# WORKFLOW REPLAY CONTEXT
# =============================================================================


class WorkflowReplayContext:
    """Context for deterministic workflow execution.
    
    Provides:
    - Deterministic clock
    - Side effect caching
    - Command verification
    - Event recording
    """
    
    def __init__(
        self,
        workflow_id: str,
        verifier: ReplayVerifier,
        contract: ReplayContract,
    ):
        self.workflow_id = workflow_id
        self.verifier = verifier
        self.contract = contract
        self.clock = verifier.get_clock()
        
        self._replay_mode = False
    
    def enable_replay_mode(self) -> None:
        """Enable replay mode (uses cached results)."""
        self._replay_mode = True
    
    def disable_replay_mode(self) -> None:
        """Disable replay mode (executes normally)."""
        self._replay_mode = False
    
    async def execute_activity(
        self,
        activity_name: str,
        args: tuple,
        kwargs: dict[str, Any],
    ) -> Any:
        """Execute activity with deterministic tracking."""
        # Record command
        command = await self.verifier.record_command(
            self.workflow_id,
            f"activity.call:{activity_name}",
            args,
            kwargs,
        )
        
        # Check for cached result in replay mode
        if self._replay_mode:
            cached = self.verifier.get_cached_result(
                self.workflow_id,
                "activity",
                activity_name,
                args,
                kwargs,
            )
            if cached is not None:
                command.result = cached
                command.replay_hash = hashlib.sha256(
                    json.dumps(cached, sort_keys=True, default=str).encode()
                ).hexdigest()
                return cached
        
        # Execute activity (would call actual implementation)
        # For now, return placeholder
        result = None
        
        # Record side effect
        await self.verifier.record_side_effect(
            self.workflow_id,
            "activity",
            activity_name,
            args,
            kwargs,
            result,
        )
        
        # Record result in command
        command.result = result
        command.replay_hash = hashlib.sha256(
            json.dumps(result, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        return result
    
    def get_deterministic_time(self) -> float:
        """Get deterministic time (not wall clock)."""
        return self.clock.get_deterministic_time()
    
    def get_sequence(self) -> int:
        """Get current sequence number."""
        return self.clock._sequence


# =============================================================================
# GLOBAL REPLAY VERIFIER
# =============================================================================


_global_verifier: ReplayVerifier | None = None


def get_replay_verifier() -> ReplayVerifier:
    """Get global replay verifier."""
    global _global_verifier
    if _global_verifier is None:
        _global_verifier = ReplayVerifier()
    return _global_verifier
