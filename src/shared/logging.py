"""Structured logging for Phase 2D/2D.1.

Provides:
- JSON-formatted logging with correlation IDs
- Redaction filter for sensitive fields
- Log rotation support
- Dynamic log level adjustment
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Any


DEFAULT_REDACTED_FIELDS = {
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "private_key",
    "access_token",
    "refresh_token",
    "session_token",
    "bearer",
    "credential",
    "passwd",
    "pwd",
}


def redact_sensitive_data(
    obj: Any,
    redacted_fields: set[str] | None = None,
) -> Any:
    """Redact sensitive fields from data structures.

    Args:
        obj: The object to redact (dict, list, or primitive).
        redacted_fields: Set of field names to redact. Uses DEFAULT_REDACTED_FIELDS if None.

    Returns:
        Redacted copy of the object.
    """
    fields = redacted_fields or DEFAULT_REDACTED_FIELDS
    fields_lower = {f.lower() for f in fields}

    if isinstance(obj, dict):
        return {
            k: redact_sensitive_data(v, fields)
            if k.lower() not in fields_lower
            else "[REDACTED]"
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [redact_sensitive_data(item, fields) for item in obj]
    else:
        return obj


class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Outputs logs in JSON format with consistent fields for observability.
    Supports redaction of sensitive fields.
    """

    def __init__(
        self,
        redacted_fields: set[str] | None = None,
    ) -> None:
        """Initialize the formatter.

        Args:
            redacted_fields: Set of field names to redact. Uses DEFAULT_REDACTED_FIELDS if None.
        """
        super().__init__()
        self._redacted_fields = redacted_fields or DEFAULT_REDACTED_FIELDS

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON string representation.
        """
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        standard_fields = {
            "session_id",
            "trace_id",
            "call_id",
            "duration_ms",
            "tool_name",
            "error_code",
            "error_message",
            "server_name",
            "attempt",
            "max_attempts",
            "delay",
            "failure_count",
            "circuit_state",
            "status",
            "reason",
            "detail",
            "mcp_server",
            "endpoint",
        }

        for field in standard_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    log_obj[field] = value

        redacted_obj = redact_sensitive_data(log_obj, self._redacted_fields)

        import json
        return json.dumps(redacted_obj, default=str)


def log_with_context(
    logger: logging.Logger,
    level: int,
    msg: str,
    **kwargs: Any,
) -> None:
    """Log a message with additional context fields.

    Args:
        logger: The logger to use.
        level: Log level (e.g., logging.INFO, logging.ERROR).
        msg: Log message.
        **kwargs: Additional context fields to include.
    """
    extra = {k: v for k, v in kwargs.items() if v is not None}
    logger.log(level, msg, extra=extra)


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    file_path: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    redacted_fields: set[str] | None = None,
) -> logging.Handler:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        format_type: Format type ('json' or 'console').
        file_path: Optional file path for file logging.
        max_bytes: Maximum size of log file before rotation.
        backup_count: Number of backup files to keep.
        redacted_fields: Set of field names to redact.

    Returns:
        The configured root handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if file_path:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
    else:
        handler = logging.StreamHandler()

    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if format_type == "json":
        formatter = StructuredJsonFormatter(redacted_fields=redacted_fields)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    return handler


def get_current_log_level() -> str:
    """Get the current log level.

    Returns:
        Current log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    return logging.getLevelName(root_logger.level)


def set_log_level(level: str) -> str:
    """Set the log level at runtime.

    Args:
        level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        The new log level.

    Raises:
        ValueError: If level is invalid.
    """
    level_upper = level.upper()
    if level_upper not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise ValueError(f"Invalid log level: {level}")

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level_upper))
    return level_upper
