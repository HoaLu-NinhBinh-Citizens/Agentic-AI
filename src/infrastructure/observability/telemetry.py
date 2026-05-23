"""OpenTelemetry Integration for Distributed Tracing.

Provides:
- Trace context propagation
- Span creation and management
- Metrics collection
- Log correlation
- Export to multiple backends (Jaeger, Zipkin, OTLP)

Usage:
    from src.infrastructure.observability.telemetry import get_tracer, trace_span
    
    tracer = get_tracer("agent")
    
    # Create spans
    async with trace_span("process_task") as span:
        span.set_attribute("task.id", task_id)
        result = await process_task(task_id)
        span.set_status(StatusCode.OK)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from functools import wraps

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Status, StatusCode, SpanKind
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.propagate import set_global_textmap
    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False
    logger.warning("opentelemetry_not_installed")


@dataclass
class TelemetryConfig:
    """Configuration for OpenTelemetry."""
    service_name: str = "aisupport"
    service_version: str = "1.0.0"
    environment: str = "development"
    
    # Tracing
    tracing_enabled: bool = True
    tracing_endpoint: str = "http://localhost:4317"  # OTLP gRPC
    tracing_export_interval_ms: int = 5000
    
    # Metrics
    metrics_enabled: bool = True
    metrics_endpoint: str = "http://localhost:4318"
    
    # Sampling
    sampling_rate: float = 1.0  # 100% in dev, lower in prod
    sampling_type: str = "always_on"  # always_on, always_off, trace_id_ratio


class NoOpSpan:
    """No-op span for when OpenTelemetry is not available."""
    
    def set_attribute(self, key: str, value: Any) -> None:
        pass
    
    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass
    
    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass
    
    def set_status(self, status: Any) -> None:
        pass
    
    def record_exception(self, exception: Exception) -> None:
        pass
    
    def end(self) -> None:
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""
    
    @asynccontextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield NoOpSpan()
    
    def start_span(self, name: str, **kwargs):
        return NoOpSpan()


@dataclass
class TelemetryManager:
    """Manager for OpenTelemetry components.
    
    Provides:
    - Automatic trace context propagation
    - Span lifecycle management
    - Metrics collection
    - Log correlation
    """
    
    config: TelemetryConfig = field(default_factory=TelemetryConfig)
    
    _tracer_provider: Any = field(default=None, init=False)
    _meter_provider: Any = field(default=None, init=False)
    _tracer: Any = field(default=None, init=False)
    _meter: Any = field(default=None, init=False)
    _initialized: bool = field(default=False, init=False)
    _propagator: Any = field(default=None, init=False)
    
    async def initialize(self) -> None:
        """Initialize OpenTelemetry."""
        if self._initialized:
            return
        
        if not HAS_OPENTELEMETRY:
            logger.warning("opentelemetry_not_available")
            self._initialized = True
            return
        
        try:
            # Create resource
            resource = Resource.create({
                "service.name": self.config.service_name,
                "service.version": self.config.service_version,
                "deployment.environment": self.config.environment,
            })
            
            # Initialize tracer provider with sampling
            tracer_provider = TracerProvider(resource=resource)
            
            # Set up exporter (configurable)
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=self.config.tracing_endpoint, insecure=True)
                span_processor = BatchSpanProcessor(exporter)
                tracer_provider.add_span_processor(span_processor)
            except Exception as e:
                logger.warning("otlp_exporter_failed", error=str(e))
            
            trace.set_tracer_provider(tracer_provider)
            self._tracer_provider = tracer_provider
            
            # Initialize meter provider
            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
                metric_exporter = OTLPMetricExporter(endpoint=self.config.metrics_endpoint, insecure=True)
                metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=self.config.tracing_export_interval_ms)
                meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            except Exception as e:
                logger.warning("otlp_metric_exporter_failed", error=str(e))
                meter_provider = MeterProvider(resource=resource)
            
            metrics.set_meter_provider(meter_provider)
            self._meter_provider = meter_provider
            
            # Get tracer and meter
            self._tracer = trace.get_tracer(self.config.service_name, self.config.service_version)
            self._meter = metrics.get_meter(self.config.service_name, self.config.service_version)
            
            # Set up propagator for distributed tracing
            self._propagator = TraceContextTextMapPropagator()
            set_global_textmap(self._propagator)
            
            self._initialized = True
            logger.info("telemetry_initialized", 
                service=self.config.service_name,
                tracing=self.config.tracing_enabled,
                metrics=self.config.metrics_enabled
            )
            
        except Exception as e:
            logger.error("telemetry_init_failed", error=str(e))
            self._initialized = True  # Prevent retry loops
    
    async def shutdown(self) -> None:
        """Shutdown OpenTelemetry."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()
        logger.info("telemetry_shutdown")
    
    @property
    def tracer(self):
        """Get the tracer."""
        if not self._initialized:
            return NoOpTracer()
        if not self._tracer:
            return NoOpTracer()
        return self._tracer
    
    @property
    def meter(self):
        """Get the meter."""
        if not self._initialized:
            return NoOpMeter()
        if not self._meter:
            return NoOpMeter()
        return self._meter
    
    def create_counter(self, name: str, unit: str = "", description: str = ""):
        """Create a counter metric."""
        return self.meter.create_counter(name, unit, description)
    
    def create_histogram(self, name: str, unit: str = "", description: str = ""):
        """Create a histogram metric."""
        return self.meter.create_histogram(name, unit, description)
    
    def create_gauge(self, name: str, unit: str = "", description: str = ""):
        """Create a gauge metric."""
        return self.meter.create_observable_gauge(name, (), unit, description)
    
    def inject_context(self, carrier: dict) -> dict:
        """Inject trace context into carrier (e.g., HTTP headers)."""
        if self._propagator:
            self._propagator.inject(carrier)
        return carrier
    
    def extract_context(self, carrier: dict):
        """Extract trace context from carrier."""
        if self._propagator:
            return self._propagator.extract(carrier)
        return None


