"""
Prometheus Metrics Export

Provides:
- Counter, Gauge, Histogram, Summary metrics
- Prometheus exposition format
- HTTP server for /metrics endpoint
- Push gateway support
- Custom collectors
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import threading
import logging

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


@dataclass
class MetricLabel:
    """Metric label."""
    name: str
    value: str


@dataclass
class MetricSample:
    """Single metric sample."""
    name: str
    labels: List[MetricLabel]
    value: float
    timestamp: Optional[datetime] = None
    metric_type: MetricType = MetricType.UNKNOWN


@dataclass
class Metric:
    """Base metric container."""
    name: str
    description: str
    metric_type: MetricType
    labels: Tuple[str, ...] = field(default_factory=tuple)
    samples: List[MetricSample] = field(default_factory=list)
    buckets: Optional[List[float]] = None  # For histogram
    created_at: datetime = field(default_factory=datetime.now)


class Counter:
    """Prometheus Counter metric."""

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
    ):
        self._name = name
        self._description = description
        self._labels = labels or ()
        self._values: Dict[Tuple, float] = defaultdict(float)
        self._total: float = 0.0

    def inc(self, amount: float = 1, **label_values) -> None:
        """Increment counter."""
        label_tuple = self._make_label_tuple(label_values)
        self._values[label_tuple] += amount
        self._total += amount

    def get(self, **label_values) -> float:
        """Get current counter value."""
        label_tuple = self._make_label_tuple(label_values)
        return self._values[label_tuple]

    def _make_label_tuple(self, label_values: Dict[str, str]) -> Tuple:
        """Create sorted label tuple from dict."""
        if self._labels:
            return tuple(label_values.get(k, "") for k in self._labels)
        return ()

    def collect(self) -> Metric:
        """Collect metric for export."""
        metric = Metric(
            name=self._name,
            description=self._description,
            metric_type=MetricType.COUNTER,
            labels=self._labels,
        )

        for label_tuple, value in self._values.items():
            labels = [
                MetricLabel(name=k, value=v)
                for k, v in zip(self._labels, label_tuple) if v
            ]
            metric.samples.append(MetricSample(
                name=self._name,
                labels=labels,
                value=value,
                metric_type=MetricType.COUNTER,
            ))

        return metric


class Gauge:
    """Prometheus Gauge metric."""

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
    ):
        self._name = name
        self._description = description
        self._labels = labels or ()
        self._values: Dict[Tuple, float] = {}

    def set(self, value: float, **label_values) -> None:
        """Set gauge value."""
        label_tuple = self._make_label_tuple(label_values)
        self._values[label_tuple] = value

    def inc(self, amount: float = 1, **label_values) -> None:
        """Increment gauge."""
        label_tuple = self._make_label_tuple(label_values)
        self._values[label_tuple] = self._values.get(label_tuple, 0) + amount

    def dec(self, amount: float = 1, **label_values) -> None:
        """Decrement gauge."""
        label_tuple = self._make_label_tuple(label_values)
        self._values[label_tuple] = self._values.get(label_tuple, 0) - amount

    def get(self, **label_values) -> float:
        """Get current gauge value."""
        label_tuple = self._make_label_tuple(label_values)
        return self._values.get(label_tuple, 0.0)

    def _make_label_tuple(self, label_values: Dict[str, str]) -> Tuple:
        if self._labels:
            return tuple(label_values.get(k, "") for k in self._labels)
        return ()

    def collect(self) -> Metric:
        """Collect metric for export."""
        metric = Metric(
            name=self._name,
            description=self._description,
            metric_type=MetricType.GAUGE,
            labels=self._labels,
        )

        for label_tuple, value in self._values.items():
            labels = [
                MetricLabel(name=k, value=v)
                for k, v in zip(self._labels, label_tuple) if v
            ]
            metric.samples.append(MetricSample(
                name=self._name,
                labels=labels,
                value=value,
                metric_type=MetricType.GAUGE,
            ))

        return metric


class Histogram:
    """Prometheus Histogram metric."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
        buckets: Optional[List[float]] = None,
    ):
        self._name = name
        self._description = description
        self._labels = labels or ()
        self._buckets = buckets or list(self.DEFAULT_BUCKETS)
        self._values: Dict[Tuple, Dict[str, float]] = defaultdict(
            lambda: {"sum": 0, "count": 0, **{f"le_{b}": 0 for b in self._buckets}}
        )

    def observe(self, value: float, **label_values) -> None:
        """Observe a value."""
        label_tuple = self._make_label_tuple(label_values)
        data = self._values[label_tuple]

        data["sum"] += value
        data["count"] += 1

        for bucket in self._buckets:
            if value <= bucket:
                data[f"le_{bucket}"] += 1

    def _make_label_tuple(self, label_values: Dict[str, str]) -> Tuple:
        if self._labels:
            return tuple(label_values.get(k, "") for k in self._labels)
        return ()

    def collect(self) -> List[Metric]:
        """Collect histogram metrics."""
        metrics = []

        # Main histogram metric
        metric = Metric(
            name=self._name,
            description=self._description,
            metric_type=MetricType.HISTOGRAM,
            labels=self._labels,
            buckets=self._buckets,
        )

        for label_tuple, data in self._values.items():
            labels = [
                MetricLabel(name=k, value=v)
                for k, v in zip(self._labels, label_tuple) if v
            ]

            # Bucket samples
            for bucket in self._buckets:
                metric.samples.append(MetricSample(
                    name=f"{self._name}_bucket",
                    labels=labels + [MetricLabel(name="le", value=str(bucket))],
                    value=data[f"le_{bucket}"],
                    metric_type=MetricType.HISTOGRAM,
                ))

            # +Inf bucket (always equals count)
            metric.samples.append(MetricSample(
                name=f"{self._name}_bucket",
                labels=labels + [MetricLabel(name="le", value="+Inf")],
                value=data["count"],
                metric_type=MetricType.HISTOGRAM,
            ))

            # Sum and count
            metric.samples.append(MetricSample(
                name=f"{self._name}_sum",
                labels=labels,
                value=data["sum"],
                metric_type=MetricType.HISTOGRAM,
            ))
            metric.samples.append(MetricSample(
                name=f"{self._name}_count",
                labels=labels,
                value=data["count"],
                metric_type=MetricType.HISTOGRAM,
            ))

        metrics.append(metric)
        return metrics


