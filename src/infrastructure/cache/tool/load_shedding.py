"""Load Shedding Controller with DEGRADED lifecycle management.

Manages system load and transitions to/from DEGRADED mode.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.infrastructure.cache.tool.state_machine import StateManager
from src.infrastructure.cache.tool.threshold_engine import AdaptiveThresholdEngine
from src.infrastructure.cache.tool.types import KeyState, LoadState

logger = logging.getLogger(__name__)


@dataclass
class LoadSheddingConfig:
    """Configuration for load shedding."""

    check_interval_seconds: float = 1.0
    recovery_check_interval_seconds: float = 5.0
    min_degraded_duration_seconds: float = 10.0
    max_degraded_duration_seconds: float = 300.0


class LoadSheddingController:
    """Load shedding controller with DEGRADED lifecycle.

    Enter DEGRADED when ANY of:
    - memory_pressure P95 > threshold
    - pending_keys P95 > threshold
    - refresh_queue_saturation > 90%

    Exit DEGRADED when ALL true for 3 consecutive windows:
    - memory_pressure < threshold * 0.8
    - pending_keys < threshold * 0.8
    - error_rate < 5%

    Guarantees:
    - No blocking I/O in hot path
    - Automatic recovery
    - System always degrades safely
    """

    def __init__(
        self,
        state_manager: StateManager,
        threshold_engine: AdaptiveThresholdEngine,
        config: LoadSheddingConfig | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.threshold_engine = threshold_engine
        self.config = config or LoadSheddingConfig()

        self._load_state = LoadState.NORMAL
        self._degraded_since: float | None = None
        self._recovery_attempts = 0

        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        self._on_degraded_enter: list[Callable[[], None]] = []
        self._on_degraded_exit: list[Callable[[], None]] = []

        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the load shedding controller."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Load shedding controller started")

    async def stop(self) -> None:
        """Stop the load shedding controller."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Load shedding controller stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_and_update_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            interval = (
                self.config.recovery_check_interval_seconds
                if self._load_state == LoadState.DEGRADED
                else self.config.check_interval_seconds
            )
            await asyncio.sleep(interval)

    async def _check_and_update_state(self) -> None:
        """Check metrics and update load state."""
        async with self._lock:
            if self._load_state == LoadState.NORMAL:
                await self._check_normal_state()
            elif self._load_state == LoadState.ELEVATED:
                await self._check_elevated_state()
            elif self._load_state == LoadState.DEGRADED:
                await self._check_degraded_state()

    async def _check_normal_state(self) -> None:
        """Check if should enter elevated or degraded state."""
        if self.threshold_engine.should_enter_degraded():
            await self._enter_degraded()
        elif self._should_enter_elevated():
            self._load_state = LoadState.ELEVATED
            logger.info("Entering ELEVATED load state")

    async def _check_elevated_state(self) -> None:
        """Check elevated state transitions."""
        if self.threshold_engine.should_enter_degraded():
            await self._enter_degraded()
        elif not self._should_enter_elevated():
            self._load_state = LoadState.NORMAL
            logger.info("Returning to NORMAL load state")

    async def _check_degraded_state(self) -> None:
        """Check if should exit degraded state."""
        if self._degraded_since is None:
            await self._exit_degraded()
            return

        min_duration = time.time() - self._degraded_since < self.config.min_degraded_duration_seconds
        max_duration = time.time() - self._degraded_since > self.config.max_degraded_duration_seconds

        if max_duration:
            logger.warning("Max degraded duration reached, forcing recovery")
            await self._exit_degraded()
            return

        if not min_duration:
            return

        if self.threshold_engine.should_exit_degraded():
            await self._exit_degraded()

    def _should_enter_elevated(self) -> bool:
        """Check if should enter elevated state."""
        mp = self.threshold_engine.get_memory_pressure()
        return mp > 0.5

    async def _enter_degraded(self) -> None:
        """Enter degraded mode."""
        async with self._lock:
            if self._load_state == LoadState.DEGRADED:
                return

            self._load_state = LoadState.DEGRADED
            self._degraded_since = time.time()
            self._recovery_attempts = 0

            await self.state_manager.enter_degraded()

            logger.warning(
                f"Entering DEGRADED mode (since {self._degraded_since})"
            )

            for callback in self._on_degraded_enter:
                try:
                    callback()
                except Exception as e:
                    logger.warning(f"Degraded enter callback error: {e}")

    async def _exit_degraded(self) -> None:
        """Exit degraded mode."""
        async with self._lock:
            if self._load_state != LoadState.DEGRADED:
                return

            duration = 0.0
            if self._degraded_since:
                duration = time.time() - self._degraded_since

            self._load_state = LoadState.NORMAL
            self._degraded_since = None
            self._recovery_attempts += 1

            logger.info(f"Exiting DEGRADED mode (duration: {duration:.1f}s)")

            for callback in self._on_degraded_exit:
                try:
                    callback()
                except Exception as e:
                    logger.warning(f"Degraded exit callback error: {e}")

    def on_degraded_enter(self, callback: Callable[[], None]) -> None:
        """Register callback for degraded enter."""
        self._on_degraded_enter.append(callback)

    def on_degraded_exit(self, callback: Callable[[], None]) -> None:
        """Register callback for degraded exit."""
        self._on_degraded_exit.append(callback)

    def should_shed_load(self) -> bool:
        """Check if should shed load (avoid new work)."""
        return self._load_state == LoadState.DEGRADED

    def should_reject_new_work(self) -> bool:
        """Check if should reject new work entirely."""
        if self._load_state != LoadState.DEGRADED:
            return False

        if self._degraded_since is None:
            return True

        severe_duration = time.time() - self._degraded_since > 60.0
        return severe_duration

    @property
    def load_state(self) -> LoadState:
        """Get current load state."""
        return self._load_state

    @property
    def is_degraded(self) -> bool:
        """Check if in degraded mode."""
        return self._load_state == LoadState.DEGRADED

    @property
    def degraded_duration(self) -> float:
        """Get current degraded duration in seconds."""
        if self._degraded_since is None:
            return 0.0
        return time.time() - self._degraded_since

    def get_stats(self) -> dict[str, Any]:
        """Get load shedding statistics."""
        return {
            "load_state": self._load_state.name,
            "is_degraded": self.is_degraded,
            "degraded_since": self._degraded_since,
            "degraded_duration": self.degraded_duration,
            "recovery_attempts": self._recovery_attempts,
            "threshold_stats": self.threshold_engine.get_stats(),
        }
