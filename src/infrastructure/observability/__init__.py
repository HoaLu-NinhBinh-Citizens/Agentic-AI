"""
Observability Module

Provides:
- Structured logging with trace ID propagation
- Configuration management with YAML support
- Prometheus metrics export
- HTTP metrics server
- OpenTelemetry tracing with span management
- Execution graph and causal chain logging

Usage:
    from src.infrastructure.observability import (
        StructuredLogger,
        LogContext,
        ConfigManager,
        MetricsCollector,
        MetricsServer,
        OtelTracer,
        TraceContext,
        Span,
        configure_tracing,
    )
"""

from src.infrastructure.observability.structured_logging import (
    StructuredLogger,
    LogContext,
    LogAggregator,
    LogLevel,
    LogFormat,
    get_logger,
)

from src.infrastructure.observability.config_manager import (
    ConfigManager,
    ConfigSource,
    ConfigChange,
)

from src.infrastructure.observability.prometheus_metrics import (
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
    Timer,
    get_metrics,
)

from src.infrastructure.observability.metrics_server import (
    MetricsServer,
    ThreadedHTTPServer,
    start_metrics_server,
)

from src.infrastructure.observability.otel import (
    OtelTracer,
    TraceContext,
    Span,
    SpanStatus,
    SpanKind,
    TraceConfig,
    TraceExporter,
    ConsoleExporter,
    OtlpExporter,
    JaegerExporter,
    configure_tracing,
    get_tracer,
)

__all__ = [
    # Logging
    "StructuredLogger",
    "LogContext",
    "LogAggregator",
    "LogLevel",
    "LogFormat",
    "get_logger",
    # Config
    "ConfigManager",
    "ConfigSource",
    "ConfigChange",
    # Metrics
    "MetricsCollector",
    "Counter",
    "Gauge",
    "Histogram",
    "Timer",
    "get_metrics",
    # Server
    "MetricsServer",
    "ThreadedHTTPServer",
    "start_metrics_server",
    # Tracing
    "OtelTracer",
    "TraceContext",
    "Span",
    "SpanStatus",
    "SpanKind",
    "TraceConfig",
    "TraceExporter",
    "ConsoleExporter",
    "OtlpExporter",
    "JaegerExporter",
    "configure_tracing",
    "get_tracer",
]