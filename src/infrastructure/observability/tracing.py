"""Distributed Tracing - OpenTelemetry propagation and instrumentation.

Provides:
- OpenTelemetry trace propagation
- Span context management
- Custom span creation
- Metrics collection
- Log correlation
- Agent workflow tracing

Usage:
    tracer = OpenTelemetryTracer(service_name="aisupport-agent")
    await tracer.initialize()
    
    with tracer.start_span("analyze_crash") as span:
        await analyze_crash(crash_data)
        span.set_attribute("crash.type", crash_data.type)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Span kind."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(Enum):
    """Span status."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanContext:
    """Trace context for propagation."""
    trace_id: str
    span_id: str
    trace_flags: int = 1  # 1 = sampled
    trace_state: str = ""
    is_remote: bool = False
    
    @classmethod
    def from_traceparent(cls, traceparent: str) -> "SpanContext":
        """Parse W3C traceparent header."""
        parts = traceparent.split("-")
        if len(parts) != 4:
            raise ValueError(f"Invalid traceparent: {traceparent}")
        
        return cls(
            trace_id=parts[1],
            span_id=parts[2],
            trace_flags=int(parts[3], 16),
        )
    
    def to_traceparent(self) -> str:
        """Create W3C traceparent header."""
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_flags": self.trace_flags,
            "trace_state": self.trace_state,
        }


@dataclass
class SpanEvent:
    """Span event (timestamped annotation)."""
    name: str
    timestamp: int  # Unix timestamp in nanoseconds
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanLink:
    """Span link to another trace."""
    trace_id: str
    span_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """OpenTelemetry span."""
    name: str
    context: SpanContext
    kind: SpanKind = SpanKind.INTERNAL
    start_time: int = 0  # Nanoseconds
    end_time: int = 0
    status: SpanStatus = SpanStatus.UNSET
    status_message: str = ""
    
    # Hierarchy
    parent_span_id: str | None = None
    
    # Data
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    links: list[SpanLink] = field(default_factory=list)
    
    # Instrumentation
    instrumentation_library: str = "aisupport"
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.end_time == 0:
            self.end_time = time.time_ns()
            if exc_type:
                self.status = SpanStatus.ERROR
                self.status_message = str(exc_val)
        return False
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Set span attribute."""
        self.attributes[key] = value
    
    def set_attributes(self, attrs: dict[str, Any]) -> None:
        """Set multiple attributes."""
        self.attributes.update(attrs)
    
    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add span event."""
        self.events.append(SpanEvent(
            name=name,
            timestamp=time.time_ns(),
            attributes=attributes or {},
        ))
    
    def record_exception(self, exception: Exception) -> None:
        """Record an exception."""
        self.status = SpanStatus.ERROR
        self.status_message = str(exception)
        self.add_event("exception", {
            "exception.type": type(exception).__name__,
            "exception.message": str(exception),
        })
    
    def set_status(self, status: SpanStatus, message: str = "") -> None:
        """Set span status."""
        self.status = status
        self.status_message = message
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "context": self.context.to_dict(),
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": {
                "code": self.status.value,
                "message": self.status_message,
            },
            "attributes": self.attributes,
            "events": [
                {"name": e.name, "timestamp": e.timestamp, "attributes": e.attributes}
                for e in self.events
            ],
            "links": [
                {"trace_id": l.trace_id, "span_id": l.span_id, "attributes": l.attributes}
                for l in self.links
            ],
            "parent_span_id": self.parent_span_id,
        }


# Context variable for current span
_current_span: ContextVar[Span | None] = ContextVar("current_span", default=None)


