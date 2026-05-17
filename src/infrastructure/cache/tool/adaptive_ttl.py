"""Adaptive TTL Engine with time-aware EMA.

Provides dynamic TTL adjustment based on hit rate patterns.
TTL cannot grow beyond 2× base, score decays with inactivity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveTTLConfig:
    """Configuration for adaptive TTL."""

    base_ttl_seconds: float = 300.0
    min_ttl_seconds: float = 60.0
    max_ttl_multiplier: float = 2.0
    decay_factor: float = 0.95
    hit_rate_window: int = 100
    inactivity_threshold_seconds: float = 3600.0


class EMA:
    """Exponential Moving Average with time decay."""

    def __init__(self, alpha: float = 0.3) -> None:
        self.alpha = alpha
        self._value: float | None = None
        self._last_update: float = 0.0

    def update(self, value: float, timestamp: float | None = None) -> float:
        """Update EMA with new value.

        Args:
            value: New value
            timestamp: Optional timestamp

        Returns:
            Updated EMA value
        """
        now = timestamp or time.time()

        if self._value is None:
            self._value = value
        else:
            self._value = self.alpha * value + (1 - self.alpha) * self._value

        self._last_update = now
        return self._value

    def get(self) -> float | None:
        """Get current EMA value."""
        return self._value

    def decay(self, decay_factor: float) -> float | None:
        """Apply decay to EMA.

        Args:
            decay_factor: Decay factor to apply

        Returns:
            Decayed value
        """
        if self._value is not None:
            self._value *= decay_factor
        return self._value

    def reset(self) -> None:
        """Reset EMA."""
        self._value = None
        self._last_update = 0.0


class HitRateTracker:
    """Tracks hit rate with rolling window."""

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._hits: int = 0
        self._total: int = 0
        self._history: list[bool] = []
        self._timestamps: list[float] = []
        self._ema = EMA(alpha=0.3)

    def record(self, hit: bool, timestamp: float | None = None) -> None:
        """Record a hit or miss.

        Args:
            hit: True if cache hit, False if miss
            timestamp: Optional timestamp
        """
        now = timestamp or time.time()

        self._history.append(hit)
        self._timestamps.append(now)

        if hit:
            self._hits += 1
        self._total += 1

        if len(self._history) > self.window_size:
            removed = self._history.pop(0)
            removed_time = self._timestamps.pop(0)
            if removed:
                self._hits -= 1
            self._total -= 1

        hit_rate = self._hits / self._total if self._total > 0 else 0.0
        self._ema.update(hit_rate, now)

    def get_hit_rate(self) -> float:
        """Get current hit rate."""
        return self._hits / self._total if self._total > 0 else 0.0

    def get_ema_hit_rate(self) -> float | None:
        """Get EMA of hit rate."""
        return self._ema.get()


class AdaptiveTTLEngine:
    """Adaptive TTL engine with time-aware adjustments.

    Formula:
    score = EMA(hit_rate, time_decay=True)
    ttl_multiplier = min(1 + score, 2.0)

    Constraints:
    - TTL cannot grow beyond 2× base
    - Score decays with inactivity time
    """

    def __init__(
        self,
        tool: str,
        config: AdaptiveTTLConfig | None = None,
    ) -> None:
        self.tool = tool
        self.config = config or AdaptiveTTLConfig()

        self._hit_rate_tracker = HitRateTracker(
            window_size=self.config.hit_rate_window
        )
        self._base_ttl = self.config.base_ttl_seconds
        self._current_ttl = self.config.base_ttl_seconds
        self._current_multiplier = 1.0

        self._last_activity: float = time.time()
        self._activity_count = 0

        self._lock = asyncio.Lock()

    def record_access(self, hit: bool) -> None:
        """Record a cache access.

        Args:
            hit: True if cache hit, False if miss
        """
        self._hit_rate_tracker.record(hit)
        self._last_activity = time.time()
        self._activity_count += 1

        if self._activity_count % 10 == 0:
            self._recompute_ttl()

    def _recompute_ttl(self) -> None:
        """Recompute TTL based on current hit rate."""
        ema_hit_rate = self._hit_rate_tracker.get_ema_hit_rate()

        if ema_hit_rate is not None:
            score = ema_hit_rate
            self._current_multiplier = min(
                1.0 + score,
                self.config.max_ttl_multiplier,
            )
        else:
            self._current_multiplier = 1.0

        self._current_ttl = self._base_ttl * self._current_multiplier

        self._current_ttl = max(
            self._current_ttl,
            self.config.min_ttl_seconds,
        )

    def get_ttl(self, key: str | None = None) -> float:
        """Get current TTL for a key.

        Args:
            key: Optional key (for per-key TTL tracking)

        Returns:
            TTL in seconds
        """
        now = time.time()
        inactive_time = now - self._last_activity

        if inactive_time > self.config.inactivity_threshold_seconds:
            self._apply_inactivity_decay()

        return self._current_ttl

    def _apply_inactivity_decay(self) -> None:
        """Apply decay due to inactivity."""
        self._hit_rate_tracker._ema.decay(self.config.decay_factor)
        self._recompute_ttl()
        logger.debug(
            f"TTL for tool {self.tool} decayed to {self._current_ttl}s "
            f"due to inactivity"
        )

    def set_base_ttl(self, ttl_seconds: float) -> None:
        """Set base TTL.

        Args:
            ttl_seconds: New base TTL in seconds
        """
        self._base_ttl = ttl_seconds
        self._recompute_ttl()

    def reset(self) -> None:
        """Reset adaptive TTL state."""
        self._hit_rate_tracker = HitRateTracker(
            window_size=self.config.hit_rate_window
        )
        self._current_ttl = self._base_ttl
        self._current_multiplier = 1.0
        self._last_activity = time.time()
        self._activity_count = 0

    def get_stats(self) -> dict[str, Any]:
        """Get TTL engine statistics."""
        return {
            "tool": self.tool,
            "base_ttl": self._base_ttl,
            "current_ttl": self._current_ttl,
            "current_multiplier": self._current_multiplier,
            "hit_rate": self._hit_rate_tracker.get_hit_rate(),
            "ema_hit_rate": self._hit_rate_tracker.get_ema_hit_rate(),
            "activity_count": self._activity_count,
            "last_activity_age": time.time() - self._last_activity,
        }
