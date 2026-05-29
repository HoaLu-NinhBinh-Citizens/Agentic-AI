"""Metrics registry for Phase 2D — with cardinality guard.

REF-7: Adds cardinality enforcement to prevent explosion from high-cardinality
label values (e.g. file paths, user IDs, session IDs).

Provides:
- CardinalityLimit: per-metric label cardinality declarations
- @cardinality_guard decorator: enforces limits on functions emitting metrics
- Registry-level enforcement: drops or samples when cardinality exceeded
- Cardinality reporting in /metrics endpoint

Cardinality explosion is the #1 cause of Prometheus/OTLP backends falling over.
High-cardinality labels (file paths, timestamps, UUIDs) must NEVER be used directly.
Always bucket or hash them first.

Example — safe vs unsafe:
    # UNSAFE: cardinality = N files × M operations (explodes)
    registry.inc_counter("file_read", {"path": "/src/foo/bar.c", "op": "read"})

    # SAFE: cardinality = fixed buckets
    registry.inc_counter("file_read", {"path_bucket": "src", "op": "read"})
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# =============================================================================
# CARDINALITY GUARD
# =============================================================================


class CardinalityAction(Enum):
    """What to do when cardinality limit is exceeded."""
    DROP = "drop"          # Silently drop the metric
    SAMPLE = "sample"      # Record to _overflow bucket
    RAISE = "raise"        # Raise CardinalityExceeded (strict mode)


class CardinalityExceeded(Exception):
    """Raised when a metric's cardinality exceeds its declared limit."""

    def __init__(
        self,
        metric: str,
        label: str,
        distinct_values: int,
        limit: int,
    ) -> None:
        self.metric = metric
        self.label = label
        self.distinct_values = distinct_values
        self.limit = limit
        super().__init__(
            f"Cardinality exceeded for '{metric}.{label}': "
            f"{distinct_values} > {limit}",
        )


@dataclass
class CardinalityLimit:
    """Declaration of the expected cardinality for a metric's label dimensions.

    Declaring limits upfront lets the registry detect cardinality drift early,
    before it causes memory exhaustion or Prometheus cardinality storms.
    """
    metric: str
    label: str
    max_distinct: int
    action: CardinalityAction = CardinalityAction.DROP
    description: str = ""

    def should_record(self, distinct_count: int) -> bool:
        if distinct_count > self.max_distinct:
            return False
        return True


