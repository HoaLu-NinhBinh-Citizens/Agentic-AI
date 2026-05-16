"""
Structured Logging with Trace ID Propagation

Provides:
- Structured JSON logging
- Trace ID generation and propagation
- Log levels with filtering
- Multiple output formats (JSON, text)
- Context managers for request tracking
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

# Context variable for trace ID propagation across async tasks
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


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


class StructuredLogger:
    """
    Structured logger with trace ID propagation.

    Features:
    - JSON structured output
    - Automatic trace/request/session ID injection
    - Context managers for scope tracking
    - Multiple handlers support
    - Rate limiting for high-volume logging
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

        # Internal logger
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self._to_std_level(level))
        self._logger.handlers.clear()

        # Handlers
        self._console_handler = None
        self._file_handler = None
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
        # Console handler
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

        # File handler (if output path specified)
        if self.output_path:
            self._setup_file_handler()

    def _setup_file_handler(self):
        """Setup rotating file handler."""
        import logging.handlers

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
        """
        Set trace ID for current context.

        Args:
            trace_id: Optional specific ID, auto-generated if not provided

        Returns:
            The trace ID (generated or provided)
        """
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

    def clear_context(self):
        """Clear all context IDs."""
        _trace_id.set(None)
        _session_id.set(None)
        _request_id.set(None)

    def get_trace_id(self) -> Optional[str]:
        """Get current trace ID."""
        return _trace_id.get()

    @property
    def trace_id(self) -> Optional[str]:
        """Property alias for get_trace_id."""
        return _trace_id.get()

    @property
    def session_id(self) -> Optional[str]:
        """Property alias for session ID."""
        return _session_id.get()

    @property
    def request_id(self) -> Optional[str]:
        """Property alias for request ID."""
        return _request_id.get()

    def _build_record(
        self,
        level: LogLevel,
        message: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Build structured log record."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "level": level.name,
            "logger": self.name,
            "message": message,
            "trace_id": _trace_id.get(),
            "session_id": _session_id.get(),
            "request_id": _request_id.get(),
        }

        # Add extra fields
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
            # Format as text with extra fields
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


class LogContext:
    """
    Context manager for scoped logging.

    Usage:
        logger = get_logger("workflow")
        with LogContext(logger, trace_id="workflow-123") as ctx:
            logger.info("Starting workflow")
            # All logs in this scope will have trace_id="workflow-123"
    """

    def __init__(
        self,
        logger: StructuredLogger,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        **extra,
    ):
        self.logger = logger
        self.trace_id = trace_id
        self.session_id = session_id
        self.request_id = request_id
        self.extra = extra
        self._previous_trace = None
        self._previous_session = None
        self._previous_request = None

    def __enter__(self):
        """Enter context and set IDs."""
        self._previous_trace = _trace_id.get()
        self._previous_session = _session_id.get()
        self._previous_request = _request_id.get()

        if self.trace_id:
            _trace_id.set(self.trace_id)
        if self.session_id:
            _session_id.set(self.session_id)
        if self.request_id:
            _request_id.set(self.request_id)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore previous IDs."""
        _trace_id.set(self._previous_trace)
        _session_id.set(self._previous_session)
        _request_id.set(self._previous_request)
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
