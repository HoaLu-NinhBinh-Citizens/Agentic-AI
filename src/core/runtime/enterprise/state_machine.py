"""Formal state machine for workflows - Phase 5B v10.

Implements formal state machines:
- StateMachine: Generic state machine
- WorkflowStateMachine: Workflow lifecycle states
- ActivityStateMachine: Activity lifecycle states
- CompensationStateMachine: Compensation states
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar


T = TypeVar('T', bound=Enum)


class StateMachineError(Exception):
    """Error in state machine operation."""
    pass


class InvalidTransitionError(StateMachineError):
    """Raised when transition is not allowed."""
    pass


@dataclass
class StateTransition:
    """A valid state transition."""
    from_state: Any
    to_state: Any
    event: str
    guard: Optional[Callable] = None
    action: Optional[Callable] = None


@dataclass
class StateMachineState:
    """State in a state machine."""
    value: Any
    entry_action: Optional[Callable] = None
    exit_action: Optional[Callable] = None
    metadata: dict = field(default_factory=dict)


class StateMachine:
    """Generic state machine implementation.
    
    Supports:
    - Defined state transitions
    - Entry/exit actions
    - Guard conditions
    - Transition actions
    """
    
    def __init__(
        self,
        states: list[Any],
        initial_state: Any,
        transitions: list[StateTransition],
        on_invalid_transition: str = "raise",
    ):
        self._states = set(states)
        self._initial = initial_state
        self._transitions = {
            (t.from_state, t.event): t for t in transitions
        }
        self._on_invalid = on_invalid_transition
        
        self._current_state = initial_state
        self._history: list[Any] = [initial_state]
    
    @property
    def current_state(self) -> Any:
        """Get current state."""
        return self._current_state
    
    @property
    def history(self) -> list[Any]:
        """Get state history."""
        return self._history.copy()
    
    def can_transition(self, event: str) -> bool:
        """Check if transition is possible.
        
        Args:
            event: Event to trigger transition
            
        Returns:
            True if transition is valid
        """
        transition = self._transitions.get((self._current_state, event))
        
        if not transition:
            return False
        
        if transition.guard and not transition.guard():
            return False
        
        return True
    
    def get_available_transitions(self) -> list[str]:
        """Get available events for current state."""
        return [
            t.event for t in self._transitions.values()
            if t.from_state == self._current_state
            and (not t.guard or t.guard())
        ]
    
    def transition(self, event: str, **kwargs) -> bool:
        """Execute a state transition.
        
        Args:
            event: Event to trigger
            **kwargs: Arguments for actions
            
        Returns:
            True if transition succeeded
            
        Raises:
            InvalidTransitionError: If transition not allowed
        """
        transition = self._transitions.get((self._current_state, event))
        
        if not transition:
            if self._on_invalid == "raise":
                raise InvalidTransitionError(
                    f"No transition from {self._current_state} on event {event}"
                )
            return False
        
        if transition.guard and not transition.guard():
            if self._on_invalid == "raise":
                raise InvalidTransitionError(
                    f"Guard condition failed for transition "
                    f"{self._current_state} -> on {event}"
                )
            return False
        
        old_state = self._current_state
        
        if transition.action:
            transition.action(**kwargs)
        
        self._current_state = transition.to_state
        self._history.append(self._current_state)
        
        return True
    
    def reset(self) -> None:
        """Reset to initial state."""
        self._current_state = self._initial
        self._history = [self._initial]


class WorkflowState(Enum):
    """Workflow lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"


WORKFLOW_TRANSITIONS = [
    StateTransition(WorkflowState.CREATED, WorkflowState.RUNNING, "start"),
    StateTransition(WorkflowState.RUNNING, WorkflowState.PAUSED, "pause"),
    StateTransition(WorkflowState.RUNNING, WorkflowState.COMPLETED, "complete"),
    StateTransition(WorkflowState.RUNNING, WorkflowState.FAILED, "fail"),
    StateTransition(WorkflowState.RUNNING, WorkflowState.CANCELLED, "cancel"),
    StateTransition(WorkflowState.PAUSED, WorkflowState.RUNNING, "resume"),
    StateTransition(WorkflowState.PAUSED, WorkflowState.CANCELLED, "cancel"),
    StateTransition(WorkflowState.FAILED, WorkflowState.RUNNING, "retry"),
    StateTransition(WorkflowState.CANCELLED, WorkflowState.RUNNING, "retry"),
    StateTransition(WorkflowState.TERMINATED, WorkflowState.TERMINATED, "terminate"),
]


