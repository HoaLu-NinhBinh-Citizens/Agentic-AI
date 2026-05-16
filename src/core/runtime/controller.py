"""
Runtime Controller - State Machine Lifecycle Management

Integrates state machine with runtime lifecycle:
- States: BOOT, INIT, READY, PLANNING, EXECUTING, VALIDATING, DONE, FAILED, RECOVERING
- Lifecycle events: on_enter, on_exit, on_transition
- Hook system for lifecycle integration
- Async state transitions with timeout support
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class RuntimeState(Enum):
    """Runtime states for the state machine."""
    BOOT = "boot"
    INIT = "init"
    READY = "ready"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    RECOVERING = "recovering"
    DONE = "done"
    FAILED = "failed"
    SHUTDOWN = "shutdown"


class LifecycleEvent(Enum):
    """Lifecycle events emitted during state transitions."""
    BOOT_STARTED = "boot_started"
    BOOT_COMPLETED = "boot_completed"
    INIT_STARTED = "init_started"
    INIT_COMPLETED = "init_completed"
    READY_ENTERED = "ready_entered"
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    RECOVERY_FAILED = "recovery_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SHUTDOWN = "shutdown"
    SHUTDOWN_COMPLETED = "shutdown_completed"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class StateTransition:
    """Represents a state transition."""
    from_state: RuntimeState
    to_state: RuntimeState
    timestamp: datetime
    duration_ms: int
    triggered_by: str
    reason: Optional[str] = None
    success: bool = True


@dataclass
class LifecycleHook:
    """Hook callback for lifecycle events."""
    event: LifecycleEvent
    callback: Callable[["RuntimeController", Optional[Any]], None]
    priority: int = 0


class RuntimeController:
    """
    Runtime Controller - manages runtime state machine lifecycle.

    Integrates with:
    - Event bus for lifecycle events
    - Health monitor for health checks
    - Self-healer for recovery
    - Metrics collector for telemetry

    States:
        BOOT → INIT → READY → PLANNING → EXECUTING → VALIDATING → DONE
                    ↓           ↓            ↓            ↓
                READY       RECOVERING    RECOVERING    FAILED
    """

    def __init__(
        self,
        name: str = "ai_support",
        init_timeout: float = 30.0,
        health_check_interval: float = 60.0,
    ):
        self.id = str(uuid4())[:8]
        self.name = name

        # State
        self._state: RuntimeState = RuntimeState.BOOT
        self._previous_state: Optional[RuntimeState] = None
        self._state_start: datetime = datetime.now()

        # Transitions
        self._transitions: List[StateTransition] = []

        # Hooks
        self._hooks: List[LifecycleHook] = []
        self._hook_lock = asyncio.Lock()

        # Configuration
        self._init_timeout = init_timeout
        self._health_check_interval = health_check_interval
        self._running = False

        # Subsystems (optional, set via set_subsystem)
        self._subsystems: Dict[str, Any] = {}

        # Statistics
        self._stats = {
            "state_changes": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "recoveries": 0,
            "errors": 0,
        }

    # -------------------------------------------------------------------------
    # State Properties
    # -------------------------------------------------------------------------

    @property
    def state(self) -> RuntimeState:
        """Get current state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if controller is running."""
        return self._running

    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return (datetime.now() - self._state_start).total_seconds()

    def get_state_duration(self) -> float:
        """Get duration in current state (seconds)."""
        return (datetime.now() - self._state_start).total_seconds()

    # -------------------------------------------------------------------------
    # Subsystem Management
    # -------------------------------------------------------------------------

    def set_subsystem(self, name: str, subsystem: Any) -> None:
        """Register a subsystem (event_bus, health_monitor, etc.)."""
        self._subsystems[name] = subsystem
        logger.debug("Registered subsystem: %s", name)

    def get_subsystem(self, name: str) -> Optional[Any]:
        """Get a registered subsystem."""
        return self._subsystems.get(name)

    # -------------------------------------------------------------------------
    # Lifecycle Hooks
    # -------------------------------------------------------------------------

    def on_lifecycle(
        self,
        event: LifecycleEvent,
        callback: Callable[["RuntimeController", Optional[Any]], None],
        priority: int = 0,
    ) -> None:
        """Register a lifecycle hook."""
        hook = LifecycleHook(event=event, callback=callback, priority=priority)
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority, reverse=True)
        logger.debug("Registered hook for: %s", event.value)

    async def emit_event(self, event: LifecycleEvent, data: Optional[Any] = None) -> None:
        """Emit a lifecycle event to all registered hooks."""
        async with self._hook_lock:
            for hook in self._hooks:
                if hook.event == event:
                    try:
                        hook.callback(self, data)
                    except Exception as exc:
                        logger.error("Hook error for %s: %s", event.value, exc)

        # Also emit to event bus if available
        event_bus = self._subsystems.get("event_bus")
        if event_bus:
            try:
                await event_bus.emit({
                    "type": event.value,
                    "source": f"runtime_controller.{self.name}",
                    "state": self._state.value,
                    "data": data,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as exc:
                logger.warning("Failed to emit to event bus: %s", exc)

    # -------------------------------------------------------------------------
    # State Transitions
    # -------------------------------------------------------------------------

    async def transition_to(self, new_state: RuntimeState, reason: Optional[str] = None) -> bool:
        """
        Transition to a new state.

        Args:
            new_state: Target state
            reason: Reason for transition

        Returns:
            True if transition succeeded
        """
        if self._state == new_state:
            logger.debug("Already in state: %s", new_state.value)
            return True

        old_state = self._state

        # Validate transition
        if not self._is_valid_transition(old_state, new_state):
            logger.warning(
                "Invalid transition: %s → %s",
                old_state.value,
                new_state.value,
            )
            return False

        # Record transition
        duration_ms = int(self.get_state_duration() * 1000)
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            triggered_by="user" if reason else "auto",
            reason=reason,
        )
        self._transitions.append(transition)

        # Update state
        self._previous_state = old_state
        self._state = new_state
        self._state_start = datetime.now()
        self._stats["state_changes"] += 1

        logger.info(
            "State transition: %s → %s (%s, %dms)",
            old_state.value,
            new_state.value,
            reason or "auto",
            duration_ms,
        )

        # Emit lifecycle events
        await self._emit_transition_events(old_state, new_state)

        return True

    async def _emit_transition_events(self, old: RuntimeState, new: RuntimeState) -> None:
        """Emit lifecycle events for state transition."""
        event_map = {
            RuntimeState.INIT: LifecycleEvent.INIT_COMPLETED if old == RuntimeState.BOOT else None,
            RuntimeState.READY: LifecycleEvent.READY_ENTERED,
            RuntimeState.PLANNING: LifecycleEvent.PLANNING_STARTED,
            RuntimeState.EXECUTING: LifecycleEvent.EXECUTION_STARTED,
            RuntimeState.VALIDATING: LifecycleEvent.VALIDATION_STARTED,
            RuntimeState.RECOVERING: LifecycleEvent.RECOVERY_STARTED,
            RuntimeState.DONE: LifecycleEvent.TASK_COMPLETED,
            RuntimeState.FAILED: LifecycleEvent.TASK_FAILED,
        }

        if event_map.get(new):
            await self.emit_event(event_map[new], {"from_state": old.value, "reason": None})

    def _is_valid_transition(self, from_state: RuntimeState, to_state: RuntimeState) -> bool:
        """Check if state transition is valid."""
        valid_transitions = {
            RuntimeState.BOOT: [RuntimeState.INIT, RuntimeState.FAILED],
            RuntimeState.INIT: [RuntimeState.READY, RuntimeState.FAILED],
            RuntimeState.READY: [RuntimeState.PLANNING, RuntimeState.SHUTDOWN, RuntimeState.FAILED],
            RuntimeState.PLANNING: [RuntimeState.EXECUTING, RuntimeState.READY, RuntimeState.FAILED],
            RuntimeState.EXECUTING: [RuntimeState.VALIDATING, RuntimeState.RECOVERING, RuntimeState.FAILED],
            RuntimeState.VALIDATING: [RuntimeState.DONE, RuntimeState.RECOVERING, RuntimeState.FAILED],
            RuntimeState.RECOVERING: [RuntimeState.READY, RuntimeState.FAILED],
            RuntimeState.DONE: [RuntimeState.READY, RuntimeState.SHUTDOWN],
            RuntimeState.FAILED: [RuntimeState.INIT, RuntimeState.RECOVERING],
            RuntimeState.SHUTDOWN: [],
        }

        return to_state in valid_transitions.get(from_state, [])

    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------

    async def boot(self) -> bool:
        """Boot the runtime (BOOT → INIT)."""
        logger.info("Runtime controller booting...")
        await self.emit_event(LifecycleEvent.BOOT_STARTED)

        self._state = RuntimeState.BOOT
        self._running = True

        await self.emit_event(LifecycleEvent.BOOT_COMPLETED)
        return await self.transition_to(RuntimeState.INIT, "boot")

    async def initialize(self, subsystems: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize subsystems (INIT → READY)."""
        if self._state not in [RuntimeState.BOOT, RuntimeState.INIT, RuntimeState.FAILED]:
            logger.warning("Cannot initialize from state: %s", self._state.value)
            return False

        if self._state == RuntimeState.BOOT:
            await self.transition_to(RuntimeState.INIT, "init_start")

        await self.emit_event(LifecycleEvent.INIT_STARTED)

        try:
            # Initialize subsystems
            if subsystems:
                for name, subsystem in subsystems.items():
                    self._subsystems[name] = subsystem

            # Initialize registered subsystems
            for name, subsystem in self._subsystems.items():
                if hasattr(subsystem, "initialize"):
                    try:
                        if asyncio.iscoroutinefunction(subsystem.initialize):
                            await asyncio.wait_for(
                                subsystem.initialize(),
                                timeout=self._init_timeout,
                            )
                        else:
                            subsystem.initialize()
                        logger.debug("Initialized subsystem: %s", name)
                    except asyncio.TimeoutError:
                        logger.error("Subsystem %s init timeout", name)
                        return False
                    except Exception as exc:
                        logger.error("Subsystem %s init failed: %s", name, exc)
                        return False

            await self.emit_event(LifecycleEvent.INIT_COMPLETED)
            return await self.transition_to(RuntimeState.READY, "init_complete")

        except Exception as exc:
            logger.exception("Initialization failed")
            await self.emit_event(LifecycleEvent.ERROR_OCCURRED, {"error": str(exc)})
            self._stats["errors"] += 1
            return False

    async def start_planning(self) -> bool:
        """Start planning phase (READY → PLANNING)."""
        if self._state != RuntimeState.READY:
            logger.warning("Cannot start planning from state: %s", self._state.value)
            return False

        return await self.transition_to(RuntimeState.PLANNING, "start_planning")

    async def start_execution(self) -> bool:
        """Start execution phase (PLANNING → EXECUTING)."""
        if self._state != RuntimeState.PLANNING:
            logger.warning("Cannot start execution from state: %s", self._state.value)
            return False

        await self.emit_event(LifecycleEvent.PLANNING_COMPLETED)
        return await self.transition_to(RuntimeState.EXECUTING, "start_execution")

    async def start_validation(self) -> bool:
        """Start validation phase (EXECUTING → VALIDATING)."""
        if self._state != RuntimeState.EXECUTING:
            logger.warning("Cannot start validation from state: %s", self._state.value)
            return False

        await self.emit_event(LifecycleEvent.EXECUTION_COMPLETED)
        return await self.transition_to(RuntimeState.VALIDATING, "start_validation")

    async def complete_task(self) -> bool:
        """Complete task successfully (VALIDATING → DONE)."""
        if self._state != RuntimeState.VALIDATING:
            logger.warning("Cannot complete from state: %s", self._state.value)
            return False

        await self.emit_event(LifecycleEvent.VALIDATION_COMPLETED)
        success = await self.transition_to(RuntimeState.DONE, "task_complete")
        if success:
            self._stats["tasks_completed"] += 1
        return success

    async def fail_task(self, reason: Optional[str] = None) -> bool:
        """Fail task (any state → FAILED)."""
        self._stats["tasks_failed"] += 1
        self._stats["errors"] += 1
        await self.emit_event(LifecycleEvent.ERROR_OCCURRED, {"reason": reason})
        return await self.transition_to(RuntimeState.FAILED, f"task_failed:{reason}")

    async def start_recovery(self) -> bool:
        """Start recovery (FAILED/EXECUTING/VALIDATING → RECOVERING)."""
        if self._state not in [RuntimeState.FAILED, RuntimeState.EXECUTING, RuntimeState.VALIDATING]:
            logger.warning("Cannot recover from state: %s", self._state.value)
            return False

        await self.emit_event(LifecycleEvent.RECOVERY_STARTED)
        self._stats["recoveries"] += 1
        return await self.transition_to(RuntimeState.RECOVERING, "start_recovery")

    async def complete_recovery(self, success: bool = True) -> bool:
        """Complete recovery (RECOVERING → READY or FAILED)."""
        if self._state != RuntimeState.RECOVERING:
            logger.warning("Cannot complete recovery from state: %s", self._state.value)
            return False

        if success:
            await self.emit_event(LifecycleEvent.RECOVERY_COMPLETED)
            return await self.transition_to(RuntimeState.READY, "recovery_success")
        else:
            await self.emit_event(LifecycleEvent.RECOVERY_FAILED)
            return await self.transition_to(RuntimeState.FAILED, "recovery_failed")

    async def reset(self) -> bool:
        """Reset to READY state (DONE/FAILED → READY)."""
        if self._state not in [RuntimeState.DONE, RuntimeState.FAILED]:
            logger.warning("Cannot reset from state: %s", self._state.value)
            return False

        return await self.transition_to(RuntimeState.READY, "reset")

    async def shutdown(self) -> bool:
        """Shutdown runtime (any state → SHUTDOWN)."""
        logger.info("Runtime controller shutting down...")
        await self.emit_event(LifecycleEvent.SHUTDOWN)

        # Cleanup subsystems
        for name, subsystem in self._subsystems.items():
            if hasattr(subsystem, "shutdown"):
                try:
                    if asyncio.iscoroutinefunction(subsystem.shutdown):
                        await subsystem.shutdown()
                    else:
                        subsystem.shutdown()
                    logger.debug("Shutdown subsystem: %s", name)
                except Exception as exc:
                    logger.error("Subsystem %s shutdown error: %s", name, exc)

        self._running = False
        await self.emit_event(LifecycleEvent.SHUTDOWN_COMPLETED)
        logger.info("Runtime controller shutdown complete")

        return True

    # -------------------------------------------------------------------------
    # Health & Status
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get runtime status."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self._state.value,
            "previous_state": self._previous_state.value if self._previous_state else None,
            "state_duration_seconds": round(self.get_state_duration(), 2),
            "uptime_seconds": round(self.uptime_seconds, 2),
            "is_running": self._running,
            "stats": dict(self._stats),
            "subsystems": list(self._subsystems.keys()),
            "transitions_count": len(self._transitions),
        }

    def is_healthy(self) -> bool:
        """Check if runtime is healthy."""
        return (
            self._running
            and self._state not in [RuntimeState.FAILED]
            and self._stats["errors"] < 10
        )

    def is_ready_for_work(self) -> bool:
        """Check if runtime is ready to accept work."""
        return self._running and self._state == RuntimeState.READY

    def can_recover(self) -> bool:
        """Check if runtime can attempt recovery."""
        return self._state in [RuntimeState.FAILED, RuntimeState.RECOVERING]

    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------

    def get_transition_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent transition history."""
        transitions = self._transitions[-limit:]
        return [
            {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "timestamp": t.timestamp.isoformat(),
                "duration_ms": t.duration_ms,
                "reason": t.reason,
                "success": t.success,
            }
            for t in transitions
        ]

    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent errors."""
        errors = []
        for t in self._transitions[-limit:]:
            if t.to_state == RuntimeState.FAILED or not t.success:
                errors.append({
                    "from_state": t.from_state.value,
                    "to_state": t.to_state.value,
                    "reason": t.reason,
                    "timestamp": t.timestamp.isoformat(),
                })
        return errors
