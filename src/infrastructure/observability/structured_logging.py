"""
Structured Logging with Trace ID Propagation

Provides:
- Structured JSON logging
- Trace ID propagation across async tasks
- Structured log correlation with: trace_id, workflow_id, transaction_id, artifact_id, target_id, probe_id, fence_token
- Log levels with filtering
- Multiple output formats (JSON, text)
- Context managers for request tracking
- OpenTelemetry integration for trace correlation
"""

import json
import logging
import logging.handlers
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


# Context variables for trace ID propagation across async tasks
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Extended trace context IDs
_workflow_id: ContextVar[Optional[str]] = ContextVar("workflow_id", default=None)
_transaction_id: ContextVar[Optional[str]] = ContextVar("transaction_id", default=None)
_artifact_id: ContextVar[Optional[str]] = ContextVar("artifact_id", default=None)
_target_id: ContextVar[Optional[str]] = ContextVar("target_id", default=None)
_probe_id: ContextVar[Optional[str]] = ContextVar("probe_id", default=None)
_fence_token: ContextVar[Optional[str]] = ContextVar("fence_token", default=None)


class LogLevel(Enum):
    """Log levels matching standard logging."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogFormat(Enum):
    """Output format for logs."""
    JSON = "json"
    TEXT = "text"
    PRETTY = "pretty"


class TraceContext:
    """
    Container for all trace correlation IDs.

    Collects IDs from both OpenTelemetry span context and local context vars
    to produce a complete correlation picture in every log line.
    """

    def __init__(self):
        self.trace_id: Optional[str] = None
        self.span_id: Optional[str] = None
        self.workflow_id: Optional[str] = None
        self.transaction_id: Optional[str] = None
        self.artifact_id: Optional[str] = None
        self.target_id: Optional[str] = None
        self.probe_id: Optional[str] = None
        self.fence_token: Optional[str] = None
        self.session_id: Optional[str] = None
        self.request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "workflow_id": self.workflow_id,
            "transaction_id": self.transaction_id,
            "artifact_id": self.artifact_id,
            "target_id": self.target_id,
            "probe_id": self.probe_id,
            "fence_token": self.fence_token,
            "session_id": self.session_id,
            "request_id": self.request_id,
        }

    @classmethod
    def from_context_vars(cls) -> "TraceContext":
        """Build context from current ContextVar values."""
        ctx = cls()
        ctx.trace_id = _trace_id.get()
        ctx.session_id = _session_id.get()
        ctx.request_id = _request_id.get()
        ctx.workflow_id = _workflow_id.get()
        ctx.transaction_id = _transaction_id.get()
        ctx.artifact_id = _artifact_id.get()
        ctx.target_id = _target_id.get()
        ctx.probe_id = _probe_id.get()
        ctx.fence_token = _fence_token.get()

        # Enrich with OTel span info if available
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span:
                sc = span.get_span_context()
                if sc.is_valid:
                    ctx.trace_id = ctx.trace_id or format(sc.trace_id, "032x")
                    ctx.span_id = format(sc.span_id, "016x")
        except Exception:
            pass

        return ctx


class StructuredLogger:
    """
    Structured logger with trace ID propagation.

    Features:
    - JSON structured output
    - Automatic trace/span correlation ID injection
    - Extended IDs: workflow_id, transaction_id, artifact_id, target_id, probe_id, fence_token
    - Context managers for scope tracking
    - Multiple handlers support
    - OpenTelemetry span context enrichment
    """

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        format: LogFormat = LogFormat.JSON,
        output_path: Optional[Path] = None,
        max_file_size_mb: int = 100,
        rotation_count: int = 5,
    ):
        self.name = name
        self.level = level
        self.format = format
        self.output_path = output_path
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.rotation_count = rotation_count

        self._logger = logging.getLogger(name)
        self._logger.setLevel(self._to_std_level(level))
        self._logger.handlers.clear()

        self._console_handler: Optional[logging.Handler] = None
        self._file_handler: Optional[logging.Handler] = None
        self._setup_handlers()

    def _to_std_level(self, level: LogLevel) -> int:
        """Convert our LogLevel to std logging level."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(level, logging.INFO)

    def _setup_handlers(self):
        """Setup console and file handlers."""
        if self.format == LogFormat.JSON:
            self._console_handler = JSONConsoleHandler()
        else:
            self._console_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            self._console_handler.setFormatter(formatter)

        self._logger.addHandler(self._console_handler)

        if self.output_path:
            self._setup_file_handler()

    def _setup_file_handler(self):
        """Setup rotating file handler."""
        if self.format == LogFormat.JSON:
            handler = JSONFileHandler(
                self.output_path,
                maxBytes=self.max_file_size,
                backupCount=self.rotation_count,
            )
        else:
            handler = logging.handlers.RotatingFileHandler(
                self.output_path,
                maxBytes=self.max_file_size,
                backupCount=self.rotation_count,
            )
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        self._file_handler = handler
        self._logger.addHandler(handler)

    def set_level(self, level: LogLevel):
        """Change log level."""
        self.level = level
        self._logger.setLevel(self._to_std_level(level))

    def set_trace_id(self, trace_id: Optional[str] = None) -> str:
        """Set trace ID for current context."""
        if trace_id is None:
            trace_id = str(uuid4())[:16]
        _trace_id.set(trace_id)
        return trace_id

    def set_session_id(self, session_id: Optional[str] = None) -> str:
        """Set session ID for current context."""
        if session_id is None:
            session_id = str(uuid4())[:16]
        _session_id.set(session_id)
        return session_id

    def set_request_id(self, request_id: Optional[str] = None) -> str:
        """Set request ID for current context."""
        if request_id is None:
            request_id = str(uuid4())[:12]
        _request_id.set(request_id)
        return request_id

    def set_workflow_id(self, workflow_id: Optional[str] = None) -> str:
        """Set workflow ID for current context."""
        if workflow_id is None:
            workflow_id = str(uuid4())[:16]
        _workflow_id.set(workflow_id)
        return workflow_id

    def set_transaction_id(self, transaction_id: Optional[str] = None) -> str:
        """Set transaction ID for current context."""
        if transaction_id is None:
            transaction_id = str(uuid4())[:16]
        _transaction_id.set(transaction_id)
        return transaction_id

    def set_artifact_id(self, artifact_id: Optional[str] = None) -> str:
        """Set artifact ID for current context."""
        if artifact_id is None:
            artifact_id = str(uuid4())[:16]
        _artifact_id.set(artifact_id)
        return artifact_id

    def set_target_id(self, target_id: Optional[str] = None) -> str:
        """Set target ID for current context."""
        if target_id is None:
            target_id = str(uuid4())[:16]
        _target_id.set(target_id)
        return target_id

    def set_probe_id(self, probe_id: Optional[str] = None) -> str:
        """Set probe ID for current context."""
        if probe_id is None:
            probe_id = str(uuid4())[:16]
        _probe_id.set(probe_id)
        return probe_id

    def set_fence_token(self, fence_token: Optional[str] = None) -> str:
        """Set fence token for current context."""
        if fence_token is None:
            fence_token = str(uuid4())[:16]
        _fence_token.set(fence_token)
        return fence_token

    def clear_context(self):
        """Clear all context IDs."""
        _trace_id.set(None)
        _session_id.set(None)
        _request_id.set(None)
        _workflow_id.set(None)
        _transaction_id.set(None)
        _artifact_id.set(None)
        _target_id.set(None)
        _probe_id.set(None)
        _fence_token.set(None)

    def get_trace_id(self) -> Optional[str]:
        """Get current trace ID."""
        return _trace_id.get()

    @property
    def trace_id(self) -> Optional[str]:
        """Property alias for get_trace_id."""
        return _trace_id.get()

    def _build_record(
        self,
        level: LogLevel,
        message: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Build structured log record with full trace context."""
        trace_ctx = TraceContext.from_context_vars()

        record = {
            "timestamp": datetime.now().isoformat(),
            "level": level.name,
            "logger": self.name,
            "message": message,
            # Primary trace correlation IDs
            "trace_id": trace_ctx.trace_id,
            "span_id": trace_ctx.span_id,
            "session_id": trace_ctx.session_id,
            "request_id": trace_ctx.request_id,
            # Extended correlation IDs
            "workflow_id": trace_ctx.workflow_id,
            "transaction_id": trace_ctx.transaction_id,
            "artifact_id": trace_ctx.artifact_id,
            "target_id": trace_ctx.target_id,
            "probe_id": trace_ctx.probe_id,
            "fence_token": trace_ctx.fence_token,
        }

        if kwargs:
            record["extra"] = kwargs

        return record

    def _log(self, level: LogLevel, message: str, **kwargs):
        """Internal log method."""
        if level.value < self.level.value:
            return

        record = self._build_record(level, message, **kwargs)

        if self.format == LogFormat.JSON:
            self._logger.log(self._to_std_level(level), json.dumps(record))
        else:
            extra_str = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
            full_message = f"{message} | {extra_str}" if extra_str else message
            self._logger.log(self._to_std_level(level), full_message)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: Optional[Exception] = None, **kwargs):
        """Log error message."""
        if exc_info:
            kwargs["exception"] = {
                "type": type(exc_info).__name__,
                "message": str(exc_info),
                "traceback": traceback.format_exc(),
            }
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, exc_info: Optional[Exception] = None, **kwargs):
        """Log critical message."""
        if exc_info:
            kwargs["exception"] = {
                "type": type(exc_info).__name__,
                "message": str(exc_info),
                "traceback": traceback.format_exc(),
            }
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def log_exception(self, message: str, exc: Exception, **kwargs):
        """Log exception with full details."""
        self.error(message, exc_info=exc, **kwargs)


class JSONConsoleHandler(logging.Handler):
    """Console handler that outputs JSON logs."""

    def emit(self, record: logging.LogRecord):
        """Emit JSON log record to stdout."""
        try:
            msg = self.format(record)
            print(msg, file=sys.stdout)
        except Exception:
            self.handleError(record)


class JSONFileHandler(logging.handlers.RotatingFileHandler):
    """File handler that outputs JSON logs with rotation."""

    def emit(self, record: logging.LogRecord):
        """Emit JSON log record to file."""
        try:
            msg = self.format(record)
            self.stream.write(msg + "\n")
            self.flush()
        except Exception:
            self.handleError(record)


def get_logger(name: str, **kwargs) -> StructuredLogger:
    """
    Get or create a structured logger.

    Usage:
        logger = get_logger("my_module")
        logger.info("Hello", user_id="123")
    """
    return StructuredLogger(name, **kwargs)


def set_workflow_id(workflow_id: Optional[str] = None) -> str:
    """Set workflow_id in the current context."""
    if workflow_id is None:
        workflow_id = str(uuid4())[:16]
    _workflow_id.set(workflow_id)
    return workflow_id


def set_transaction_id(transaction_id: Optional[str] = None) -> str:
    """Set transaction_id in the current context."""
    if transaction_id is None:
        transaction_id = str(uuid4())[:16]
    _transaction_id.set(transaction_id)
    return transaction_id


def set_artifact_id(artifact_id: Optional[str] = None) -> str:
    """Set artifact_id in the current context."""
    if artifact_id is None:
        artifact_id = str(uuid4())[:16]
    _artifact_id.set(artifact_id)
    return artifact_id


def set_target_id(target_id: Optional[str] = None) -> str:
    """Set target_id in the current context."""
    if target_id is None:
        target_id = str(uuid4())[:16]
    _target_id.set(target_id)
    return target_id


def set_probe_id(probe_id: Optional[str] = None) -> str:
    """Set probe_id in the current context."""
    if probe_id is None:
        probe_id = str(uuid4())[:16]
    _probe_id.set(probe_id)
    return probe_id


def set_fence_token(fence_token: Optional[str] = None) -> str:
    """Set fence_token in the current context."""
    if fence_token is None:
        fence_token = str(uuid4())[:16]
    _fence_token.set(fence_token)
    return fence_token


def get_current_trace_context() -> TraceContext:
    """Get all current trace context values."""
    return TraceContext.from_context_vars()


class LogContext:
    """
    Context manager for scoped logging with full trace context.

    Usage:
        logger = get_logger("workflow")
        with LogContext(logger, workflow_id="wf-123", transaction_id="tx-456") as ctx:
            logger.info("Starting workflow")
            # All logs in this scope will have the full trace context
    """

    def __init__(
        self,
        logger: StructuredLogger,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        target_id: Optional[str] = None,
        probe_id: Optional[str] = None,
        fence_token: Optional[str] = None,
        **extra,
    ):
        self.logger = logger
        self.trace_id = trace_id
        self.session_id = session_id
        self.request_id = request_id
        self.workflow_id = workflow_id
        self.transaction_id = transaction_id
        self.artifact_id = artifact_id
        self.target_id = target_id
        self.probe_id = probe_id
        self.fence_token = fence_token
        self.extra = extra

        self._saved: Dict[str, Any] = {}

    def __enter__(self):
        """Enter context and save/restore IDs."""
        self._saved = {
            "trace_id": _trace_id.get(),
            "session_id": _session_id.get(),
            "request_id": _request_id.get(),
            "workflow_id": _workflow_id.get(),
            "transaction_id": _transaction_id.get(),
            "artifact_id": _artifact_id.get(),
            "target_id": _target_id.get(),
            "probe_id": _probe_id.get(),
            "fence_token": _fence_token.get(),
        }

        if self.trace_id is not None:
            _trace_id.set(self.trace_id)
        if self.session_id is not None:
            _session_id.set(self.session_id)
        if self.request_id is not None:
            _request_id.set(self.request_id)
        if self.workflow_id is not None:
            _workflow_id.set(self.workflow_id)
        if self.transaction_id is not None:
            _transaction_id.set(self.transaction_id)
        if self.artifact_id is not None:
            _artifact_id.set(self.artifact_id)
        if self.target_id is not None:
            _target_id.set(self.target_id)
        if self.probe_id is not None:
            _probe_id.set(self.probe_id)
        if self.fence_token is not None:
            _fence_token.set(self.fence_token)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore previous IDs."""
        for key, val in self._saved.items():
            ctx_var = {
                "trace_id": _trace_id,
                "session_id": _session_id,
                "request_id": _request_id,
                "workflow_id": _workflow_id,
                "transaction_id": _transaction_id,
                "artifact_id": _artifact_id,
                "target_id": _target_id,
                "probe_id": _probe_id,
                "fence_token": _fence_token,
            }.get(key)
            if ctx_var is not None:
                ctx_var.set(val)
        return False


class LogAggregator:
    """
    Aggregate logs for batch processing.

    Useful for:
    - Buffering logs for async processing
    - Batch writes to reduce I/O
    - Log sampling for high-volume streams
    """

    def __init__(self, max_size: int = 1000, flush_interval: float = 5.0):
        self.max_size = max_size
        self.flush_interval = flush_interval
        self._buffer: list = []
        self._flush_callbacks: list = []

    def add_log(self, record: Dict[str, Any]):
        """Add log record to buffer."""
        self._buffer.append(record)
        if len(self._buffer) >= self.max_size:
            self.flush()

    def on_flush(self, callback):
        """Register flush callback."""
        self._flush_callbacks.append(callback)

    def flush(self):
        """Flush buffer to callbacks."""
        if not self._buffer:
            return

        logs = self._buffer.copy()
        self._buffer.clear()

        for callback in self._flush_callbacks:
            try:
                callback(logs)
            except Exception:
                pass

    def __len__(self):
        return len(self._buffer)
