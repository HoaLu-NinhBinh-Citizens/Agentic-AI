"""Unit tests for ToolCallState and ToolCallRecord (Phase 2B)."""

from __future__ import annotations

import pytest
from datetime import datetime

from domain.models.tool_call import ToolCallState, ToolCallRecord


class TestToolCallState:
    """Test suite for ToolCallState enum."""

    def test_all_states_defined(self):
        """Test all expected states are defined."""
        expected = {
            "PENDING",
            "RUNNING",
            "COMPLETED",
            "FAILED",
            "TIMED_OUT",
            "CANCELLED",
            "ORPHANED",
        }
        actual = {s.name for s in ToolCallState}
        assert expected == actual

    def test_state_values(self):
        """Test state values are correct strings."""
        assert ToolCallState.PENDING.value == "pending"
        assert ToolCallState.RUNNING.value == "running"
        assert ToolCallState.COMPLETED.value == "completed"
        assert ToolCallState.FAILED.value == "failed"
        assert ToolCallState.TIMED_OUT.value == "timed_out"
        assert ToolCallState.CANCELLED.value == "cancelled"
        assert ToolCallState.ORPHANED.value == "orphaned"


class TestToolCallRecord:
    """Test suite for ToolCallRecord dataclass."""

    def test_create_record(self):
        """Test creating a basic record."""
        record = ToolCallRecord(
            call_id="call-123",
            session_id="session-456",
            tool_name="test_tool",
            arguments={"arg": "value"},
            state=ToolCallState.PENDING,
        )

        assert record.call_id == "call-123"
        assert record.session_id == "session-456"
        assert record.tool_name == "test_tool"
        assert record.arguments == {"arg": "value"}
        assert record.state == ToolCallState.PENDING
        assert record.trace_id is not None
        assert record.created_at is not None
        assert record.started_at is None
        assert record.completed_at is None
        assert record.duration_ms is None

    def test_create_record_with_optional_fields(self):
        """Test creating a record with optional fields."""
        record = ToolCallRecord(
            call_id="call-123",
            session_id="session-456",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.COMPLETED,
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 0, 1),
            duration_ms=1000.0,
            result_content=[{"type": "text", "text": "result"}],
            trace_id="trace-789",
            parent_call_id="parent-111",
        )

        assert record.started_at == datetime(2024, 1, 1, 12, 0, 0)
        assert record.completed_at == datetime(2024, 1, 1, 12, 0, 1)
        assert record.duration_ms == 1000.0
        assert record.result_content[0]["text"] == "result"
        assert record.trace_id == "trace-789"
        assert record.parent_call_id == "parent-111"

    def test_to_dict(self):
        """Test converting record to dictionary."""
        record = ToolCallRecord(
            call_id="call-123",
            session_id="session-456",
            tool_name="test_tool",
            arguments={"key": "value"},
            state=ToolCallState.RUNNING,
        )

        d = record.to_dict()

        assert d["call_id"] == "call-123"
        assert d["session_id"] == "session-456"
        assert d["tool_name"] == "test_tool"
        assert d["arguments"] == {"key": "value"}
        assert d["state"] == "running"
        assert "created_at" in d
        assert "trace_id" in d

    def test_to_dict_with_completed_state(self):
        """Test to_dict with completed state."""
        record = ToolCallRecord(
            call_id="call-123",
            session_id="session-456",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.COMPLETED,
            completed_at=datetime(2024, 1, 1, 12, 0, 0),
            duration_ms=500.0,
            result_content=[{"type": "text", "text": "done"}],
        )

        d = record.to_dict()

        assert d["state"] == "completed"
        assert d["duration_ms"] == 500.0
        assert d["result_content"][0]["text"] == "done"
        assert d["completed_at"] == "2024-01-01T12:00:00"

    def test_to_dict_with_error(self):
        """Test to_dict with error state."""
        record = ToolCallRecord(
            call_id="call-123",
            session_id="session-456",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.FAILED,
            error_code="TOOL_ERROR",
            error_message="Something went wrong",
        )

        d = record.to_dict()

        assert d["state"] == "failed"
        assert d["error_code"] == "TOOL_ERROR"
        assert d["error_message"] == "Something went wrong"
