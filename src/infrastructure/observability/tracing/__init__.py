"""
Tracing module - OpenTelemetry SDK integration.

Re-exports from the main otel module for convenient access.
"""

from opentelemetry.trace import SpanKind, Status, StatusCode

from ..otel import (
    configure_tracing,
    get_tracer,
    get_current_trace_id,
    get_current_span_id,
    get_replay_exporter,
    ReplaySpanExporter,
    TraceConfig,
    TraceId,
    traced,
)


__all__ = [
    "SpanKind",
    "Status",
    "StatusCode",
    "configure_tracing",
    "get_tracer",
    "get_current_trace_id",
    "get_current_span_id",
    "get_replay_exporter",
    "ReplaySpanExporter",
    "TraceConfig",
    "TraceId",
    "traced",
]
