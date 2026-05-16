"""
Metrics Collector

Collect and aggregate metrics for AI agents.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import statistics

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Metrics collection and aggregation.

    Features:
    - Counter, gauge, histogram metrics
    - Time-series storage
    - Aggregation (avg, min, max, p95, p99)
    - Export to various formats

    Usage:
        collector = MetricsCollector()

        # Record metrics
        collector.increment("requests_total")
        collector.gauge("memory_usage_mb", 512.5)
        collector.histogram("request_duration_ms", 150)

        # Get aggregated metrics
        stats = collector.get_stats("request_duration_ms")
    """

    def __init__(
        self,
        retention_period: timedelta = timedelta(hours=24),
        flush_interval: timedelta = timedelta(minutes=5),
    ):
        """
        Initialize metrics collector.

        Args:
            retention_period: How long to retain metrics
            flush_interval: Interval to flush/summarize metrics
        """
        self.retention_period = retention_period
        self.flush_interval = flush_interval

        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._time_series: Dict[str, List[MetricPoint]] = defaultdict(list)
        self._metrics_history: Dict[str, List[Dict]] = defaultdict(list)
        self._exporters: List[Callable] = []

    def increment(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Value to add
            tags: Optional tags
        """
        self._counters[name] += value
        self._record_point(name, value, tags)

    def decrement(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Decrement a counter."""
        self.increment(name, -value, tags)

    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Set a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            tags: Optional tags
        """
        self._gauges[name] = value
        self._record_point(name, value, tags)

    def histogram(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a histogram value.

        Args:
            name: Metric name
            value: Histogram value
            tags: Optional tags
        """
        self._histograms[name].append(value)
        self._record_point(name, value, tags)

    def timing(
        self,
        name: str,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record timing metric (histogram with _ms suffix).

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            tags: Optional tags
        """
        self.histogram(f"{name}_ms", duration_ms, tags)

    def _record_point(self, name: str, value: float, tags: Optional[Dict[str, str]]) -> None:
        """Record a metric point."""
        point = MetricPoint(name=name, value=value, tags=tags or {})
        self._time_series[name].append(point)

        # Prune old points
        cutoff = datetime.now() - self.retention_period
        self._time_series[name] = [
            p for p in self._time_series[name] if p.timestamp > cutoff
        ]

    def get_counter(self, name: str) -> float:
        """Get counter value."""
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get gauge value."""
        return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics."""
        values = self._histograms.get(name, [])

        if not values:
            return {}

        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "count": n,
            "sum": sum(values),
            "mean": statistics.mean(values),
            "median": statistics.median(sorted_values),
            "min": min(values),
            "max": max(values),
            "p50": sorted_values[int(n * 0.5)],
            "p75": sorted_values[int(n * 0.75)],
            "p90": sorted_values[int(n * 0.9)],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)] if n >= 100 else sorted_values[-1],
        }

    def get_stats(self, name: str) -> Dict[str, Any]:
        """Get all stats for a metric."""
        return {
            "counter": self.get_counter(name),
            "gauge": self.get_gauge(name),
            "histogram": self.get_histogram_stats(name),
        }

    def get_all_metrics(self) -> Dict[str, Dict]:
        """Get all metrics."""
        metrics = {}

        # Add counters
        for name, value in self._counters.items():
            metrics[name] = {"type": "counter", "value": value}

        # Add gauges
        for name, value in self._gauges.items():
            metrics[name] = {"type": "gauge", "value": value}

        # Add histograms
        for name, values in self._histograms.items():
            metrics[name] = {"type": "histogram", **self.get_histogram_stats(name)}

        return metrics

    def get_time_series(
        self,
        name: str,
        window: Optional[timedelta] = None,
    ) -> List[MetricPoint]:
        """Get time series for a metric."""
        points = self._time_series.get(name, [])

        if window:
            cutoff = datetime.now() - window
            points = [p for p in points if p.timestamp > cutoff]

        return points

    def register_exporter(self, exporter: Callable[[Dict], None]) -> None:
        """Register an exporter callback."""
        self._exporters.append(exporter)

    def export(self) -> None:
        """Export all metrics to registered exporters."""
        metrics = self.get_all_metrics()

        for exporter in self._exporters:
            try:
                exporter(metrics)
            except Exception as e:
                logger.error(f"Metrics export failed: {e}")

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._time_series.clear()
        self._metrics_history.clear()

    def reset_metric(self, name: str) -> None:
        """Reset a specific metric."""
        self._counters.pop(name, None)
        self._gauges.pop(name, None)
        self._histograms.pop(name, None)
        self._time_series.pop(name, None)


# Convenience decorators
def timed(metric_name: str = None):
    """
    Decorator to automatically record timing metrics.

    Usage:
        @timed("my_function_duration")
        async def my_function():
            ...
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            collector = kwargs.pop("_metrics_collector", None)
            name = metric_name or f"{func.__name__}_duration"

            import time
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start) * 1000
                if collector:
                    collector.timing(name, duration_ms)

        def sync_wrapper(*args, **kwargs):
            collector = kwargs.pop("_metrics_collector", None)
            name = metric_name or f"{func.__name__}_duration"

            import time
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start) * 1000
                if collector:
                    collector.timing(name, duration_ms)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Global collector instance
_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