class MetricsCollector:
    """
    Prometheus metrics collector.

    Features:
    - Counter, Gauge, Histogram, Summary
    - Automatic registration
    - Prometheus exposition format export
    - HTTP endpoint support
    """

    def __init__(self, namespace: str = "ai_support"):
        self.namespace = namespace
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
        self._custom_collectors: List[Callable[[], List[Metric]]] = []

    def _full_name(self, name: str) -> str:
        """Get full metric name with namespace."""
        if self.namespace:
            return f"{self.namespace}_{name}"
        return name

    def counter(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
    ) -> Counter:
        """
        Register or get a counter metric.

        Args:
            name: Metric name (without namespace)
            description: Help text
            labels: Label names

        Returns:
            Counter instance
        """
        full_name = self._full_name(name)

        with self._lock:
            if full_name not in self._counters:
                self._counters[full_name] = Counter(full_name, description, labels)
            return self._counters[full_name]

    def gauge(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
    ) -> Gauge:
        """Register or get a gauge metric."""
        full_name = self._full_name(name)

        with self._lock:
            if full_name not in self._gauges:
                self._gauges[full_name] = Gauge(full_name, description, labels)
            return self._gauges[full_name]

    def histogram(
        self,
        name: str,
        description: str,
        labels: Optional[Tuple[str, ...]] = None,
        buckets: Optional[List[float]] = None,
    ) -> Histogram:
        """Register or get a histogram metric."""
        full_name = self._full_name(name)

        with self._lock:
            if full_name not in self._histograms:
                self._histograms[full_name] = Histogram(full_name, description, labels, buckets)
            return self._histograms[full_name]

    def register_collector(self, collector: Callable[[], List[Metric]]) -> None:
        """Register a custom collector."""
        self._custom_collectors.append(collector)

    def collect(self) -> List[Metric]:
        """Collect all metrics."""
        metrics = []

        with self._lock:
            for counter in self._counters.values():
                metrics.append(counter.collect())

            for gauge in self._gauges.values():
                metrics.append(gauge.collect())

            for histogram in self._histograms.values():
                metrics.extend(histogram.collect())

        for collector in self._custom_collectors:
            try:
                metrics.extend(collector())
            except Exception as exc:
                logger.error("Custom collector error: %s", exc)

        return metrics

    def to_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus text exposition format.

        Returns:
            Metrics in Prometheus format
        """
        output = []
        metrics = self.collect()

        for metric in metrics:
            # Help and type
            output.append(f"# HELP {metric.name} {metric.description}")
            output.append(f"# TYPE {metric.name} {metric.metric_type.value}")

            for sample in metric.samples:
                label_str = ""
                if sample.labels:
                    label_parts = [f'{l.name}="{l.value}"' for l in sample.labels]
                    label_str = "{" + ",".join(label_parts) + "}"

                output.append(f"{sample.name}{label_str} {sample.value}")

            output.append("")  # Blank line between metrics

        return "\n".join(output)

    def to_json(self) -> List[Dict[str, Any]]:
        """Export metrics as JSON."""
        metrics = self.collect()
        result = []

        for metric in metrics:
            metric_dict = {
                "name": metric.name,
                "description": metric.description,
                "type": metric.metric_type.value,
                "samples": [],
            }

            for sample in metric.samples:
                sample_dict = {"value": sample.value}
                if sample.labels:
                    sample_dict["labels"] = {l.name: l.value for l in sample.labels}
                metric_dict["samples"].append(sample_dict)

            result.append(metric_dict)

        return result


class Timer:
    """Context manager for timing operations."""

    def __init__(self, histogram: Histogram, **label_values):
        self.histogram = histogram
        self.label_values = label_values
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        duration = time.perf_counter() - self.start_time
        self.histogram.observe(duration, **self.label_values)


# Global metrics collector
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