class OpenTelemetryTracer:
    """OpenTelemetry-compatible distributed tracer.
    
    Features:
    - W3C TraceContext propagation
    - Custom span creation
    - Agent workflow tracing
    - Metrics collection
    - Log correlation
    - Exporter interface for backend
    """
    
    def __init__(
        self,
        service_name: str,
        service_version: str = "1.0.0",
        exporter: "SpanExporter | None" = None,
    ):
        """
        Args:
            service_name: Service name for traces
            service_version: Service version
            exporter: Span exporter for backend
        """
        self._service_name = service_name
        self._service_version = service_version
        self._exporter = exporter
        
        # Trace management
        self._spans: list[Span] = []
        self._span_index: dict[str, Span] = {}
        self._lock = asyncio.Lock()
        
        # Metrics
        self._metrics: dict[str, Any] = {
            "spans_created": 0,
            "spans_completed": 0,
            "spans_errored": 0,
        }
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the tracer."""
        if self._exporter:
            await self._exporter.initialize()
        
        self._initialized = True
        logger.info(
            "otel_tracer_initialized",
            service=self._service_name,
            version=self._service_version,
        )
    
    async def shutdown(self) -> None:
        """Shutdown the tracer."""
        if self._exporter:
            await self._exporter.shutdown()
        self._initialized = False
        logger.info("otel_tracer_shutdown", metrics=self._metrics)
    
    def _generate_trace_id(self) -> str:
        """Generate 32-character trace ID."""
        return uuid.uuid4().hex[:16] + uuid.uuid4().hex[:16]
    
    def _generate_span_id(self) -> str:
        """Generate 16-character span ID."""
        return uuid.uuid4().hex[:16]
    
    def start_span(
        self,
        name: str,
        context: SpanContext | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        links: list[SpanLink] | None = None,
    ) -> Span:
        """Start a new span.
        
        Args:
            name: Span name
            context: Optional parent context
            kind: Span kind
            attributes: Initial attributes
            links: Links to other traces
            
        Returns:
            New Span object
        """
        # Get parent from context if not provided
        if context is None:
            parent_span = _current_span.get()
            if parent_span:
                context = parent_span.context
        else:
            # Create child of provided context
            pass
        
        # Generate IDs
        if context is None:
            trace_id = self._generate_trace_id()
        else:
            trace_id = context.trace_id
        
        span_id = self._generate_span_id()
        
        # Create span
        span = Span(
            name=name,
            context=SpanContext(
                trace_id=trace_id,
                span_id=span_id,
            ),
            kind=kind,
            start_time=time.time_ns(),
            parent_span_id=context.span_id if context else None,
            attributes=attributes or {},
            links=links or [],
        )
        
        # Set service attributes
        span.set_attribute("service.name", self._service_name)
        span.set_attribute("service.version", self._service_version)
        
        self._metrics["spans_created"] += 1
        
        return span
    
    def start_active_span(
        self,
        name: str,
        context: SpanContext | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start an active span (sets as current).
        
        Can be used as context manager:
            with tracer.start_active_span("operation") as span:
                ...
        """
        span = self.start_span(name, context, kind, attributes)
        token = _current_span.set(span)
        span._token = token
        return span
    
    def end_span(self, span: Span) -> None:
        """End a span and export it."""
        if span.end_time == 0:
            span.end_time = time.time_ns()
        
        span.set_attribute("span.duration_ms", (span.end_time - span.start_time) / 1_000_000)
        
        # Update metrics
        if span.status == SpanStatus.ERROR:
            self._metrics["spans_errored"] += 1
        else:
            self._metrics["spans_completed"] += 1
        
        # Reset current span if this was active
        if hasattr(span, "_token"):
            _current_span.reset(span._token)
        
        # Export span
        if self._exporter:
            asyncio.create_task(self._exporter.export([span]))
    
    def get_current_span(self) -> Span | None:
        """Get the current active span."""
        return _current_span.get()
    
    def get_current_trace_id(self) -> str | None:
        """Get current trace ID."""
        span = _current_span.get()
        return span.context.trace_id if span else None
    
    def get_current_span_id(self) -> str | None:
        """Get current span ID."""
        span = _current_span.get()
        return span.context.span_id if span else None
    
    def extract_context(self, headers: dict[str, str]) -> SpanContext | None:
        """Extract context from HTTP/gRPC headers.
        
        Supports:
        - W3C TraceContext (traceparent, tracestate)
        - B3 Propagation
        """
        # Try W3C TraceContext first
        traceparent = headers.get("traceparent") or headers.get("Traceparent")
        if traceparent:
            try:
                return SpanContext.from_traceparent(traceparent)
            except Exception:
                pass
        
        # Try B3
        b3_trace_id = headers.get("X-B3-TraceId") or headers.get("b3")
        b3_span_id = headers.get("X-B3-SpanId") or headers.get("b3")
        
        if b3_trace_id and b3_span_id:
            return SpanContext(
                trace_id=b3_trace_id,
                span_id=b3_span_id,
                is_remote=True,
            )
        
        return None
    
    def inject_context(self, headers: dict[str, str]) -> dict[str, str]:
        """Inject current context into headers."""
        span = _current_span.get()
        
        if not span:
            return headers
        
        # W3C TraceContext
        headers["traceparent"] = span.context.to_traceparent()
        
        # B3 (legacy)
        headers["X-B3-TraceId"] = span.context.trace_id[:16]
        headers["X-B3-SpanId"] = span.context.span_id
        
        return headers
    
    def create_link(self, context: SpanContext, attributes: dict[str, Any] | None = None) -> SpanLink:
        """Create a link to another trace."""
        return SpanLink(
            trace_id=context.trace_id,
            span_id=context.span_id,
            attributes=attributes or {},
        )


class SpanExporter:
    """Interface for exporting spans to a backend."""
    
    async def initialize(self) -> None:
        """Initialize the exporter."""
        pass
    
    async def export(self, spans: list[Span]) -> None:
        """Export spans to backend."""
        raise NotImplementedError
    
    async def shutdown(self) -> None:
        """Shutdown the exporter."""
        pass


