"""
Observability Module

Provides:
- Structured logging with trace ID propagation
- Configuration management with YAML support
- Prometheus metrics export
- HTTP metrics server
- Health checks (liveness and readiness)
- Circuit breaker for fault tolerance
- OpenTelemetry tracing with SDK integration
- Execution graph and causal chain logging
- Replay trace capture and forensic diff

Usage:
    from src.infrastructure.observability import (
        StructuredLogger,
        LogContext,
        LogLevel,
        get_logger,
        configure_tracing,
        get_tracer,
        get_current_trace_id,
        set_workflow_id,
        set_transaction_id,
        set_artifact_id,
        set_target_id,
        set_probe_id,
        set_fence_token,
        TraceContext,
        HealthChecker,
        HealthStatus,
        MetricsCollector,
    )
"""

from .structured_logging import (
    StructuredLogger,
    LogContext,
    LogAggregator,
    LogLevel,
    LogFormat,
    get_logger,
    TraceContext,
    get_current_trace_context,
    set_workflow_id,
    set_transaction_id,
    set_artifact_id,
    set_target_id,
    set_probe_id,
    set_fence_token,
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
    configure_tracing,
    get_tracer,
    get_current_trace_id,
    get_current_span_id,
    get_replay_exporter,
    ReplaySpanExporter,
    TraceConfig,
    TraceId,
    traced,
    SpanStatus,
    SpanKind,
)

__all__ = [
    # Logging
    "StructuredLogger",
    "LogContext",
    "LogAggregator",
    "LogLevel",
    "LogFormat",
    "get_logger",
    "TraceContext",
    "get_current_trace_context",
    "set_workflow_id",
    "set_transaction_id",
    "set_artifact_id",
    "set_target_id",
    "set_probe_id",
    "set_fence_token",
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
    "configure_tracing",
    "get_tracer",
    "get_current_trace_id",
    "get_current_span_id",
    "get_replay_exporter",
    "ReplaySpanExporter",
    "TraceConfig",
    "TraceId",
    "traced",
    "SpanStatus",
    "SpanKind",
]