def cardinality_guard(
    metric: str,
    label: str,
    max_distinct: int,
    action: CardinalityAction = CardinalityAction.DROP,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that enforces cardinality limits on a function that emits metrics.

    Use this on functions that call MetricsRegistry methods with dynamic label values.

    Example:
        @cardinality_guard(
            metric="file_operation",
            label="path",
            max_distinct=100,
            action=CardinalityAction.SAMPLE,
        )
        async def read_file(path: str) -> None:
            registry.inc_counter("file_operation", {"path": path, "op": "read"})
            ...

    The decorator intercepts every call, tracks distinct label values seen so far,
    and applies `action` when max_distinct is exceeded.
    """
    _seen: dict[str, int] = {}
    _lock = asyncio.Lock()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = f"{metric}:{label}"

            # Track cardinality
            label_value = kwargs.get(label)
            if label_value is None and args:
                label_value = str(args[0])

            async with _lock:
                if label_value is not None:
                    if label_value not in _seen:
                        _seen[label_value] = 0
                    _seen[label_value] += 1

                    if len(_seen) > max_distinct:
                        if action == CardinalityAction.RAISE:
                            raise CardinalityExceeded(
                                metric=metric,
                                label=label,
                                distinct_values=len(_seen),
                                limit=max_distinct,
                            )
                        elif action == CardinalityAction.SAMPLE:
                            # Record with overflow label instead
                            kwargs = dict(kwargs)
                            kwargs[f"_cardinality_exceeded_{label}"] = label_value
                            kwargs[label] = f"_overflow_{len(_seen)}"

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = f"{metric}:{label}"
            label_value = kwargs.get(label)
            if label_value is None and args:
                label_value = str(args[0])

            if label_value is not None:
                if label_value not in _seen:
                    _seen[label_value] = 0
                _seen[label_value] += 1

                if len(_seen) > max_distinct:
                    if action == CardinalityAction.RAISE:
                        raise CardinalityExceeded(
                            metric=metric,
                            label=label,
                            distinct_values=len(_seen),
                            limit=max_distinct,
                        )
                    elif action == CardinalityAction.SAMPLE:
                        kwargs = dict(kwargs)
                        kwargs[label] = f"_overflow_{len(_seen)}"

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# SIMPLE HISTOGRAM
# =============================================================================


@dataclass
class SimpleHistogram:
    """Histogram with fixed buckets for memory efficiency."""

    buckets: list[float] | None = None
    counts: list[int] | None = None
    sum: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if self.buckets is None:
            self.buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        if self.counts is None:
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self.counts[i] += 1
                return
        self.counts[-1] += 1

    def export(self) -> tuple[list[float], list[int], float, int]:
        return self.buckets, self.counts, self.sum, self.count


# =============================================================================
# METRICS REGISTRY
# =============================================================================


class MetricsRegistry:
    """In-memory metrics registry with Prometheus text format and cardinality guard.

    REF-7: Adds cardinality enforcement on all counter/histogram registrations.

    Cardinality limits must be declared via `register_cardinality_limit` before
    observing metrics with those labels. Metrics with undeclared labels are
    allowed by default but emit a warning on first use.

    Safe label usage:
        # Good — fixed cardinality
        registry.inc_counter("http_request", {"method": "GET", "status": "200"})

        # Bad — high cardinality (file paths, UUIDs, timestamps)
        registry.inc_counter("file_read", {"path": "/src/foo/bar.c"})  # DON'T

        # Good — hash or bucket high-cardinality values
        registry.inc_counter("file_read", {"path_bucket": hash_path(p)})
    """

    _instance: "MetricsRegistry | None" = None

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, SimpleHistogram] = {}
        self._lock = asyncio.Lock()
        self._histogram_buckets: dict[str, list[float]] = {}

        # REF-7: cardinality enforcement
        self._cardinality_limits: dict[str, CardinalityLimit] = {}
        self._label_seen: dict[str, set[str]] = defaultdict(set)
        self._undeclared_warned: set[str] = set()
        self._cardinality_violations: int = 0

    @classmethod
    def get_instance(cls) -> "MetricsRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ─── Cardinality management ────────────────────────────────────────────────

    def register_cardinality_limit(
        self,
        metric: str,
        label: str,
        max_distinct: int,
        action: CardinalityAction = CardinalityAction.DROP,
        description: str = "",
    ) -> None:
        """Declare a cardinality limit for a metric's label.

        Call this at startup for every metric with non-trivial label cardinality.
        The registry will enforce the limit on all subsequent observations.

        Args:
            metric:        Metric name (e.g. "http_request").
            label:         Label that may have high cardinality (e.g. "path").
            max_distinct:  Maximum distinct values expected.
            action:        What to do when exceeded (DROP / SAMPLE / RAISE).
            description:   Human-readable reason for the limit.
        """
        key = self._limit_key(metric, label)
        self._cardinality_limits[key] = CardinalityLimit(
            metric=metric,
            label=label,
            max_distinct=max_distinct,
            action=action,
            description=description,
        )
        logger.info(
            "cardinality_limit_registered",
            metric=metric, label=label,
            max_distinct=max_distinct, action=action.value,
        )

    def _limit_key(self, metric: str, label: str) -> str:
        return f"{metric}:{label}"

    def _check_cardinality(
        self,
        metric: str,
        tags: dict[str, str],
    ) -> bool:
        """Check cardinality limits. Returns True if the metric should be recorded.

        Logs a warning for undeclared labels on first occurrence.
        Drops / samples / raises according to the registered action.
        """
        dropped = False
        for label, value in tags.items():
            key = self._limit_key(metric, label)
            limit = self._cardinality_limits.get(key)

            if limit is None:
                # Undeclared label — warn once
                if key not in self._undeclared_warned:
                    logger.warning(
                        "metric_label_not_cardinality_declared",
                        metric=metric, label=label,
                        hint=f"Call register_cardinality_limit('{metric}', '{label}', N)",
                    )
                    self._undeclared_warned.add(key)
                continue

            # Track distinct values seen
            self._label_seen[key].add(value)
            distinct = len(self._label_seen[key])

            if distinct > limit.max_distinct:
                self._cardinality_violations += 1
                if limit.action == CardinalityAction.RAISE:
                    raise CardinalityExceeded(
                        metric=metric,
                        label=label,
                        distinct_values=distinct,
                        limit=limit.max_distinct,
                    )
                elif limit.action == CardinalityAction.DROP:
                    dropped = True
                    logger.debug(
                        "metric_dropped_cardinality_exceeded",
                        metric=metric, label=label,
                        distinct=distinct, limit=limit.max_distinct,
                    )
                elif limit.action == CardinalityAction.SAMPLE:
                    # Replace high-cardinality value with bucket
                    tags[label] = f"_overflow_{distinct}"
                    logger.debug(
                        "metric_sampled_cardinality_exceeded",
                        metric=metric, label=label, distinct=distinct,
                    )

        return not dropped

    # ─── Metric operations ─────────────────────────────────────────────────────

    def _make_key(self, name: str, tags: dict[str, str]) -> str:
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
        """Increment a counter with cardinality enforcement.

        Args:
            name:  Counter name.
            tags:  Labels. High-cardinality values (paths, UUIDs, timestamps)
                   must be bucketed or hashed first. Register limits via
                   `register_cardinality_limit` to enforce at runtime.
            value: Value to add.
        """
        tags = dict(tags) if tags else {}
        if not self._check_cardinality(name, tags):
            return

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
        """Record a histogram observation with cardinality enforcement.

        Args:
            name:    Histogram name.
            value:   Observed value (in seconds).
            tags:    Labels.
            buckets: Custom bucket boundaries (optional).
        """
        tags = dict(tags) if tags else {}
        if not self._check_cardinality(name, tags):
            return

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
        self._histogram_buckets[name] = buckets

    # ─── Export ────────────────────────────────────────────────────────────────

    async def export_text(self) -> str:
        """Export all metrics in Prometheus text format."""
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
                    lines.append(f'{key}_bucket{{le="{bound}"}} {counts[i]}')
                lines.append(f'{key}_bucket{{le="+Inf"}} {counts[-1]}')
                lines.append(f"{key}_sum {total_sum}")
                lines.append(f"{key}_count {total_count}")

            return "\n".join(lines)

    async def get_counter(self, name: str, tags: dict[str, str] | None = None) -> int:
        tags = dict(tags) if tags else {}
        key = self._make_key(name, tags)
        async with self._lock:
            return self._counters.get(key, 0)

    async def clear(self) -> None:
        async with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._label_seen.clear()

    # ─── Diagnostics ──────────────────────────────────────────────────────────

    def get_cardinality_report(self) -> dict[str, Any]:
        """Return cardinality status for all registered limits."""
        report: dict[str, Any] = {
            "violations_total": self._cardinality_violations,
            "limits": {},
            "undeclared_warnings": len(self._undeclared_warned),
        }
        for key, limit in self._cardinality_limits.items():
            seen = self._label_seen.get(key, set())
            report["limits"][key] = {
                "limit": limit.max_distinct,
                "seen": len(seen),
                "pct": round(len(seen) / limit.max_distinct * 100, 1) if limit.max_distinct else 0,
                "action": limit.action.value,
                "description": limit.description,
            }
        return report

    async def get_stats(self) -> dict[str, Any]:
        """Return registry statistics including cardinality health."""
        async with self._lock:
            return {
                "counters": len(self._counters),
                "histograms": len(self._histograms),
                "cardinality_limits": len(self._cardinality_limits),
                "cardinality_violations": self._cardinality_violations,
                "label_series_tracked": sum(len(v) for v in self._label_seen.values()),
            }
