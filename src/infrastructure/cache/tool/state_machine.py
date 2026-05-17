"""Key state machine with deterministic transitions.

Provides linearizable per-key FSM with strict transition rules.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from src.infrastructure.cache.tool.types import CacheEntry, KeyState

logger = logging.getLogger(__name__)


class TransitionError(Exception):
    """Invalid state transition attempted."""

    pass


class KeyStateMachine:
    """Per-key finite state machine with linearizable transitions.

    State transitions are deterministic and follow strict priority:
    DEGRADED > REFRESHING > STALE > FRESH > LOADING > MISS

    Transition table:
    | Current   | Event           | Next          |
    |-----------|-----------------|---------------|
    | MISS      | first request   | LOADING       |
    | LOADING   | success         | FRESH         |
    | LOADING   | failure         | MISS/COOLDOWN |
    | FRESH     | TTL expired     | STALE         |
    | STALE     | refresh trig.   | REFRESHING    |
    | REFRESHING| success         | FRESH         |
    | REFRESHING| failure         | STALE         |
    | ANY       | overload        | DEGRADED      |
    | DEGRADED  | recovery        | STALE         |
    """

    def __init__(self, key: str) -> None:
        self.key = key
        self._state = KeyState.MISS
        self._lock = asyncio.Lock()
        self._last_transition = time.time()
        self._transition_count = 0
        self._failure_count = 0
        self._on_state_change: list[Callable[[KeyState, KeyState], None]] = []

    @property
    def state(self) -> KeyState:
        """Current state (read-only)."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Check if state is terminal."""
        return self._state in (KeyState.MISS, KeyState.FRESH)

    def on_state_change(
        self,
        callback: Callable[[KeyState, KeyState], None],
    ) -> None:
        """Register state change callback."""
        self._on_state_change.append(callback)

    async def transition(
        self,
        event: str,
        new_state: KeyState,
        force: bool = False,
    ) -> bool:
        """Transition to new state.

        Args:
            event: Event name triggering transition
            new_state: Target state
            force: Force transition even if not in valid table

        Returns:
            True if transition succeeded

        Raises:
            TransitionError: If transition is invalid
        """
        async with self._lock:
            return self._transition_internal(event, new_state, force)

    def _transition_internal(
        self,
        event: str,
        new_state: KeyState,
        force: bool = False,
    ) -> bool:
        """Internal transition logic (must hold lock)."""
        old_state = self._state

        if not force and not self._is_valid_transition(old_state, new_state):
            logger.warning(
                f"Invalid transition for key {self.key}: "
                f"{old_state.name} + {event} -> {new_state.name}"
            )
            raise TransitionError(
                f"Invalid transition: {old_state.name} + {event} -> {new_state.name}"
            )

        self._state = new_state
        self._last_transition = time.time()
        self._transition_count += 1

        if new_state in (KeyState.MISS, KeyState.LOADING, KeyState.REFRESHING):
            self._failure_count = 0

        logger.debug(
            f"Key {self.key}: {old_state.name} + {event} -> {new_state.name}"
        )

        for callback in self._on_state_change:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.warning(f"State change callback error: {e}")

        return True

    def _is_valid_transition(self, current: KeyState, target: KeyState) -> bool:
        """Check if transition is valid per spec.

        Priority: DEGRADED > REFRESHING > STALE > FRESH > LOADING > MISS
        """
        transitions = {
            KeyState.MISS: {KeyState.LOADING},
            KeyState.LOADING: {KeyState.FRESH, KeyState.MISS, KeyState.COOLDOWN},
            KeyState.FRESH: {KeyState.STALE, KeyState.DEGRADED},
            KeyState.STALE: {KeyState.REFRESHING, KeyState.DEGRADED, KeyState.FRESH},
            KeyState.REFRESHING: {KeyState.FRESH, KeyState.STALE, KeyState.DEGRADED},
            KeyState.DEGRADED: {KeyState.STALE, KeyState.FRESH},
            KeyState.COOLDOWN: {KeyState.MISS, KeyState.LOADING},
        }

        valid_targets = transitions.get(current, set())
        return target in valid_targets

    async def try_transition(self, event: str, new_state: KeyState) -> bool:
        """Try transition, return False if invalid instead of raising."""
        try:
            return await self.transition(event, new_state)
        except TransitionError:
            return False

    def check_and_update_stale(self, now: float, expires_at: float | None) -> KeyState:
        """Check if entry should transition to STALE.

        Args:
            now: Current time
            expires_at: Entry expiration time

        Returns:
            Current state (may be STALE if TTL expired)
        """
        if expires_at is not None and now > expires_at:
            if self._state == KeyState.FRESH:
                self._state = KeyState.STALE
                logger.debug(f"Key {self.key} expired, transitioned to STALE")
        return self._state


