"""
Observability Module

Provides:
- Structured logging with trace ID propagation
- Configuration management with YAML support
- Prometheus metrics export
- HTTP metrics server
- Health checks (liveness and readiness)
- Circuit breaker for fault tolerance
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
        HealthChecker,
        HealthStatus,
        MetricsRegistry,
    )
"""

from .structured_logging import (
    StructuredLogger,
    LogContext,
    LogAggregator,
    LogLevel,
    LogFormat,
    get_logger,
)

from .config_manager import (
    ConfigManager,
    ConfigSource,
    ConfigChange,
)

from .prometheus_metrics import (
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
    Timer,
    get_metrics,
)

from .metrics_server import (
    MetricsServer,
    ThreadedHTTPServer,
    start_metrics_server,
)

from .health import (
    HealthChecker,
    HealthStatus,
    HealthReport,
    ServerHealth,
)

from .metrics import (
    MetricsRegistry,
    SimpleHistogram,
)

from .otel import (
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
    "MetricsRegistry",
    "SimpleHistogram",
    "Counter",
    "Gauge",
    "Histogram",
    "Timer",
    "get_metrics",
    # Health
    "HealthChecker",
    "HealthStatus",
    "HealthReport",
    "ServerHealth",
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