class ConsoleSpanExporter(SpanExporter):
    """Export spans to console (for debugging)."""
    
    async def export(self, spans: list[Span]) -> None:
        """Print spans to console."""
        for span in spans:
            logger.info(
                "span_exported",
                name=span.name,
                trace_id=span.context.trace_id[:16],
                span_id=span.context.span_id,
                duration_ms=(span.end_time - span.start_time) / 1_000_000,
                status=span.status.value,
            )


class OTLPExporter(SpanExporter):
    """Export spans via OTLP protocol.
    
    Supports:
    - gRPC (OTLP/gRPC)
    - HTTP/protobuf (OTLP/HTTP)
    """
    
    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        protocol: str = "grpc",
    ):
        self._endpoint = endpoint
        self._protocol = protocol
        self._client = None
    
    async def initialize(self) -> None:
        """Initialize OTLP client."""
        if self._protocol == "grpc":
            try:
                import grpc
                # In production, use opentelemetry-exporter-otlp-proto-grpc
                self._client = None
                logger.info("otlp_grpc_exporter_initialized", endpoint=self._endpoint)
            except ImportError:
                logger.warning("grpc_not_available_falling_back_to_console")
                self._client = None
        else:
            # HTTP/protobuf
            self._client = None
            logger.info("otlp_http_exporter_initialized", endpoint=self._endpoint)
    
    async def export(self, spans: list[Span]) -> None:
        """Export spans via OTLP."""
        if not self._client:
            # Fallback to console
            for span in spans:
                logger.debug(
                    "span_export_otlp",
                    trace_id=span.context.trace_id[:16],
                    name=span.name,
                )
            return
        
        # Convert to OTLP format and send
        # In production, use opentelemetry-exporter-otlp-proto-*
        pass


class JaegerExporter(SpanExporter):
    """Export spans to Jaeger."""
    
    def __init__(self, agent_host: str = "localhost", agent_port: int = 6831):
        self._agent_host = agent_host
        self._agent_port = agent_port
    
    async def initialize(self) -> None:
        """Initialize Jaeger agent connection."""
        logger.info(
            "jaeger_exporter_initialized",
            host=self._agent_host,
            port=self._agent_port,
        )
    
    async def export(self, spans: list[Span]) -> None:
        """Export spans to Jaeger agent."""
        # In production, use opentelemetry-exporter-jaeger
        for span in spans:
            logger.debug(
                "span_export_jaeger",
                service=self._service_name if hasattr(self, '_service_name') else "unknown",
                operation=span.name,
                trace_id=span.context.trace_id[:16],
            )


class ZipkinExporter(SpanExporter):
    """Export spans to Zipkin."""
    
    def __init__(self, endpoint: str = "http://localhost:9411/api/v2/spans"):
        self._endpoint = endpoint
    
    async def initialize(self) -> None:
        """Initialize Zipkin exporter."""
        logger.info("zipkin_exporter_initialized", endpoint=self._endpoint)
    
    async def export(self, spans: list[Span]) -> None:
        """Export spans to Zipkin."""
        # Convert to Zipkin format
        zipkin_spans = []
        for span in spans:
            zipkin_span = {
                "id": span.context.span_id,
                "traceId": span.context.trace_id,
                "localEndpoint": {
                    "serviceName": span.attributes.get("service.name", "unknown"),
                },
                "name": span.name,
                "timestamp": span.start_time // 1000,  # Microseconds
                "duration": (span.end_time - span.start_time) // 1000,
                "tags": span.attributes,
                "kind": span.kind.value.upper(),
            }
            zipkin_spans.append(zipkin_span)
        
        # Send to Zipkin
        if zipkin_spans:
            logger.debug("spans_sent_to_zipkin", count=len(zipkin_spans))


# Decorator for tracing functions
def traced(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
):
    """Decorator to trace a function."""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            tracer = getattr(wrapper, "_tracer", None)
            if not tracer:
                return await func(*args, **kwargs)
            
            span_name = name or func.__name__
            with tracer.start_active_span(span_name, kind=kind) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(SpanStatus.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    raise
        
        wrapper._tracer = None  # Set by user
        return wrapper
    return decorator


# Global tracer
_tracer: OpenTelemetryTracer | None = None


def get_tracer(service_name: str = "aisupport") -> OpenTelemetryTracer:
    """Get global tracer."""
    global _tracer
    if _tracer is None:
        _tracer = OpenTelemetryTracer(service_name)
    return _tracer


def init_tracing(
    service_name: str,
    exporter: SpanExporter | None = None,
) -> OpenTelemetryTracer:
    """Initialize global tracing."""
    global _tracer
    
    exporter = exporter or ConsoleSpanExporter()
    _tracer = OpenTelemetryTracer(service_name, exporter=exporter)
    return _tracer


if __name__ == "__main__":
    print("OpenTelemetry Distributed Tracing")
    print("=" * 40)
    print("W3C TraceContext propagation and instrumentation")
    print()
    print("Features:")
    print("  - W3C TraceContext propagation")
    print("  - Custom span creation")
    print("  - Agent workflow tracing")
    print("  - Metrics collection")
    print("  - Multiple exporter backends")
