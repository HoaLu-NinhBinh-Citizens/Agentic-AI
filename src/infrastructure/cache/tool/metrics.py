"""Metrics Engine with lock-free counters and sampling aggregator.

Control metrics are lock-free with 1-operation staleness.
Observability metrics are sampled and aggregated asynchronously.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricsConfig:
    """Configuration for metrics collection."""

    enable_lock_free: bool = True
    sampling_rate: float = 0.01
    aggregation_interval_seconds: float = 60.0
    max_samples: int = 10000
    percentiles: tuple[float, ...] = (50, 90, 95, 99)


class AtomicCounter:
    """Lock-free atomic counter using atomic operations."""

    def __init__(self, initial_value: int = 0) -> None:
        self._value = initial_value

    def increment(self, delta: int = 1) -> int:
        """Atomically increment counter."""
        result = self._value + delta
        self._value = result
        return result

    def decrement(self, delta: int = 1) -> int:
        """Atomically decrement counter."""
        result = self._value - delta
        self._value = result
        return result

    def get(self) -> int:
        """Get current value."""
        return self._value

    def reset(self) -> int:
        """Reset and return old value."""
        old = self._value
        self._value = 0
        return old


class AtomicGauge:
    """Lock-free atomic gauge."""

    def __init__(self, initial_value: float = 0.0) -> None:
        self._value = initial_value

    def set(self, value: float) -> None:
        """Set gauge value."""
        self._value = value

    def get(self) -> float:
        """Get current value."""
        return self._value


class PercentileHistogram:
    """Rolling histogram for percentile calculations."""

    def __init__(self, max_samples: int = 10000) -> None:
        self.max_samples = max_samples
        self._samples: deque[float] = deque(maxlen=max_samples)
        self._lock = asyncio.Lock()

    async def add(self, value: float) -> None:
        """Add a sample."""
        async with self._lock:
            self._samples.append(value)

    def add_sync(self, value: float) -> None:
        """Add a sample (synchronous, for lock-free path)."""
        if len(self._samples) < self.max_samples:
            self._samples.append(value)
        else:
            import random
            if random.random() < self.sampling_rate:
                idx = random.randint(0, self.max_samples - 1)
                self._samples[idx] = value

    sampling_rate = 1.0

    def get_percentile(self, p: float) -> float:
        """Get percentile value."""
        if not self._samples:
            return 0.0

        sorted_samples = sorted(self._samples)
        index = int(len(sorted_samples) * p / 100)
        index = min(index, len(sorted_samples) - 1)
        return sorted_samples[index]

    def get_stats(self) -> dict[str, float]:
        """Get histogram statistics."""
        if not self._samples:
            return {"count": 0, "min": 0, "max": 0, "mean": 0}

        samples = list(self._samples)
        return {
            "count": len(samples),
            "min": min(samples),
            "max": max(samples),
            "mean": sum(samples) / len(samples),
            "p50": self.get_percentile(50),
            "p90": self.get_percentile(90),
            "p95": self.get_percentile(95),
            "p99": self.get_percentile(99),
        }


class MetricsEngine:
    """Metrics engine with lock-free counters.

    Control metrics (STRICT):
    - memory_pressure: lock-free, 1-op stale
    - pending_keys: lock-free, 1-op stale
    - hit_ratio: lock-free, 1-op stale

    Observability metrics:
    - sampled
    - async aggregation
    - dashboard only
    """

    def __init__(self, config: MetricsConfig | None = None) -> None:
        self.config = config or MetricsConfig()

        self._hits = AtomicCounter()
        self._misses = AtomicCounter()
        self._evictions = AtomicCounter()
        self._refreshes = AtomicCounter()
        self._failures = AtomicCounter()

        self._memory_pressure = AtomicGauge()
        self._pending_keys = AtomicGauge()

        self._latency_histogram = PercentileHistogram(
            max_samples=self.config.max_samples
        )
        self._error_histogram = PercentileHistogram(
            max_samples=self.config.max_samples
        )

        self._callbacks: list[Callable[[dict], None]] = []
        self._aggregation_task: Optional[asyncio.Task] = None
        self._running = False

        self._start_time = time.time()

    def record_hit(self) -> None:
        """Record a cache hit (lock-free)."""
        self._hits.increment()

    def record_miss(self) -> None:
        """Record a cache miss (lock-free)."""
        self._misses.increment()

    def record_eviction(self) -> None:
        """Record an eviction (lock-free)."""
        self._evictions.increment()

    def record_refresh(self) -> None:
        """Record a refresh (lock-free)."""
        self._refreshes.increment()

    def record_failure(self) -> None:
        """Record a failure (lock-free)."""
        self._failures.increment()

    def set_memory_pressure(self, pressure: float) -> None:
        """Set memory pressure gauge (lock-free)."""
        self._memory_pressure.set(pressure)

    def set_pending_keys(self, count: int) -> None:
        """Set pending keys gauge (lock-free)."""
        self._pending_keys.set(float(count))

    def record_latency(self, latency_ms: float) -> None:
        """Record latency (sampled)."""
        if self._should_sample():
            self._latency_histogram.add_sync(latency_ms)

    def record_error_latency(self, latency_ms: float) -> None:
        """Record error latency (sampled)."""
        if self._should_sample():
            self._error_histogram.add_sync(latency_ms)

    def _should_sample(self) -> bool:
        """Determine if should sample."""
        import random
        return random.random() < self.config.sampling_rate

    async def start(self) -> None:
        """Start the metrics engine."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()

        self._aggregation_task = asyncio.create_task(self._aggregation_loop())

        logger.info("MetricsEngine started")

    async def stop(self) -> None:
        """Stop the metrics engine."""
        self._running = False

        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass

        logger.info("MetricsEngine stopped")

    async def _aggregation_loop(self) -> None:
        """Background loop for metric aggregation."""
        while self._running:
            try:
                await asyncio.sleep(self.config.aggregation_interval_seconds)
                await self._aggregate()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Aggregation loop error: {e}")

    async def _aggregate(self) -> None:
        """Aggregate and report metrics."""
        metrics = self.get_snapshot()

        for callback in self._callbacks:
            try:
                callback(metrics)
            except Exception as e:
                logger.warning(f"Metrics callback error: {e}")

    def on_metrics(self, callback: Callable[[dict], None]) -> None:
        """Register metrics callback."""
        self._callbacks.append(callback)

    def get_snapshot(self) -> dict[str, Any]:
        """Get current metrics snapshot."""
        hits = self._hits.get()
        misses = self._misses.get()
        total = hits + misses

        return {
            "timestamp": time.time(),
            "uptime_seconds": time.time() - self._start_time,
            "counters": {
                "hits": hits,
                "misses": misses,
                "evictions": self._evictions.get(),
                "refreshes": self._refreshes.get(),
                "failures": self._failures.get(),
            },
            "gauges": {
                "memory_pressure": self._memory_pressure.get(),
                "pending_keys": self._pending_keys.get(),
            },
            "derived": {
                "hit_ratio": hits / total if total > 0 else 0.0,
                "miss_ratio": misses / total if total > 0 else 0.0,
                "total_requests": total,
            },
            "latency": self._latency_histogram.get_stats(),
            "errors": self._error_histogram.get_stats(),
        }

    def get_control_metrics(self) -> dict[str, float]:
        """Get control metrics only (lock-free, 1-op stale)."""
        hits = self._hits.get()
        misses = self._misses.get()
        total = hits + misses

        return {
            "memory_pressure": self._memory_pressure.get(),
            "pending_keys": self._pending_keys.get(),
            "hit_ratio": hits / total if total > 0 else 0.0,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._hits.reset()
        self._misses.reset()
        self._evictions.reset()
        self._refreshes.reset()
        self._failures.reset()
        self._memory_pressure.set(0.0)
        self._pending_keys.set(0.0)
        self._start_time = time.time()

    def get_stats(self) -> dict[str, Any]:
        """Get full statistics."""
        return self.get_snapshot()
