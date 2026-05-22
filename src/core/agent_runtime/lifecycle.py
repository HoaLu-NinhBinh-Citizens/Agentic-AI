"""Agent Lifecycle Management - spawn, suspend, resume, cancel, checkpoint.

Manages the complete lifecycle of agent instances including state transitions,
checkpointing, and event handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """Agent lifecycle states."""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    SUSPENDED = "suspended"
    CHECKPOINTED = "checkpointed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class LifecycleEvent(str, Enum):
    """Lifecycle events that trigger state transitions."""

    CREATE = "create"
    INIT = "init"
    START = "start"
    SUSPEND = "suspend"
    RESUME = "resume"
    CHECKPOINT = "checkpoint"
    RESTORE = "restore"
    CANCEL = "cancel"
    COMPLETE = "complete"
    FAIL = "fail"
    TIMEOUT = "timeout"


@dataclass
class AgentCheckpoint:
    """Checkpoint data for agent state persistence."""

    agent_id: str
    state: AgentState
    step: int
    context: dict[str, Any]
    created_at: int = field(default_factory=lambda: int(time.time()))
    checkpoint_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "step": self.step,
            "context": self.context,
            "created_at": self.created_at,
            "checkpoint_id": self.checkpoint_id,
        }


class AgentLifecycle:
    """Manages agent lifecycle state transitions.

    Provides methods for:
    - Creating and initializing agents
    - Suspending and resuming execution
    - Checkpointing and restoring state
    - Cancelling agents
    - Tracking state transitions
    """

    def __init__(self, agent_id: str) -> None:
        """Initialize lifecycle manager.

        Args:
            agent_id: Unique identifier for the agent.
        """
        self._agent_id = agent_id
        self._state = AgentState.CREATED
        self._step = 0
        self._context: dict[str, Any] = {}
        self._checkpoints: list[AgentCheckpoint] = []
        self._event_handlers: dict[LifecycleEvent, list[Callable]] = {}
        self._lock = asyncio.Lock()
        self._created_at = int(time.time())
        self._updated_at = int(time.time())

    @property
    def agent_id(self) -> str:
        """Get agent ID."""
        return self._agent_id

    @property
    def state(self) -> AgentState:
        """Get current state."""
        return self._state

    @property
    def step(self) -> int:
        """Get current step number."""
        return self._step

    @property
    def context(self) -> dict[str, Any]:
        """Get agent context."""
        return self._context.copy()

    async def emit(self, event: LifecycleEvent, data: dict[str, Any] | None = None) -> None:
        """Emit a lifecycle event.

        Args:
            event: Event type.
            data: Optional event data.
        """
        logger.debug(
            "Agent lifecycle event: agent=%s event=%s state=%s",
            self._agent_id,
            event.value,
            self._state.value,
        )

        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event, data or {})
                else:
                    handler(event, data or {})
            except Exception as e:
                logger.error(
                    "Error in lifecycle handler: agent=%s event=%s error=%s",
                    self._agent_id,
                    event.value,
                    str(e),
                )

    async def transition(
        self,
        target_state: AgentState,
        event: LifecycleEvent,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Transition to a new state.

        Args:
            target_state: Target state.
            event: Event that triggered transition.
            data: Optional transition data.

        Returns:
            True if transition succeeded, False otherwise.
        """
        async with self._lock:
            if not self._can_transition(target_state):
                logger.warning(
                    "Invalid state transition: agent=%s from=%s to=%s",
                    self._agent_id,
                    self._state.value,
                    target_state.value,
                )
                return False

            old_state = self._state
            self._state = target_state
            self._updated_at = int(time.time())

            logger.info(
                "Agent state transition: agent=%s from=%s to=%s",
                self._agent_id,
                old_state.value,
                target_state.value,
            )

            await self.emit(event, data or {})
            return True

    def _can_transition(self, target: AgentState) -> bool:
        """Check if transition is valid.

        Args:
            target: Target state.

        Returns:
            True if transition is allowed.
        """
        valid_transitions: dict[AgentState, set[AgentState]] = {
            AgentState.CREATED: {AgentState.INITIALIZING},
            AgentState.INITIALIZING: {AgentState.RUNNING, AgentState.FAILED},
            AgentState.RUNNING: {
                AgentState.SUSPENDED,
                AgentState.CHECKPOINTED,
                AgentState.CANCELLING,
                AgentState.COMPLETED,
                AgentState.FAILED,
            },
            AgentState.SUSPENDED: {AgentState.RUNNING, AgentState.CANCELLING},
            AgentState.CHECKPOINTED: {AgentState.RUNNING, AgentState.CANCELLED},
            AgentState.CANCELLING: {AgentState.CANCELLED, AgentState.FAILED},
            AgentState.CANCELLED: set(),
            AgentState.COMPLETED: set(),
            AgentState.FAILED: set(),
        }

        allowed = valid_transitions.get(self._state, set())
        return target in allowed

    async def spawn(
        self,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Spawn a new agent instance.

        Args:
            context: Initial agent context.

        Returns:
            True if spawned successfully.
        """
        if context:
            self._context.update(context)

        return await self.transition(
            AgentState.INITIALIZING,
            LifecycleEvent.CREATE,
            {"context": self._context.copy()},
        )

    async def start(self) -> bool:
        """Start agent execution.

        Returns:
            True if started successfully.
        """
        return await self.transition(
            AgentState.RUNNING,
            LifecycleEvent.START,
        )

    async def suspend(self) -> bool:
        """Suspend agent execution.

        Returns:
            True if suspended successfully.
        """
        return await self.transition(
            AgentState.SUSPENDED,
            LifecycleEvent.SUSPEND,
        )

    async def resume(self) -> bool:
        """Resume agent execution.

        Returns:
            True if resumed successfully.
        """
        return await self.transition(
            AgentState.RUNNING,
            LifecycleEvent.RESUME,
        )

    async def checkpoint(self) -> AgentCheckpoint:
        """Create a checkpoint of current state.

        Returns:
            AgentCheckpoint with current state.
        """
        checkpoint = AgentCheckpoint(
            agent_id=self._agent_id,
            state=self._state,
            step=self._step,
            context=self._context.copy(),
        )
        self._checkpoints.append(checkpoint)

        await self.transition(
            AgentState.CHECKPOINTED,
            LifecycleEvent.CHECKPOINT,
            {"checkpoint_id": checkpoint.checkpoint_id},
        )

        return checkpoint

    async def restore(self, checkpoint: AgentCheckpoint) -> bool:
        """Restore state from checkpoint.

        Args:
            checkpoint: Checkpoint to restore from.

        Returns:
            True if restored successfully.
        """
        if checkpoint.agent_id != self._agent_id:
            logger.error("Checkpoint agent_id mismatch: %s != %s", checkpoint.agent_id, self._agent_id)
            return False

        self._state = checkpoint.state
        self._step = checkpoint.step
        self._context = checkpoint.context.copy()
        self._updated_at = int(time.time())

        return await self.transition(
            AgentState.RUNNING,
            LifecycleEvent.RESTORE,
            {"checkpoint_id": checkpoint.checkpoint_id},
        )

    async def cancel(self) -> bool:
        """Cancel agent execution.

        Returns:
            True if cancellation initiated successfully.
        """
        return await self.transition(
            AgentState.CANCELLING,
            LifecycleEvent.CANCEL,
        )

    async def complete(self) -> bool:
        """Mark agent as completed.

        Returns:
            True if marked successfully.
        """
        return await self.transition(
            AgentState.COMPLETED,
            LifecycleEvent.COMPLETE,
        )

    async def fail(self, error: str) -> bool:
        """Mark agent as failed.

        Args:
            error: Error message.

        Returns:
            True if marked successfully.
        """
        self._context["error"] = error
        return await self.transition(
            AgentState.FAILED,
            LifecycleEvent.FAIL,
            {"error": error},
        )

    def increment_step(self) -> None:
        """Increment the current step number."""
        self._step += 1

    def update_context(self, key: str, value: Any) -> None:
        """Update a context value.

        Args:
            key: Context key.
            value: New value.
        """
        self._context[key] = value

    def on_event(self, event: LifecycleEvent, handler: Callable) -> None:
        """Register an event handler.

        Args:
            event: Event type to listen for.
            handler: Handler function.
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def get_stats(self) -> dict[str, Any]:
        """Get lifecycle statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "agent_id": self._agent_id,
            "state": self._state.value,
            "step": self._step,
            "checkpoints": len(self._checkpoints),
            "created_at": self._created_at,
            "updated_at": self._updated_at,
        }
