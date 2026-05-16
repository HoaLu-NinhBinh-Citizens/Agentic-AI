"""Tool call state machine and record models for Phase 2B.

Defines the state machine for tool execution and the record dataclass
that tracks each tool call throughout its lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ToolCallState(Enum):
    """State machine for tool execution lifecycle.

    States:
        PENDING: Tool call has been received but not yet started.
        RUNNING: Tool is currently executing.
        COMPLETED: Tool executed successfully.
        FAILED: Tool execution failed with an error.
        TIMED_OUT: Tool exceeded its timeout limit.
        CANCELLED: Tool was cancelled (e.g., session deleted).
        ORPHANED: Execution whose lifecycle could not be fully observed
                  due to shutdown or ownership loss. Used as debugging aid
                  to detect resource leaks.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


ALLOWED_TRANSITIONS: dict[ToolCallState, set[ToolCallState]] = {
    ToolCallState.PENDING: {
        ToolCallState.RUNNING,
        ToolCallState.CANCELLED,
        ToolCallState.ORPHANED,
    },
    ToolCallState.RUNNING: {
        ToolCallState.COMPLETED,
        ToolCallState.FAILED,
        ToolCallState.TIMED_OUT,
        ToolCallState.CANCELLED,
    },
    ToolCallState.COMPLETED: set(),
    ToolCallState.FAILED: set(),
    ToolCallState.TIMED_OUT: set(),
    ToolCallState.CANCELLED: set(),
    ToolCallState.ORPHANED: set(),
}


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self,
        current_state: ToolCallState,
        target_state: ToolCallState,
        call_id: str | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.call_id = call_id
        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "none"
        msg = (
            f"Invalid state transition: {current_state.value} -> {target_state.value}. "
            f"Allowed transitions from {current_state.value}: {allowed_str}"
        )
        if call_id:
            msg = f"[{call_id}] {msg}"
        super().__init__(msg)


def validate_transition(
    current: ToolCallState,
    target: ToolCallState,
    call_id: str | None = None,
) -> None:
    """Validate a state transition is allowed.

    Args:
        current: Current state.
        target: Target state.
        call_id: Optional call ID for error messages.

    Raises:
        InvalidStateTransitionError: If transition is not allowed.
    """
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(current, target, call_id)


@dataclass
class ToolCallRecord:
    """Record tracking a single tool call execution.

    Attributes:
        call_id: Unique identifier for this tool call.
        session_id: ID of the session that initiated this call.
        client_id: WebSocket client ID that initiated the call (Phase 2C).
        tool_name: Name of the tool being called (may be namespaced).
        arguments: Tool input arguments as a dictionary.
        state: Current state in the execution lifecycle.
        created_at: When the call was received.
        started_at: When execution actually began (None if pending).
        completed_at: When execution finished (None if not finished).
        duration_ms: Execution duration in milliseconds.
        result_content: Result content from the tool.
        error_code: Error code if execution failed.
        error_message: Human-readable error message.
        trace_id: Unique trace identifier for observability.
        parent_call_id: Optional parent call ID for nested executions.
    """

    call_id: str
    session_id: str
    tool_name: str
    arguments: dict[str, Any]
    state: ToolCallState
    client_id: str = ""
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    result_content: list[Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    parent_call_id: str | None = None

    def __post_init__(self) -> None:
        import uuid

        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.trace_id is None:
            self.trace_id = str(uuid.uuid4())

    def transition_to(
        self,
        new_state: ToolCallState,
        validate: bool = True,
    ) -> None:
        """Transition to a new state with optional validation.

        Args:
            new_state: Target state.
            validate: Whether to validate the transition.

        Raises:
            InvalidStateTransitionError: If validation fails and validate=True.
        """
        if validate:
            validate_transition(self.state, new_state, self.call_id)

        self.state = new_state

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for serialization."""
        return {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "client_id": self.client_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "state": self.state.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "result_content": self.result_content,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "trace_id": self.trace_id,
            "parent_call_id": self.parent_call_id,
        }