class StateManager:
    """Manages state machines for multiple keys.

    Provides linearizable access per key with thread-safe operations.
    """

    def __init__(self) -> None:
        self._machines: dict[str, KeyStateMachine] = {}
        self._lock = asyncio.Lock()
        self._global_degraded = False
        self._degraded_since: float | None = None

    async def get_machine(self, key: str) -> KeyStateMachine:
        """Get or create state machine for key."""
        async with self._lock:
            if key not in self._machines:
                self._machines[key] = KeyStateMachine(key)
            return self._machines[key]

    async def get_state(self, key: str) -> KeyState:
        """Get current state for key."""
        machine = await self.get_machine(key)
        return machine.state

    async def transition(
        self,
        key: str,
        event: str,
        new_state: KeyState,
    ) -> bool:
        """Transition key to new state."""
        machine = await self.get_machine(key)

        if self._global_degraded and new_state != KeyState.DEGRADED:
            new_state = KeyState.DEGRADED

        return await machine.transition(event, new_state)

    async def try_transition(self, key: str, event: str, new_state: KeyState) -> bool:
        """Try transition, return False if invalid."""
        machine = await self.get_machine(key)
        return await machine.try_transition(event, new_state)

    async def enter_degraded(self) -> None:
        """Enter global degraded mode."""
        async with self._lock:
            if not self._global_degraded:
                self._global_degraded = True
                self._degraded_since = time.time()
                logger.warning("Entering global DEGRADED mode")

                for key, machine in self._machines.items():
                    if machine.state not in (KeyState.DEGRADED, KeyState.REFRESHING):
                        try:
                            machine._transition_internal("system_overload", KeyState.DEGRADED, force=True)
                        except TransitionError:
                            pass

    async def try_exit_degraded(
        self,
        memory_pressure: float,
        pending_keys: int,
        error_rate: float,
        threshold: float = 0.8,
    ) -> bool:
        """Try to exit degraded mode.

        Returns:
            True if exited degraded mode
        """
        async with self._lock:
            if not self._global_degraded:
                return True

            should_exit = (
                memory_pressure < threshold
                and pending_keys < threshold * 100
                and error_rate < 0.05
            )

            if should_exit:
                self._global_degraded = False
                self._degraded_since = None
                logger.info("Exiting global DEGRADED mode")
                return True

            return False

    @property
    def is_degraded(self) -> bool:
        """Check if in global degraded mode."""
        return self._global_degraded

    async def cleanup(self, max_age: float = 3600.0) -> int:
        """Clean up old state machines.

        Args:
            max_age: Maximum age in seconds before cleanup

        Returns:
            Number of machines cleaned up
        """
        async with self._lock:
            now = time.time()
            to_remove = []

            for key, machine in self._machines.items():
                if now - machine._last_transition > max_age:
                    if machine.state in (KeyState.MISS, KeyState.FRESH):
                        to_remove.append(key)

            for key in to_remove:
                del self._machines[key]

            return len(to_remove)
