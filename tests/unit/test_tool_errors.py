"""Unit tests for error normalization (Phase 2B)."""

from __future__ import annotations

import pytest

from shared.exceptions.tool_errors import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    MCPError,
    InvalidArgumentsError,
    ToolBusyError,
    ToolSessionClosedError,
    normalize_tool_error,
)


class TestNormalizeToolError:
    """Test suite for normalize_tool_error function."""

    def test_tool_execution_error(self):
        """Test ToolExecutionError subclass normalization."""
        exc = ToolNotFoundError("Tool 'foo' not found")
        code, msg = normalize_tool_error(exc)

        assert code == "TOOL_NOT_FOUND"
        assert "foo" in msg

    def test_tool_timeout_error(self):
        """Test ToolTimeoutError normalization."""
        exc = ToolTimeoutError("Execution timed out")
        code, msg = normalize_tool_error(exc)

        assert code == "TIMEOUT"
        assert "timed out" in msg

    def test_mcp_error(self):
        """Test MCPError normalization."""
        exc = MCPError("MCP server error")
        code, msg = normalize_tool_error(exc)

        assert code == "MCP_ERROR"
        assert "MCP server error" in msg

    def test_invalid_arguments_error(self):
        """Test InvalidArgumentsError normalization."""
        exc = InvalidArgumentsError("Invalid argument")
        code, msg = normalize_tool_error(exc)

        assert code == "INVALID_ARGUMENTS"
        assert "Invalid argument" in msg

    def test_tool_busy_error(self):
        """Test ToolBusyError normalization."""
        exc = ToolBusyError("Too many concurrent calls")
        code, msg = normalize_tool_error(exc)

        assert code == "TOO_MANY_CONCURRENT"

    def test_session_closed_error(self):
        """Test ToolSessionClosedError normalization."""
        exc = ToolSessionClosedError("Session is closed")
        code, msg = normalize_tool_error(exc)

        assert code == "SESSION_CLOSED"

    def test_asyncio_timeout_error(self):
        """Test asyncio.TimeoutError normalization."""
        import asyncio

        exc = asyncio.TimeoutError()
        code, msg = normalize_tool_error(exc)

        assert code == "TIMEOUT"
        assert "timed out" in msg.lower()

    def test_value_error(self):
        """Test ValueError normalization."""
        exc = ValueError("Invalid value provided")
        code, msg = normalize_tool_error(exc)

        assert code == "INVALID_ARGUMENTS"
        assert "Invalid value provided" in msg

    def test_type_error(self):
        """Test TypeError normalization."""
        exc = TypeError("expected str, got int")
        code, msg = normalize_tool_error(exc)

        assert code == "INVALID_ARGUMENTS"
        assert "Type error" in msg

    def test_key_error(self):
        """Test KeyError normalization."""
        exc = KeyError("missing_key")
        code, msg = normalize_tool_error(exc)

        assert code == "INVALID_ARGUMENTS"
        assert "missing_key" in msg

    def test_not_found_in_message(self):
        """Test errors with 'not found' in message."""
        exc = RuntimeError("Tool does not exist")
        code, msg = normalize_tool_error(exc)

        assert code == "TOOL_NOT_FOUND"

    def test_generic_exception(self):
        """Test generic Exception normalization."""
        exc = RuntimeError("Something went wrong")
        code, msg = normalize_tool_error(exc)

        assert code == "INTERNAL_ERROR"
        assert "Something went wrong" in msg
