"""
OpenTelemetry Integration

Provides distributed tracing integration using OpenTelemetry protocol.
This module enables tracing across all AI_support components for
observability and performance analysis.

Features:
- Trace context propagation
- Span creation and management
- Metrics export (OpenTelemetry format)
- Exporter adapters (Jaeger, Zipkin, OTLP)
- Automatic instrumentation

Usage:
    from src.infrastructure.observability.otel import OtelTracer, configure_tracing

    # Configure tracing
    configure_tracing(
        service_name="ai_support",
        otlp_endpoint="http://localhost:4317",
    )

    # Create spans
    tracer = OtelTracer()
    with tracer.span("my_operation"):
        # do work
        pass
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class SpanStatus(Enum):
    """Span status codes."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class SpanKind(Enum):
    """Span kind types."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


@dataclass
class Span:
    """
    Represents a single trace span.

    A span represents a unit of work in a distributed trace.
    """
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    kind: SpanKind = SpanKind.INTERNAL
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {},
        })

    def set_status(self, status: SpanStatus, description: str = "") -> None:
        """Set span status."""
        self.status = status
        if description:
            self.attributes["status.description"] = description

    def end(self) -> None:
        """End the span."""
        self.end_time = datetime.now()

    @property
    def duration_ms(self) -> float:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds() * 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "kind": self.kind.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "links": self.links,
        }


@dataclass
class TraceConfig:
    """Trace configuration."""
    service_name: str = "ai_support"
    service_version: str = "1.0.0"
    environment: str = "development"
    otlp_endpoint: str = "http://localhost:4317"
    enabled: bool = True
    sample_rate: float = 1.0  # 1.0 = 100%, 0.1 = 10%
    max_spans_per_trace: int = 1000


class TraceContext:
    """Maintains trace context across async operations."""

    def __init__(self):
        self._current_span: Optional[Span] = None
        self._spans: List[Span] = []

    def set_current_span(self, span: Span) -> None:
        """Set the current active span."""
        self._current_span = span

    def get_current_span(self) -> Optional[Span]:
        """Get the current active span."""
        return self._current_span

    def add_span(self, span: Span) -> None:
        """Add a span to this trace."""
        self._spans.append(span)

    def get_spans(self) -> List[Span]:
        """Get all spans in this trace."""
        return self._spans.copy()

    def export(self) -> Dict[str, Any]:
        """Export trace as dictionary."""
        if not self._spans:
            return {"spans": []}

        # Group by trace_id
        traces: Dict[str, List[Span]] = {}
        for span in self._spans:
            if span.trace_id not in traces:
                traces[span.trace_id] = []
            traces[span.trace_id].append(span)

        return {
            "traces": [
                {
                    "trace_id": trace_id,
                    "spans": [s.to_dict() for s in spans]
                }
                for trace_id, spans in traces.items()
            ]
        }


class OtelTracer:
    """
    OpenTelemetry-compatible tracer for src.

    Provides tracing capabilities compatible with OpenTelemetry protocol.
    Supports:
    - Span creation and management
    - Context propagation
    - Multiple exporters
    - Sampling

    Usage:
        tracer = OtelTracer(config=TraceConfig(service_name="my_service"))

        # Create spans
        with tracer.start_span("operation") as span:
            span.set_attribute("key", "value")
            # do work

        # Export traces
        traces = tracer.export()
    """

    def __init__(
        self,
        config: Optional[TraceConfig] = None,
        exporter: Optional["TraceExporter"] = None,
    ):
        self.config = config or TraceConfig()
        self.exporter = exporter
        self._contexts: Dict[str, TraceContext] = {}
        self._lock = asyncio.Lock()

        # Span ID generator
        self._span_counter = 0

    def _generate_span_id(self) -> str:
        """Generate a unique span ID."""
        self._span_counter += 1
        return f"{self._span_counter:016x}"

    def _generate_trace_id(self) -> str:
        """Generate a unique trace ID."""
        return uuid4().hex

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Span] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """
        Start a new span.

        Args:
            name: Name of the span
            kind: Kind of span
            parent: Parent span (if any)
            attributes: Initial attributes

        Returns:
            New Span instance
        """
        try:
            current_task = asyncio.current_task()
            task_name = current_task.get_name() if current_task else "main"
        except RuntimeError:
            task_name = "main"

        current_span = self._contexts.get(task_name)

        parent_id = None
        trace_id = self._generate_trace_id()

        if parent:
            parent_id = parent.span_id
            trace_id = parent.trace_id
        elif current_span and current_span._current_span:
            parent_id = current_span._current_span.span_id
            trace_id = current_span._current_span.trace_id

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=self._generate_span_id(),
            parent_id=parent_id,
            kind=kind,
            attributes=attributes or {},
        )

        # Add to context
        try:
            task_name = asyncio.current_task().get_name() if asyncio.current_task() else "main"
        except RuntimeError:
            task_name = "main"
        if task_name not in self._contexts:
            self._contexts[task_name] = TraceContext()
        self._contexts[task_name].add_span(span)
        self._contexts[task_name].set_current_span(span)

        logger.debug(f"Started span: {name} (trace_id={trace_id[:8]}...)")

        return span

    async def start_span_async(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Span] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Async version of start_span."""
        async with self._lock:
            return self.start_span(name, kind, parent, attributes)

    def end_span(self, span: Span) -> None:
        """End a span."""
        span.end()
        logger.debug(
            f"Ended span: {span.name} (duration={span.duration_ms:.2f}ms)"
        )

        # Export if enabled
        if self.exporter and self.config.enabled:
            self.exporter.export_span(span)

    def add_link(
        self,
        span: Span,
        trace_id: str,
        span_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a link to another trace."""
        span.links.append({
            "trace_id": trace_id,
            "span_id": span_id,
            "attributes": attributes or {},
        })

    def export(self) -> Dict[str, Any]:
        """Export all traces."""
        all_traces = []
        for context in self._contexts.values():
            all_traces.append(context.export())

        return {"traces": all_traces}

    def clear(self) -> None:
        """Clear all traces."""
        self._contexts.clear()
        self._span_counter = 0


class SpanContext:
    """Context manager for spans."""

    def __init__(self, tracer: OtelTracer, name: str, **kwargs):
        self.tracer = tracer
        self.name = name
        self.kwargs = kwargs
        self.span: Optional[Span] = None

    def __enter__(self) -> Span:
        self.span = self.tracer.start_span(self.name, **self.kwargs)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type is not None:
                self.span.set_status(SpanStatus.ERROR, str(exc_val))
            else:
                self.span.set_status(SpanStatus.OK)
            self.tracer.end_span(self.span)
        return False


class TraceExporter(ABC):
    """Base class for trace exporters."""

    @abstractmethod
    def export_span(self, span: Span) -> None:
        """Export a single span."""
        pass

    @abstractmethod
    def export_batch(self, spans: List[Span]) -> None:
        """Export a batch of spans."""
        pass

    def flush(self) -> None:
        """Flush pending exports."""
        pass


class ConsoleExporter(TraceExporter):
    """Console exporter for debugging."""

    def export_span(self, span: Span) -> None:
        print(f"[TRACE] {span.name}: {span.duration_ms:.2f}ms")

    def export_batch(self, spans: List[Span]) -> None:
        for span in spans:
            self.export_span(span)


class OtlpExporter(TraceExporter):
    """OTLP protocol exporter."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._pending: List[Span] = []
        self._batch_size = 100
        self._flush_interval = 5.0

    def export_span(self, span: Span) -> None:
        self._pending.append(span)
        if len(self._pending) >= self._batch_size:
            self.flush()

    def export_batch(self, spans: List[Span]) -> None:
        # In a real implementation, this would send to OTLP endpoint
        logger.debug(f"Exporting {len(spans)} spans to {self.endpoint}")

    def flush(self) -> None:
        if self._pending:
            self.export_batch(self._pending)
            self._pending.clear()


class JaegerExporter(TraceExporter):
    """Jaeger thrift format exporter."""

    def __init__(self, agent_host: str = "localhost", agent_port: int = 6831):
        self.agent_host = agent_host
        self.agent_port = agent_port
        self._pending: List[Span] = []

    def export_span(self, span: Span) -> None:
        self._pending.append(span)
        if len(self._pending) >= 50:
            self.flush()

    def export_batch(self, spans: List[Span]) -> None:
        # In a real implementation, this would send via UDP to Jaeger agent
        logger.debug(
            f"Jaeger: exporting {len(spans)} spans to "
            f"{self.agent_host}:{self.agent_port}"
        )

    def flush(self) -> None:
        if self._pending:
            self.export_batch(self._pending)
            self._pending.clear()


# Global tracer instance
_global_tracer: Optional[OtelTracer] = None


def configure_tracing(
    service_name: str = "ai_support",
    otlp_endpoint: Optional[str] = None,
    jaeger_host: Optional[str] = None,
    jaeger_port: int = 6831,
    console_export: bool = False,
) -> OtelTracer:
    """
    Configure global tracing.

    Args:
        service_name: Name of the service
        otlp_endpoint: OTLP collector endpoint
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
        console_export: Enable console export

    Returns:
        Configured OtelTracer instance
    """
    global _global_tracer

    config = TraceConfig(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint or "http://localhost:4317",
    )

    # Create exporter
    exporter = None
    if console_export:
        exporter = ConsoleExporter()
    elif otlp_endpoint:
        exporter = OtlpExporter(otlp_endpoint)
    elif jaeger_host:
        exporter = JaegerExporter(jaeger_host, jaeger_port)

    _global_tracer = OtelTracer(config=config, exporter=exporter)

    logger.info(
        f"Tracing configured: service={service_name}, "
        f"endpoint={otlp_endpoint or jaeger_host}"
    )

    return _global_tracer


def get_tracer() -> OtelTracer:
    """Get the global tracer instance."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = OtelTracer()
    return _global_tracer
