"""Metrics registry for Phase 2D.

Provides in-memory metrics collection with Prometheus text format export.
Designed to avoid cardinality explosion by limiting tag values.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SimpleHistogram:
    """Histogram with fixed buckets for memory efficiency.

    Uses bucket counting instead of storing individual values.
    """

    buckets: list[float] | None = None
    counts: list[int] | None = None
    sum: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        """Initialize bucket counts."""
        if self.buckets is None:
            self.buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        if self.counts is None:
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        """Record an observation.

        Args:
            value: The observed value.
        """
        self.sum += value
        self.count += 1

        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self.counts[i] += 1
                return

        self.counts[-1] += 1

    def export(self) -> tuple[list[float], list[int], float, int]:
        """Export histogram data.

        Returns:
            Tuple of (buckets, counts, sum, total_count).
        """
        return self.buckets, self.counts, self.sum, self.count


class MetricsRegistry:
    """In-memory metrics registry with Prometheus text format.

    Supports counters and histograms. All labels must have low cardinality.
    """

    _instance: "MetricsRegistry | None" = None

    def __init__(self) -> None:
        """Initialize the registry."""
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, SimpleHistogram] = {}
        self._lock = asyncio.Lock()
        self._histogram_buckets: dict[str, list[float]] = {}

    @classmethod
    def get_instance(cls) -> "MetricsRegistry":
        """Get the singleton instance.

        Returns:
            MetricsRegistry instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    def _make_key(self, name: str, tags: dict[str, str]) -> str:
        """Create a metric key from name and tags.

        Args:
            name: Metric name.
            tags: Labels (must be low cardinality).

        Returns:
            Unique key for storage.
        """
        if not tags:
            return name

        tag_parts = [f'{k}="{v}"' for k, v in sorted(tags.items())]
        return f"{name}{{{','.join(tag_parts)}}}"

    async def inc_counter(
        self,
        name: str,
        tags: dict[str, str] | None = None,
        value: int = 1,
    ) -> None:
        """Increment a counter.

        Args:
            name: Counter name.
            tags: Labels (e.g., {"tool": "read_file", "success": "true"}).
            value: Value to add.
        """
        tags = tags or {}
        key = self._make_key(name, tags)

        async with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    async def observe_histogram(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
        buckets: list[float] | None = None,
    ) -> None:
        """Record an observation in a histogram.

        Args:
            name: Histogram name.
            value: Observed value (in seconds).
            tags: Labels.
            buckets: Custom bucket boundaries (optional).
        """
        tags = tags or {}
        key = self._make_key(name, tags)

        async with self._lock:
            if key not in self._histograms:
                hist_buckets = buckets or self._histogram_buckets.get(name)
                self._histograms[key] = SimpleHistogram(buckets=hist_buckets)

            self._histograms[key].observe(value)

    def set_histogram_buckets(
        self,
        name: str,
        buckets: list[float],
    ) -> None:
        """Set bucket configuration for a histogram.

        Args:
            name: Histogram name.
            buckets: Bucket boundaries.
        """
        self._histogram_buckets[name] = buckets

    async def export_text(self) -> str:
        """Export all metrics in Prometheus text format.

        Returns:
            Metrics in Prometheus exposition format.
        """
        async with self._lock:
            lines: list[str] = []

            for key, value in sorted(self._counters.items()):
                metric_name = key.split("{")[0]
                lines.append(f"# HELP {metric_name} Counter metric")
                lines.append(f"# TYPE {metric_name} counter")
                lines.append(f"{key} {value}")

            for key, hist in sorted(self._histograms.items()):
                metric_name = key.split("{")[0]
                buckets, counts, total_sum, total_count = hist.export()

                lines.append(f"# HELP {metric_name} Histogram metric")
                lines.append(f"# TYPE {metric_name} histogram")

                for i, bound in enumerate(buckets):
                    lines.append(
                        f'{key}_bucket{{le="{bound}"}} {counts[i]}'
                    )
                lines.append(f'{key}_bucket{{le="+Inf"}} {counts[-1]}')
                lines.append(f"{key}_sum {total_sum}")
                lines.append(f"{key}_count {total_count}")

            return "\n".join(lines)

    async def get_counter(self, name: str, tags: dict[str, str] | None = None) -> int:
        """Get counter value.

        Args:
            name: Counter name.
            tags: Labels.

        Returns:
            Counter value.
        """
        tags = tags or {}
        key = self._make_key(name, tags)

        async with self._lock:
            return self._counters.get(key, 0)

    async def clear(self) -> None:
        """Clear all metrics."""
        async with self._lock:
            self._counters.clear()
            self._histograms.clear()
