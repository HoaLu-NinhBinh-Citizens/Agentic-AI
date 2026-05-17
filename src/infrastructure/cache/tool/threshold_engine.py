"""Adaptive Threshold Engine with time-decayed EMA and percentile.

Provides dynamic threshold adjustment for load shedding decisions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ThresholdConfig:
    """Configuration for threshold engine."""

    memory_pressure_threshold: float = 0.8
    pending_keys_threshold: int = 100
    queue_saturation_threshold: float = 0.9
    window_size: int = 100
    ema_alpha: float = 0.3
    percentile_window: int = 50
    recovery_threshold_factor: float = 0.8
    soft_protection_multiplier: float = 1.5
    enable_adaptive: bool = True


class PercentileTracker:
    """Tracks percentile values over a rolling window."""

    def __init__(self, window_size: int = 50) -> None:
        self.window_size = window_size
        self._values: deque[float] = deque(maxlen=window_size)

    def add(self, value: float) -> None:
        """Add a value to the window."""
        self._values.append(value)

    def get_percentile(self, p: float) -> float:
        """Get percentile value.

        Args:
            p: Percentile (0-100)

        Returns:
            Percentile value
        """
        if not self._values:
            return 0.0

        sorted_values = sorted(self._values)
        index = int(len(sorted_values) * p / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def get_p95(self) -> float:
        """Get 95th percentile."""
        return self.get_percentile(95)

    def get_p99(self) -> float:
        """Get 99th percentile."""
        return self.get_percentile(99)

    def get_avg(self) -> float:
        """Get average value."""
        if not self._values:
            return 0.0
        return sum(self._values) / len(self._values)


class AdaptiveThresholdEngine:
    """Adaptive threshold engine with EMA and percentile.

    Control metrics:
    - EMA(memory_pressure, time-decayed)
    - P95(pending_keys, rolling window)

    Modes:
    - Soft protection: threshold * 1.5
    - Hard mode: No relaxation

    Key rule: Thresholds must be time-aware (decay-adjusted), not static averages.
    """

    def __init__(self, config: ThresholdConfig | None = None) -> None:
        self.config = config or ThresholdConfig()

        self._memory_ema = EMA(alpha=self.config.ema_alpha)
        self._pending_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )
        self._queue_saturation_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )
        self._error_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )

        self._consecutive_recovery_windows = 0
        self._mode: Literal["normal", "soft", "hard"] = "normal"

        self._last_check: float = time.time()
        self._lock = asyncio.Lock()

    def record_memory_pressure(self, pressure: float) -> None:
        """Record memory pressure metric.

        Args:
            pressure: Memory pressure value (0-1)
        """
        self._memory_ema.update(pressure)
        self._pending_tracker.add(pressure)

    def record_pending_keys(self, count: int) -> None:
        """Record pending keys count.

        Args:
            count: Number of pending keys
        """
        self._pending_tracker.add(float(count))

    def record_queue_saturation(self, saturation: float) -> None:
        """Record queue saturation.

        Args:
            saturation: Queue saturation (0-1)
        """
        self._queue_saturation_tracker.add(saturation)

    def record_error(self, error: bool) -> None:
        """Record error occurrence.

        Args:
            error: True if error occurred
        """
        self._error_tracker.add(1.0 if error else 0.0)

    def get_memory_pressure(self) -> float:
        """Get current memory pressure (EMA)."""
        return self._memory_ema.get() or 0.0

    def get_pending_keys_p95(self) -> float:
        """Get P95 of pending keys."""
        return self._pending_tracker.get_p95()

    def get_queue_saturation(self) -> float:
        """Get current queue saturation."""
        return self._queue_saturation_tracker.get_avg()

    def get_error_rate(self) -> float:
        """Get current error rate."""
        return self._error_tracker.get_avg()

    def should_enter_degraded(
        self,
        memory_pressure: float | None = None,
        pending_keys: int | None = None,
        queue_saturation: float | None = None,
    ) -> bool:
        """Check if should enter degraded mode.

        Enter DEGRADED when ANY of:
        - memory_pressure P95 > threshold
        - pending_keys P95 > threshold
        - refresh_queue_saturation > 90%

        Returns:
            True if should enter degraded mode
        """
        mp = memory_pressure if memory_pressure is not None else self.get_memory_pressure()
        pk = pending_keys if pending_keys is not None else self.get_pending_keys_p95()
        qs = queue_saturation if queue_saturation is not None else self.get_queue_saturation()

        threshold = self._get_current_threshold()

        if mp > threshold:
            logger.warning(f"Memory pressure {mp:.2f} exceeds threshold {threshold:.2f}")
            return True

        if pk > threshold:
            logger.warning(f"Pending keys P95 {pk:.0f} exceeds threshold")
            return True

        if qs > self.config.queue_saturation_threshold:
            logger.warning(f"Queue saturation {qs:.2f} exceeds threshold")
            return True

        return False

    def should_exit_degraded(self) -> bool:
        """Check if should exit degraded mode.

        Exit DEGRADED when ALL true for 3 consecutive windows:
        - memory_pressure < threshold * 0.8
        - pending_keys < threshold * 0.8
        - error_rate < 5%

        Returns:
            True if should exit degraded mode
        """
        mp = self.get_memory_pressure()
        pk = self.get_pending_keys_p95()
        er = self.get_error_rate()

        threshold = self._get_current_threshold() * self.config.recovery_threshold_factor

        should_exit = (
            mp < threshold
            and pk < threshold * 100
            and er < 0.05
        )

        if should_exit:
            self._consecutive_recovery_windows += 1
        else:
            self._consecutive_recovery_windows = 0

        return self._consecutive_recovery_windows >= 3

    def _get_current_threshold(self) -> float:
        """Get current threshold based on mode."""
        base = self.config.memory_pressure_threshold

        if self._mode == "soft":
            return base * self.config.soft_protection_multiplier
        elif self._mode == "hard":
            return base

        return base

    def set_mode(self, mode: Literal["normal", "soft", "hard"]) -> None:
        """Set threshold mode.

        Args:
            mode: Mode to set
        """
        self._mode = mode
        logger.info(f"Threshold mode set to: {mode}")

    def reset(self) -> None:
        """Reset threshold engine state."""
        self._memory_ema = EMA(alpha=self.config.ema_alpha)
        self._pending_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )
        self._queue_saturation_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )
        self._error_tracker = PercentileTracker(
            window_size=self.config.percentile_window
        )
        self._consecutive_recovery_windows = 0
        self._mode = "normal"

    def get_stats(self) -> dict[str, Any]:
        """Get threshold engine statistics."""
        return {
            "memory_pressure_ema": self.get_memory_pressure(),
            "pending_keys_p95": self.get_pending_keys_p95(),
            "queue_saturation": self.get_queue_saturation(),
            "error_rate": self.get_error_rate(),
            "mode": self._mode,
            "consecutive_recovery_windows": self._consecutive_recovery_windows,
            "threshold": self._get_current_threshold(),
        }


class EMA:
    """Simple EMA implementation for threshold engine."""

    def __init__(self, alpha: float = 0.3) -> None:
        self.alpha = alpha
        self._value: float | None = None

    def update(self, value: float) -> float:
        """Update EMA with new value."""
        if self._value is None:
            self._value = value
        else:
            self._value = self.alpha * value + (1 - self.alpha) * self._value
        return self._value

    def get(self) -> float | None:
        """Get current EMA value."""
        return self._value
