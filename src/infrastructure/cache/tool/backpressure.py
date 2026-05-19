"""Backpressure Manager for cache overload protection.

Propagates backpressure signals to upstream components.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BackpressureSeverity(Enum):
    """Severity levels for backpressure signals."""

    NORMAL = 0.0
    THROTTLE = 0.5
    REJECT = 0.8
    SELF_PRESERVATION = 0.9


@dataclass
class BackpressureSignal:
    """Signal emitted when backpressure is detected."""

    source: str
    severity: float
    metric: str
    current_value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class BackpressureConfig:
    """Configuration for backpressure management."""

    throttle_threshold: float = 0.5
    reject_threshold: float = 0.8
    self_preservation_threshold: float = 0.9

    min_preservation_duration: float = 30.0
    cooldown_after_preservation: float = 60.0
    flapping_threshold: int = 3
    flapping_window_seconds: float = 300.0

    check_interval_seconds: float = 1.0


@dataclass
class BackpressureStats:
    """Statistics for backpressure management."""

    signals_emitted: int = 0
    throttle_events: int = 0
    reject_events: int = 0
    preservation_activations: int = 0
    current_severity: float = 0.0


class BackpressureManager:
    """Manages backpressure propagation.

    Signal Types:
    - THROTTLE (0.5-0.8): Reduce request rate
    - REJECT (0.8-0.9): Reject new requests
    - SELF_PRESERVATION (>0.9): Cache self-protection mode

    Guarantees:
    - Backpressure signals reach agent
    - Flapping prevention
    - Self-preservation when severity > 0.9
    """

    def __init__(
        self,
        config: BackpressureConfig | None = None,
    ) -> None:
        self.config = config or BackpressureConfig()

        self._signals: dict[str, BackpressureSignal] = {}
        self._severity: float = 0.0

        self._preservation_active: bool = False
        self._preservation_enter_time: Optional[float] = None
        self._last_exit_time: Optional[float] = None
        self._activation_count: int = 0
        self._activation_window_start: float = time.time()

        self._on_throttle: list[Callable[[float], None]] = []
        self._on_reject: list[Callable[[], None]] = []
        self._on_preserve: list[Callable[[], None]] = []
        self._on_recover: list[Callable[[], None]] = []

        self._stats = BackpressureStats()
        self._lock = asyncio.Lock()

    @property
    def stats(self) -> BackpressureStats:
        """Get current backpressure statistics."""
        return self._stats

    @property
    def is_preservation_active(self) -> bool:
        """Check if self-preservation mode is active."""
        return self._preservation_active

    async def emit_signal(self, signal: BackpressureSignal) -> None:
        """Emit a backpressure signal.

        Args:
            signal: The backpressure signal to emit
        """
        async with self._lock:
            self._signals[signal.source] = signal
            self._severity = self._calculate_overall_severity()
            self._stats.signals_emitted += 1

            await self._handle_severity_change()

    def _calculate_overall_severity(self) -> float:
        """Calculate overall severity from all signals."""
        if not self._signals:
            return 0.0

        max_severity = 0.0
        for signal in self._signals.values():
            if signal.severity > max_severity:
                max_severity = signal.severity

        return min(1.0, max_severity)

    async def _handle_severity_change(self) -> None:
        """Handle changes in backpressure severity."""
        if self._severity >= self.config.self_preservation_threshold:
            if not self._preservation_active:
                await self._activate_preservation()
        elif self._severity >= self.config.reject_threshold:
            self._stats.reject_events += 1
            await self._emit_reject()
        elif self._severity >= self.config.throttle_threshold:
            self._stats.throttle_events += 1
            await self._emit_throttle()

    async def _activate_preservation(self) -> None:
        """Activate self-preservation mode."""
        if not await self._should_enter_preservation():
            return

        self._preservation_active = True
        self._preservation_enter_time = time.time()
        self._stats.preservation_activations += 1
        self._activation_count += 1

        if time.time() - self._activation_window_start > self.config.flapping_window_seconds:
            self._activation_count = 1
            self._activation_window_start = time.time()

        self._stats.current_severity = self._severity

        logger.warning(
            f"Self-preservation activated: severity={self._severity:.2f}"
        )

        for callback in self._on_preserve:
            try:
                callback()
            except Exception as e:
                logger.error(f"Preservation callback error: {e}")

    async def _should_enter_preservation(self) -> bool:
        """Check if should enter preservation mode with flapping prevention."""
        if self._preservation_active:
            return False

        if self._last_exit_time:
            if time.time() - self._last_exit_time < self.config.cooldown_after_preservation:
                return False

        if self._activation_count >= self.config.flapping_threshold:
            if time.time() - self._activation_window_start < self.config.flapping_window_seconds:
                logger.error("Flapping detected! Forcing extended cooldown")
                self._last_exit_time = time.time()
                self._activation_count = 0
                return False

        return self._severity >= self.config.self_preservation_threshold

    async def _emit_throttle(self) -> None:
        """Emit throttle signal to upstream."""
        throttle_ratio = (self._severity - self.config.throttle_threshold) / (
            self.config.reject_threshold - self.config.throttle_threshold
        )

        for callback in self._on_throttle:
            try:
                callback(throttle_ratio)
            except Exception as e:
                logger.error(f"Throttle callback error: {e}")

    async def _emit_reject(self) -> None:
        """Emit reject signal to upstream."""
        for callback in self._on_reject:
            try:
                callback()
            except Exception as e:
                logger.error(f"Reject callback error: {e}")

    async def should_serve_request(self) -> tuple[bool, Optional[str]]:
        """Check if request should be served despite backpressure.

        Returns:
            Tuple of (allowed, reason)
        """
        if not self._preservation_active:
            return True, None

        if self._preservation_enter_time:
            elapsed = time.time() - self._preservation_enter_time
            if elapsed >= self.config.min_preservation_duration:
                if self._severity < self.config.throttle_threshold:
                    await self._exit_preservation()
                    return True, None

        return False, "SELF_PRESERVATION_ACTIVE"

    async def _exit_preservation(self) -> None:
        """Exit preservation mode."""
        self._preservation_active = False
        self._preservation_enter_time = None
        self._last_exit_time = time.time()
        self._severity = 0.0
        self._signals.clear()
        self._stats.current_severity = 0.0

        logger.info("Self-preservation deactivated, system recovered")

        for callback in self._on_recover:
            try:
                callback()
            except Exception as e:
                logger.error(f"Recover callback error: {e}")

    def on_throttle(self, callback: Callable[[float], None]) -> None:
        """Register throttle callback."""
        self._on_throttle.append(callback)

    def on_reject(self, callback: Callable[[], None]) -> None:
        """Register reject callback."""
        self._on_reject.append(callback)

    def on_preserve(self, callback: Callable[[], None]) -> None:
        """Register preserve callback."""
        self._on_preserve.append(callback)

    def on_recover(self, callback: Callable[[], None]) -> None:
        """Register recover callback."""
        self._on_recover.append(callback)

    def get_severity(self) -> float:
        """Get current overall severity."""
        return self._severity

    def get_signals(self) -> dict[str, BackpressureSignal]:
        """Get all current backpressure signals."""
        return self._signals.copy()

    async def clear_signals(self) -> None:
        """Clear all backpressure signals."""
        async with self._lock:
            self._signals.clear()
            self._severity = 0.0

    def get_throttle_ratio(self) -> float:
        """Calculate current throttle ratio.

        Returns:
            Throttle ratio from 0.0 (no throttle) to 1.0 (full throttle)
        """
        if self._severity < self.config.throttle_threshold:
            return 0.0
        if self._severity >= self.config.reject_threshold:
            return 1.0

        return (self._severity - self.config.throttle_threshold) / (
            self.config.reject_threshold - self.config.throttle_threshold
        )
