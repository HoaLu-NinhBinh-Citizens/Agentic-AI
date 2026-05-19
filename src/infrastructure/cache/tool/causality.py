"""Causality Tracer with anomaly detection.

Per-tool tracing and latency breakdown analysis.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolTrace:
    """Trace of a single tool execution."""

    tool_name: str
    timestamp: float
    cache_hit: bool
    latency_ms: float
    error_type: Optional[str] = None
    memory_state: Optional[dict[str, Any]] = None
    system_load: Optional[dict[str, float]] = None


@dataclass
class LatencyBreakdown:
    """Breakdown of request latency components."""

    cache_lookup_ms: float
    tool_execution_ms: float
    embedding_generation_ms: float
    serialization_ms: float
    total_ms: float


@dataclass
class ErrorBreakdown:
    """Breakdown of errors by type."""

    network_errors: int = 0
    timeout_errors: int = 0
    validation_errors: int = 0
    resource_errors: int = 0


@dataclass
class CausalityMetrics:
    """Aggregated causality metrics per tool."""

    tool_name: str
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_latency_ms: float = 0.0
    errors: ErrorBreakdown = field(default_factory=ErrorBreakdown)
    anomaly_detected: bool = False


@dataclass
class AnomalySignal:
    """Signal emitted when anomaly is detected."""

    type: str
    severity: float
    probable_cause: str
    affected_metrics: list[str]
    timestamp: float = field(default_factory=time.time)


@dataclass
class CausalityConfig:
    """Configuration for causality tracing."""

    correlation_window_seconds: float = 60.0
    baseline_window_size: int = 100
    zscore_threshold: float = 3.0
    sample_rate: float = 0.1
    analysis_interval_seconds: float = 10.0
    emit_alerts: bool = True


class CausalityTracer:
    """Per-tool causality tracing with anomaly detection.

    Features:
    - Per-tool trace collection
    - Latency breakdown analysis
    - Z-score based anomaly detection
    - Off-critical-path analysis

    Guarantees:
    - Minimal overhead on hot path
    - Background analysis only
    """

    def __init__(
        self,
        config: CausalityConfig | None = None,
    ) -> None:
        self.config = config or CausalityConfig()

        self._tool_traces: dict[str, deque[ToolTrace]] = {}
        self._metrics: dict[str, CausalityMetrics] = {}
        self._anomalies: list[AnomalySignal] = []

        self._baseline_windows: dict[str, list[float]] = {}
        self._analysis_buffer: list[ToolTrace] = []
        self._lock = asyncio.Lock()

        self._analysis_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the causality tracer."""
        if self._running:
            return

        self._running = True
        self._analysis_task = asyncio.create_task(self._analysis_loop())
        logger.info("Causality tracer started")

    async def stop(self) -> None:
        """Stop the causality tracer."""
        self._running = False
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
        logger.info("Causality tracer stopped")

    async def trace_execution(
        self,
        tool_name: str,
        cache_hit: bool,
        latency_ms: float,
        error: Optional[Exception] = None,
    ) -> ToolTrace:
        """Trace a tool execution (minimal overhead).

        Args:
            tool_name: Name of the tool
            cache_hit: Whether result was from cache
            latency_ms: Total latency in milliseconds
            error: Optional exception if execution failed

        Returns:
            ToolTrace object
        """
        trace = ToolTrace(
            tool_name=tool_name,
            timestamp=time.time(),
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            error_type=type(error).__name__ if error else None,
            memory_state=self._capture_memory_state(),
            system_load=self._capture_system_load(),
        )

        if tool_name not in self._tool_traces:
            self._tool_traces[tool_name] = deque(maxlen=int(self.config.correlation_window_seconds * 10))

        self._tool_traces[tool_name].append(trace)

        self._update_metrics(tool_name, trace)

        if self._should_sample():
            async with self._lock:
                self._analysis_buffer.append(trace)

        return trace

    def _should_sample(self) -> bool:
        """Check if this request should be sampled for analysis."""
        return self.config.sample_rate >= 1.0 or (
            self.config.sample_rate > 0 and
            (hash(time.time()) % 1000) < (self.config.sample_rate * 1000)
        )

    def _capture_memory_state(self) -> dict[str, Any]:
        """Capture current memory state (minimal overhead)."""
        try:
            import psutil
            process = psutil.Process()
            return {
                "rss_mb": process.memory_info().rss / (1024 * 1024),
            }
        except ImportError:
            return {}

    def _capture_system_load(self) -> dict[str, float]:
        """Capture system load (minimal overhead)."""
        try:
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(),
                "load_avg": psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else 0.0,
            }
        except ImportError:
            return {}

    def _update_metrics(self, tool_name: str, trace: ToolTrace) -> None:
        """Update aggregated metrics."""
        if tool_name not in self._metrics:
            self._metrics[tool_name] = CausalityMetrics(tool_name=tool_name)

        metrics = self._metrics[tool_name]
        metrics.total_requests += 1
        metrics.total_latency_ms += trace.latency_ms

        if trace.cache_hit:
            metrics.cache_hits += 1
        else:
            metrics.cache_misses += 1

        if trace.error_type:
            if "timeout" in trace.error_type.lower():
                metrics.errors.timeout_errors += 1
            elif "network" in trace.error_type.lower():
                metrics.errors.network_errors += 1
            elif "validation" in trace.error_type.lower():
                metrics.errors.validation_errors += 1
            else:
                metrics.errors.resource_errors += 1

    async def analyze_latency(
        self,
        request_start: float,
        request_end: float,
        cache_lookup_time: float,
        embedding_time: float,
        tool_execution_time: float,
    ) -> LatencyBreakdown:
        """Analyze latency breakdown.

        Args:
            request_start: Start time of request
            request_end: End time of request
            cache_lookup_time: Time spent in cache lookup
            embedding_time: Time spent generating embeddings
            tool_execution_time: Time spent executing tool

        Returns:
            LatencyBreakdown with component breakdown
        """
        total_time = request_end - request_start
        serialization_time = max(
            0,
            total_time - (cache_lookup_time + embedding_time + tool_execution_time)
        )

        return LatencyBreakdown(
            cache_lookup_ms=cache_lookup_time,
            tool_execution_ms=tool_execution_time,
            embedding_generation_ms=embedding_time,
            serialization_ms=serialization_time,
            total_ms=total_time,
        )

    def identify_bottleneck(self, breakdown: LatencyBreakdown) -> str:
        """Identify the latency bottleneck.

        Args:
            breakdown: Latency breakdown to analyze

        Returns:
            Name of the bottleneck component
        """
        components = {
            "cache_lookup": breakdown.cache_lookup_ms,
            "embedding_generation": breakdown.embedding_generation_ms,
            "tool_execution": breakdown.tool_execution_ms,
            "serialization": breakdown.serialization_ms,
        }
        return max(components, key=components.get)

    async def _analysis_loop(self) -> None:
        """Background loop for causality analysis."""
        while self._running:
            try:
                await asyncio.sleep(self.config.analysis_interval_seconds)

                async with self._lock:
                    metrics = list(self._analysis_buffer)
                    self._analysis_buffer.clear()

                if metrics:
                    anomalies = await self._detect_anomalies(metrics)
                    for anomaly in anomalies:
                        self._anomalies.append(anomaly)
                        if self.config.emit_alerts:
                            await self._emit_alert(anomaly)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Causality analysis error: {e}")

    async def _detect_anomalies(self, traces: list[ToolTrace]) -> list[AnomalySignal]:
        """Detect anomalies using Z-score analysis."""
        anomalies = []

        if not traces:
            return anomalies

        tool_traces = {}
        for trace in traces:
            tool_traces.setdefault(trace.tool_name, []).append(trace)

        for tool_name, tool_traces_list in tool_traces.items():
            for metric_name, value_fn in [
                ("hit_rate", lambda: sum(1 for t in tool_traces_list if t.cache_hit) / len(tool_traces_list)),
                ("latency", lambda: sum(t.latency_ms for t in tool_traces_list) / len(tool_traces_list)),
            ]:
                current_value = value_fn()

                if tool_name not in self._baseline_windows:
                    self._baseline_windows[tool_name] = []

                window = self._baseline_windows[tool_name]
                window.append(current_value)

                if len(window) >= self.config.baseline_window_size:
                    window.pop(0)

                if len(window) >= 10:
                    mean = statistics.mean(window[:-1])
                    stdev = statistics.stdev(window[:-1]) if len(window) > 1 else 0

                    if stdev > 0:
                        zscore = (current_value - mean) / stdev

                        if abs(zscore) > self.config.zscore_threshold:
                            anomalies.append(AnomalySignal(
                                type=f"{metric_name}_anomaly",
                                severity=min(1.0, abs(zscore) / 5.0),
                                probable_cause=self._infer_cause(metric_name, zscore),
                                affected_metrics=[metric_name],
                            ))

        return anomalies

    def _infer_cause(self, metric_name: str, zscore: float) -> str:
        """Infer probable cause of anomaly."""
        causes = {
            "hit_rate": "cache_pollution or TTL misconfiguration",
            "miss_count": "cold_start or cache_invalidation_storm",
            "latency": "memory_pressure or embedding_service_slowdown",
        }
        return causes.get(metric_name, "unknown_cause")

    async def _emit_alert(self, anomaly: AnomalySignal) -> None:
        """Emit anomaly alert."""
        logger.warning(
            f"Anomaly detected: type={anomaly.type}, "
            f"severity={anomaly.severity:.2f}, "
            f"cause={anomaly.probable_cause}"
        )

    def get_metrics(self, tool_name: str) -> Optional[CausalityMetrics]:
        """Get metrics for a specific tool."""
        return self._metrics.get(tool_name)

    def get_all_metrics(self) -> dict[str, CausalityMetrics]:
        """Get metrics for all tools."""
        return self._metrics.copy()

    def get_anomalies(self) -> list[AnomalySignal]:
        """Get recent anomaly signals."""
        return self._anomalies.copy()

    def get_hit_rate(self, tool_name: str) -> float:
        """Calculate hit rate for a tool."""
        if tool_name not in self._tool_traces:
            return 0.0

        traces = list(self._tool_traces[tool_name])
        if not traces:
            return 0.0

        return sum(1 for t in traces if t.cache_hit) / len(traces)

    def get_average_latency(self, tool_name: str) -> float:
        """Calculate average latency for a tool."""
        if tool_name not in self._metrics:
            return 0.0

        metrics = self._metrics[tool_name]
        if metrics.total_requests == 0:
            return 0.0

        return metrics.total_latency_ms / metrics.total_requests