class WorkflowStateMachine(StateMachine):
    """State machine for workflow lifecycle.
    
    States:
    - CREATED: Initial state
    - RUNNING: Workflow is executing
    - PAUSED: Workflow is paused
    - COMPLETED: Workflow completed successfully
    - FAILED: Workflow failed
    - CANCELLED: Workflow was cancelled
    - TERMINATED: Workflow was forcefully terminated
    """
    
    def __init__(
        self,
        initial_state: WorkflowState = WorkflowState.CREATED,
        on_invalid_transition: str = "raise",
    ):
        super().__init__(
            states=[s for s in WorkflowState],
            initial_state=initial_state,
            transitions=WORKFLOW_TRANSITIONS,
            on_invalid_transition=on_invalid_transition,
        )
    
    def start(self) -> bool:
        """Start the workflow."""
        return self.transition("start")
    
    def pause(self) -> bool:
        """Pause the workflow."""
        return self.transition("pause")
    
    def resume(self) -> bool:
        """Resume a paused workflow."""
        return self.transition("resume")
    
    def complete(self) -> bool:
        """Mark workflow as completed."""
        return self.transition("complete")
    
    def fail(self) -> bool:
        """Mark workflow as failed."""
        return self.transition("fail")
    
    def cancel(self) -> bool:
        """Cancel the workflow."""
        return self.transition("cancel")
    
    def retry(self) -> bool:
        """Retry a failed or cancelled workflow."""
        return self.transition("retry")
    
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._current_state in {
            WorkflowState.COMPLETED,
            WorkflowState.TERMINATED,
        }
    
    def is_active(self) -> bool:
        """Check if workflow is currently active."""
        return self._current_state == WorkflowState.RUNNING


class ActivityState(Enum):
    """Activity lifecycle states."""
    SCHEDULED = "scheduled"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


ACTIVITY_TRANSITIONS = [
    StateTransition(ActivityState.SCHEDULED, ActivityState.STARTED, "start"),
    StateTransition(ActivityState.STARTED, ActivityState.COMPLETED, "complete"),
    StateTransition(ActivityState.STARTED, ActivityState.FAILED, "fail"),
    StateTransition(ActivityState.STARTED, ActivityState.TIMED_OUT, "timeout"),
    StateTransition(ActivityState.STARTED, ActivityState.CANCELLED, "cancel"),
    StateTransition(ActivityState.SCHEDULED, ActivityState.CANCELLED, "cancel"),
]


class ActivityStateMachine(StateMachine):
    """State machine for activity lifecycle.
    
    States:
    - SCHEDULED: Activity is scheduled
    - STARTED: Activity is running
    - COMPLETED: Activity completed successfully
    - FAILED: Activity failed
    - CANCELLED: Activity was cancelled
    - TIMED_OUT: Activity timed out
    """
    
    def __init__(
        self,
        initial_state: ActivityState = ActivityState.SCHEDULED,
        on_invalid_transition: str = "raise",
    ):
        super().__init__(
            states=[s for s in ActivityState],
            initial_state=initial_state,
            transitions=ACTIVITY_TRANSITIONS,
            on_invalid_transition=on_invalid_transition,
        )
    
    def start(self) -> bool:
        """Start the activity."""
        return self.transition("start")
    
    def complete(self) -> bool:
        """Mark activity as completed."""
        return self.transition("complete")
    
    def fail(self) -> bool:
        """Mark activity as failed."""
        return self.transition("fail")
    
    def timeout(self) -> bool:
        """Mark activity as timed out."""
        return self.transition("timeout")
    
    def cancel(self) -> bool:
        """Cancel the activity."""
        return self.transition("cancel")
    
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._current_state in {
            ActivityState.COMPLETED,
            ActivityState.FAILED,
            ActivityState.CANCELLED,
            ActivityState.TIMED_OUT,
        }
    
    def is_successful(self) -> bool:
        """Check if activity completed successfully."""
        return self._current_state == ActivityState.COMPLETED


class CompensationState(Enum):
    """Compensation lifecycle states."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


COMPENSATION_TRANSITIONS = [
    StateTransition(CompensationState.PENDING, CompensationState.SCHEDULED, "schedule"),
    StateTransition(CompensationState.SCHEDULED, CompensationState.RUNNING, "run"),
    StateTransition(CompensationState.RUNNING, CompensationState.COMPLETED, "complete"),
    StateTransition(CompensationState.RUNNING, CompensationState.FAILED, "fail"),
    StateTransition(CompensationState.PENDING, CompensationState.SKIPPED, "skip"),
    StateTransition(CompensationState.SCHEDULED, CompensationState.SKIPPED, "skip"),
]


class CompensationStateMachine(StateMachine):
    """State machine for compensation lifecycle.
    
    States:
    - PENDING: Compensation is pending
    - SCHEDULED: Compensation is scheduled
    - RUNNING: Compensation is executing
    - COMPLETED: Compensation completed
    - FAILED: Compensation failed
    - SKIPPED: Compensation was skipped
    """
    
    def __init__(
        self,
        initial_state: CompensationState = CompensationState.PENDING,
        on_invalid_transition: str = "raise",
    ):
        super().__init__(
            states=[s for s in CompensationState],
            initial_state=initial_state,
            transitions=COMPENSATION_TRANSITIONS,
            on_invalid_transition=on_invalid_transition,
        )
    
    def schedule(self) -> bool:
        """Schedule the compensation."""
        return self.transition("schedule")
    
    def run(self) -> bool:
        """Run the compensation."""
        return self.transition("run")
    
    def complete(self) -> bool:
        """Mark compensation as completed."""
        return self.transition("complete")
    
    def fail(self) -> bool:
        """Mark compensation as failed."""
        return self.transition("fail")
    
    def skip(self) -> bool:
        """Skip the compensation."""
        return self.transition("skip")
    
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._current_state in {
            CompensationState.COMPLETED,
            CompensationState.FAILED,
            CompensationState.SKIPPED,
        }
