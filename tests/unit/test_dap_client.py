"""Unit tests for DAP client."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.debug.dap_client import (
    DAPConnection,
    DAPDebugger,
    DAPSession,
    DAPError,
    DAPBreakpoint,
    DAPThread,
    DAPStackFrame,
    DAPVariable,
    DAPStoppedEvent,
)


class TestDAPBreakpoint:
    """Tests for DAPBreakpoint."""

    def test_create_breakpoint(self):
        """Test creating breakpoint."""
        bp = DAPBreakpoint("test.py", 10)
        
        assert bp.source == "test.py"
        assert bp.line == 10
        assert bp.verified is False

    def test_breakpoint_with_condition(self):
        """Test breakpoint with condition."""
        bp = DAPBreakpoint("test.py", 10, condition="x > 5")
        
        assert bp.condition == "x > 5"


class TestDAPConnection:
    """Tests for DAPConnection."""

    def test_create_connection(self):
        """Test creating connection."""
        conn = DAPConnection(["python", "-m", "debugpy"])
        
        assert conn.adapter_command == ["python", "-m", "debugpy"]


class TestDAPDebugger:
    """Tests for DAPDebugger."""

    def test_create_debugger(self):
        """Test creating debugger."""
        conn = DAPConnection(["echo"])
        debugger = DAPDebugger(conn)
        
        assert debugger.conn is conn
        assert debugger._breakpoints == {}


class TestDAPSession:
    """Tests for DAPSession."""

    def test_create_session(self):
        """Test creating session."""
        conn = DAPConnection(["echo"])
        debugger = DAPDebugger(conn)
        session = DAPSession(debugger)
        
        assert session.debugger is debugger