class AnomalyDetector:
    """Standalone anomaly detector for external use."""

    def __init__(
        self,
        window_size: int = 100,
        zscore_threshold: float = 3.0,
    ) -> None:
        self.window_size = window_size
        self.zscore_threshold = zscore_threshold
        self._baseline_windows: dict[str, list[float]] = {}

    def detect(
        self,
        metric_name: str,
        current_value: float,
    ) -> Optional[AnomalySignal]:
        """Detect anomaly for a metric.

        Args:
            metric_name: Name of the metric
            current_value: Current metric value

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        if metric_name not in self._baseline_windows:
            self._baseline_windows[metric_name] = []

        window = self._baseline_windows[metric_name]
        window.append(current_value)

        if len(window) > self.window_size:
            window.pop(0)

        if len(window) >= 10:
            mean = statistics.mean(window[:-1])
            stdev = statistics.stdev(window[:-1]) if len(window) > 1 else 0

            if stdev > 0:
                zscore = (current_value - mean) / stdev

                if abs(zscore) > self.zscore_threshold:
                    return AnomalySignal(
                        type=f"{metric_name}_anomaly",
                        severity=min(1.0, abs(zscore) / 5.0),
                        probable_cause=f"{metric_name} deviation detected",
                        affected_metrics=[metric_name],
                    )

        return None

    def reset(self, metric_name: str | None = None) -> None:
        """Reset baseline windows."""
        if metric_name:
            self._baseline_windows.pop(metric_name, None)
        else:
            self._baseline_windows.clear()
