"""Tool execution error hierarchy for Phase 2B.

Defines structured errors for tool execution failures with
standardized error codes for client handling.
"""

from __future__ import annotations


class ToolExecutionError(Exception):
    """Base exception for tool execution errors.

    All tool-related errors inherit from this class.
    Subclasses must define a `code` class attribute for error identification.

    Attributes:
        code: Error code string for programmatic handling.
    """

    code: str = "TOOL_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ToolNotFoundError(ToolExecutionError):
    """Raised when the requested tool does not exist."""

    code = "TOOL_NOT_FOUND"


class ToolTimeoutError(ToolExecutionError):
    """Raised when tool execution exceeds the configured timeout."""

    code = "TIMEOUT"


class MCPError(ToolExecutionError):
    """Raised when the MCP server returns an error."""

    code = "MCP_ERROR"


class InvalidArgumentsError(ToolExecutionError):
    """Raised when tool arguments fail validation."""

    code = "INVALID_ARGUMENTS"


class ToolBusyError(ToolExecutionError):
    """Raised when session has too many concurrent tool calls."""

    code = "TOO_MANY_CONCURRENT"


class ToolSessionClosedError(ToolExecutionError):
    """Raised when attempting to call a tool on a closed session."""

    code = "SESSION_CLOSED"


class ToolPermissionError(ToolExecutionError):
    """Raised when session lacks permission to execute a tool."""

    code = "PERMISSION_DENIED"


def normalize_tool_error(exc: Exception) -> tuple[str, str]:
    """Convert any exception to a standardized error code and message.

    This function ensures all tool execution errors are normalized to
    a consistent format regardless of their original source.

    Args:
        exc: Any exception that occurred during tool execution.

    Returns:
        Tuple of (error_code, error_message) strings.
    """
    import asyncio

    if isinstance(exc, ToolExecutionError):
        return exc.code, exc.message

    if isinstance(exc, asyncio.TimeoutError):
        return "TIMEOUT", "Tool execution timed out"

    if isinstance(exc, ValueError):
        return "INVALID_ARGUMENTS", str(exc)

    if isinstance(exc, TypeError):
        return "INVALID_ARGUMENTS", f"Type error: {str(exc)}"

    if isinstance(exc, KeyError):
        return "INVALID_ARGUMENTS", f"Missing required argument: {str(exc)}"

    if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
        return "TOOL_NOT_FOUND", str(exc)

    return "INTERNAL_ERROR", str(exc)
