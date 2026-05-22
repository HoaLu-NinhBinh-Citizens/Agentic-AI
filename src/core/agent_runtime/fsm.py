"""Deterministic FSM - replayable execution, action log, idempotency.

Provides a deterministic finite state machine for agent execution:
- Replayable execution from action log
- Idempotent operations
- State transition validation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FSMState(str, Enum):
    """FSM states."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class FSMAction(str, Enum):
    """FSM actions."""

    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    COMPLETE = "complete"
    FAIL = "fail"
    RESET = "reset"


@dataclass
class FSMTransition:
    """State transition record."""

    from_state: FSMState
    to_state: FSMState
    action: FSMAction
    timestamp: int
    data: dict[str, Any] = field(default_factory=dict)
    transition_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "action": self.action.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "transition_id": self.transition_id,
        }


@dataclass
class ActionLogEntry:
    """Entry in the action log for replay."""

    action_id: str
    action_type: str
    args: dict[str, Any]
    result: Any
    timestamp: int
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "args": self.args,
            "result": self.result,
            "timestamp": self.timestamp,
            "checksum": self.checksum,
        }

    def compute_checksum(self) -> str:
        """Compute checksum of this entry."""
        content = json.dumps(
            {"action_id": self.action_id, "action_type": self.action_type, "args": self.args},
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class DeterministicFSM:
    """Deterministic Finite State Machine for agent execution.

    Features:
    - Replayable execution from action log
    - Idempotent operations
    - State transition validation
    - Action logging for debugging and replay
    """

    def __init__(self, initial_state: FSMState = FSMState.IDLE) -> None:
        """Initialize FSM.

        Args:
            initial_state: Starting state.
        """
        self._state = initial_state
        self._transitions: list[FSMTransition] = []
        self._action_log: list[ActionLogEntry] = []
        self._lock = asyncio.Lock()

    @property
    def state(self) -> FSMState:
        """Get current state."""
        return self._state

    @property
    def action_log(self) -> list[ActionLogEntry]:
        """Get action log."""
        return self._action_log.copy()

    def get_valid_actions(self) -> list[FSMAction]:
        """Get valid actions for current state.

        Returns:
            List of valid actions.
        """
        transitions = self._get_transitions()
        return [t.action for t in transitions if t.to_state == self._state]

    def _get_transitions(self) -> list[FSMTransition]:
        """Get all defined transitions."""
        return [
            FSMTransition(FSMState.IDLE, FSMState.RUNNING, FSMAction.START, 0),
            FSMTransition(FSMState.RUNNING, FSMState.PAUSED, FSMAction.PAUSE, 0),
            FSMTransition(FSMState.RUNNING, FSMState.COMPLETED, FSMAction.COMPLETE, 0),
            FSMTransition(FSMState.RUNNING, FSMState.FAILED, FSMAction.FAIL, 0),
            FSMTransition(FSMState.PAUSED, FSMState.RUNNING, FSMAction.RESUME, 0),
            FSMTransition(FSMState.PAUSED, FSMState.IDLE, FSMAction.RESET, 0),
            FSMTransition(FSMState.FAILED, FSMState.IDLE, FSMAction.RESET, 0),
        ]

    def can_transition(self, action: FSMAction) -> bool:
        """Check if action is valid from current state.

        Args:
            action: Action to check.

        Returns:
            True if transition is valid.
        """
        for transition in self._get_transitions():
            if transition.from_state == self._state and transition.action == action:
                return True
        return False

    async def execute_action(
        self,
        action: FSMAction,
        data: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Execute an action if valid.

        Args:
            action: Action to execute.
            data: Optional action data.

        Returns:
            Tuple of (success, message).
        """
        async with self._lock:
            if not self.can_transition(action):
                return False, f"Invalid action '{action.value}' from state '{self._state.value}'"

            transitions = [t for t in self._get_transitions() if t.from_state == self._state and t.action == action]

            if not transitions:
                return False, f"No transition found for {action.value}"

            transition = transitions[0]
            old_state = self._state
            self._state = transition.to_state

            transition.timestamp = int(time.time())
            transition.data = data or {}
            transition.transition_id = f"{old_state.value}_{action.value}_{transition.timestamp}"
            self._transitions.append(transition)

            logger.info(
                "FSM transition: from=%s action=%s to=%s",
                old_state.value,
                action.value,
                self._state.value,
            )

            return True, f"Transitioned to {self._state.value}"

    async def log_action(
        self,
        action_type: str,
        args: dict[str, Any],
        result: Any,
    ) -> ActionLogEntry:
        """Log an action for replay.

        Args:
            action_type: Type of action.
            args: Action arguments.
            result: Action result.

        Returns:
            Created log entry.
        """
        entry = ActionLogEntry(
            action_id=f"{action_type}_{len(self._action_log)}",
            action_type=action_type,
            args=args,
            result=result,
            timestamp=int(time.time()),
        )
        entry.checksum = entry.compute_checksum()
        self._action_log.append(entry)

        logger.debug(
            "Action logged: id=%s type=%s checksum=%s",
            entry.action_id,
            entry.action_type,
            entry.checksum,
        )

        return entry

    async def replay(
        self,
        from_index: int = 0,
        validate_checksums: bool = True,
    ) -> tuple[bool, str, list[ActionLogEntry]]:
        """Replay actions from log.

        Args:
            from_index: Starting index.
            validate_checksums: Whether to validate checksums.

        Returns:
            Tuple of (success, message, replayed_entries).
        """
        if from_index >= len(self._action_log):
            return False, "Invalid replay index", []

        replayed = []
        for i in range(from_index, len(self._action_log)):
            entry = self._action_log[i]

            if validate_checksums:
                expected = entry.compute_checksum()
                if expected != entry.checksum:
                    return False, f"Checksum mismatch at index {i}", replayed

            replayed.append(entry)

        logger.info("Replay completed: entries=%d from=%d", len(replayed), from_index)
        return True, f"Replayed {len(replayed)} actions", replayed

    def get_state_history(self) -> list[FSMTransition]:
        """Get state transition history.

        Returns:
            List of transitions.
        """
        return self._transitions.copy()

    def verify_idempotency(self) -> tuple[bool, list[str]]:
        """Verify action log is idempotent.

        Returns:
            Tuple of (is_idempotent, list of issues).
        """
        seen: dict[str, int] = {}
        issues = []

        for entry in self._action_log:
            key = f"{entry.action_type}:{json.dumps(entry.args, sort_keys=True)}"

            if key in seen:
                issues.append(f"Duplicate action at indices {seen[key]} and {len(self._action_log) - 1}")
            else:
                seen[key] = len(self._action_log) - 1

        return len(issues) == 0, issues

    def get_stats(self) -> dict[str, Any]:
        """Get FSM statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "state": self._state.value,
            "transitions": len(self._transitions),
            "logged_actions": len(self._action_log),
            "can_start": self.can_transition(FSMAction.START),
            "can_pause": self.can_transition(FSMAction.PAUSE),
            "can_resume": self.can_transition(FSMAction.RESUME),
        }

    def reset(self) -> None:
        """Reset FSM to initial state."""
        self._state = FSMState.IDLE
        self._transitions.clear()
