"""
OpenTelemetry Production Integration

Provides distributed tracing integration using OpenTelemetry SDK.
Enables tracing across all AI_support components with:
- Real OpenTelemetry SDK (not custom implementation)
- OTLP export to collectors (Jaeger, Tempo, etc.)
- Automatic span context propagation
- Resource and attribute enrichment
- Sampling support

Usage:
    from src.infrastructure.observability import configure_tracing, tracer

    # Initialize once at startup
    configure_tracing(service_name="ai_support")

    # Use the global tracer
    with tracer.start_as_current_span("operation") as span:
        span.set_attribute("workflow_id", "wf-123")
        # do work
"""

import os
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.context import Context

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _OTLP_AVAILABLE = True
except ImportError:
    _OTLP_AVAILABLE = False

logger = logging.getLogger(__name__)


class TraceConfig:
    """Trace configuration."""

    def __init__(
        self,
        service_name: str = "ai_support",
        service_version: str = "1.0.0",
        environment: str = "development",
        otlp_endpoint: Optional[str] = None,
        enabled: bool = True,
        sample_rate: float = 1.0,
        console_export: bool = False,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.otlp_endpoint = otlp_endpoint
        self.enabled = enabled
        self.sample_rate = sample_rate
        self.console_export = console_export


class TraceId:
    """Utility class for working with trace IDs."""

    @staticmethod
    def get_current() -> Optional[str]:
        """Get current span's trace ID as hex string."""
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().trace_id, "032x")
        return None

    @staticmethod
    def get_current_span_id() -> Optional[str]:
        """Get current span's span ID as hex string."""
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().span_id, "016x")
        return None


class ReplaySpanExporter:
    """
    Captures spans for replay trace analysis.

    Stores spans in memory for later comparison between
    original and replayed execution.
    """

    def __init__(self):
        self._spans: list[Dict[str, Any]] = []

    def export(self, span: ReadableSpan) -> None:
        """Capture a span for replay analysis."""
        self._spans.append(self._span_to_dict(span))

    def _span_to_dict(self, span: ReadableSpan) -> Dict[str, Any]:
        """Convert span to dictionary for storage."""
        ctx = span.get_span_context()
        return {
            "name": span.name,
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "parent_span_id": format(span.parent.span_id, "016x") if span.parent and span.parent.is_valid else None,
            "kind": span.kind.name,
            "start_time": datetime.fromtimestamp(span.start_time / 1e9).isoformat(),
            "end_time": datetime.fromtimestamp(span.end_time / 1e9).isoformat(),
            "duration_ms": (span.end_time - span.start_time) / 1e6,
            "attributes": dict(span.attributes) if span.attributes else {},
            "events": [
                {
                    "name": e.name,
                    "timestamp": datetime.fromtimestamp(e.timestamp / 1e9).isoformat(),
                    "attributes": dict(e.attributes) if e.attributes else {},
                }
                for e in span.events
            ],
            "status": span.status.status_code.name if span.status else "UNSET",
            "status_description": span.status.description if span.status else None,
        }

    def get_spans(self) -> list[Dict[str, Any]]:
        """Get all captured spans."""
        return self._spans.copy()

    def get_traces(self) -> Dict[str, list[Dict[str, Any]]]:
        """Group spans by trace ID."""
        traces: Dict[str, list[Dict[str, Any]]] = {}
        for span in self._spans:
            tid = span["trace_id"]
            if tid not in traces:
                traces[tid] = []
            traces[tid].append(span)
        return traces

    def clear(self) -> None:
        """Clear all captured spans."""
        self._spans.clear()


# Global instances
_global_config: Optional[TraceConfig] = None
_global_tracer: Optional[trace.Tracer] = None
_global_provider: Optional[TracerProvider] = None
_replay_exporter: Optional[ReplaySpanExporter] = None


def configure_tracing(
    service_name: str = "ai_support",
    service_version: str = "1.0.0",
    environment: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    console_export: bool = False,
    sample_rate: float = 1.0,
) -> trace.Tracer:
    """
    Configure global OpenTelemetry tracing.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        environment: Deployment environment (defaults to OTEL_ENV or "development")
        otlp_endpoint: OTLP collector endpoint (e.g., "http://localhost:4317")
        console_export: Enable console span export for debugging
        sample_rate: Sampling rate (1.0 = 100%)

    Returns:
        Configured tracer instance
    """
    global _global_config, _global_tracer, _global_provider, _replay_exporter

    env = environment or os.getenv("OTEL_ENV", "development")
    _global_config = TraceConfig(
        service_name=service_name,
        service_version=service_version,
        environment=env,
        otlp_endpoint=otlp_endpoint,
        console_export=console_export,
        sample_rate=sample_rate,
    )

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        DEPLOYMENT_ENVIRONMENT: env,
    })

    _global_provider = TracerProvider(resource=resource)
    _replay_exporter = ReplaySpanExporter()

    _global_provider.add_span_processor(SpanProcessor(_replay_exporter))

    if console_export:
        _global_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Console span export enabled")

    if otlp_endpoint and _OTLP_AVAILABLE:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            _global_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTLP export configured: {otlp_endpoint}")
        except Exception as exc:
            logger.warning(f"Failed to configure OTLP exporter: {exc}")

    trace.set_tracer_provider(_global_provider)
    _global_tracer = trace.get_tracer(service_name, service_version)

    logger.info(f"OpenTelemetry configured: service={service_name}, env={env}")
    return _global_tracer


def get_tracer() -> trace.Tracer:
    """
    Get the global tracer instance.

    Creates a default tracer if not configured.
    """
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = trace.get_tracer("ai_support", "1.0.0")
    return _global_tracer


def get_replay_exporter() -> ReplaySpanExporter:
    """Get the replay span exporter for forensic analysis."""
    global _replay_exporter
    if _replay_exporter is None:
        _replay_exporter = ReplaySpanExporter()
    return _replay_exporter


def get_current_trace_id() -> Optional[str]:
    """Get current trace ID from active span."""
    return TraceId.get_current()


def get_current_span_id() -> Optional[str]:
    """Get current span ID from active span."""
    return TraceId.get_current_span_id()


@contextmanager
def traced(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[trace.Span, None, None]:
    """
    Context manager for creating traced spans.

    Usage:
        with traced("my_operation", attributes={"key": "value"}) as span:
            # work
            span.set_attribute("result", "success")
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


# Backward-compatible type aliases for existing code
SpanStatus = Status
SpanKind = SpanKind