class NoOpMeter:
    """No-op meter for when OpenTelemetry is not available."""
    
    def create_counter(self, name: str, unit: str = "", description: str = ""):
        return NoOpCounter()
    
    def create_histogram(self, name: str, unit: str = "", description: str = ""):
        return NoOpHistogram()
    
    def create_observable_gauge(self, name: str, callbacks=[], unit: str = "", description: str = ""):
        return NoOpGauge()


class NoOpCounter:
    def add(self, amount: int = 1, attributes: dict = None):
        pass


class NoOpHistogram:
    def record(self, amount: float, attributes: dict = None):
        pass


class NoOpGauge:
    pass


# Global telemetry manager
_telemetry: TelemetryManager | None = None


def get_telemetry() -> TelemetryManager:
    """Get the global telemetry manager."""
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryManager()
    return _telemetry


async def init_telemetry(config: TelemetryConfig | None = None) -> TelemetryManager:
    """Initialize telemetry with config."""
    global _telemetry
    _telemetry = TelemetryManager(config=config) if config else TelemetryManager()
    await _telemetry.initialize()
    return _telemetry


def get_tracer(name: str = "aisupport") -> Any:
    """Get a tracer by name."""
    return get_telemetry().tracer


def get_meter(name: str = "aisupport") -> Any:
    """Get a meter by name."""
    return get_telemetry().meter


@asynccontextmanager
async def trace_span(
    name: str,
    kind: int = 0,  # SpanKind.INTERNAL
    attributes: dict[str, Any] | None = None,
):
    """Context manager for creating trace spans.
    
    Usage:
        async with trace_span("process_task", attributes={"task.id": "123"}) as span:
            result = await process()
            span.set_attribute("result", "success")
    """
    tracer = get_tracer()
    
    if HAS_OPENTELEMETRY:
        from opentelemetry.trace import SpanKind
        kind = SpanKind.INTERNAL
    
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            span.set_attributes(attributes)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            if HAS_OPENTELEMETRY:
                span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def traced(
    span_name: str | None = None,
    attributes: dict[str, Any] | None = None,
):
    """Decorator for tracing async functions.
    
    Usage:
        @traced("process_task")
        async def process_task():
            return await do_work()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            name = span_name or func.__name__
            async with trace_span(name, attributes=attributes) as span:
                result = await func(*args, **kwargs)
                return result
        return wrapper
    return decorator


class StructuredLogger:
    """Structured logger with trace correlation.
    
    Usage:
        logger = StructuredLogger("agent")
        logger.info("task_completed", task_id="123", duration_ms=50)
    """
    
    def __init__(self, component: str):
        self._logger = logging.getLogger(component)
        self._component = component
    
    def _log(
        self,
        level: int,
        msg: str,
        trace_id: str | None = None,
        span_id: str | None = None,
        **kwargs
    ):
        """Log with trace context."""
        extra = {"component": self._component}
        
        if trace_id:
            extra["trace_id"] = trace_id
        if span_id:
            extra["span_id"] = span_id
        
        self._logger.log(level, msg, extra=extra, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)
    
    def exception(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)


def get_logger(component: str) -> StructuredLogger:
    """Get a structured logger."""
    return StructuredLogger(component)
