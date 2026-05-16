"""Unit tests for ToolTracker (Phase 2B)."""

from __future__ import annotations

import asyncio
import pytest

from domain.models.tool_call import (
    ToolCallRecord,
    ToolCallState,
    InvalidStateTransitionError,
)
from core.execution.tool_tracker import ToolTracker


class TestToolTracker:
    """Test suite for ToolTracker."""

    @pytest.fixture
    def tracker(self):
        """Create a ToolTracker instance."""
        return ToolTracker(session_id="test-session", max_history=5)

    @pytest.mark.asyncio
    async def test_add_pending(self, tracker):
        """Test adding a pending tool call."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={"arg": "value"},
            state=ToolCallState.PENDING,
        )

        await tracker.add_pending(record)

        pending_ids = await tracker.get_pending_ids()
        assert "call-1" in pending_ids

    @pytest.mark.asyncio
    async def test_update_state_to_running(self, tracker):
        """Test updating state to RUNNING."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        result = await tracker.update_state("call-1", ToolCallState.RUNNING)

        assert result is True
        pending_ids = await tracker.get_pending_ids()
        assert "call-1" in pending_ids

    @pytest.mark.asyncio
    async def test_update_state_to_completed_moves_to_history(self, tracker):
        """Test that COMPLETED state moves record to history (via RUNNING)."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        await tracker.update_state("call-1", ToolCallState.RUNNING)
        result = await tracker.update_state("call-1", ToolCallState.COMPLETED)

        assert result is True
        pending_ids = await tracker.get_pending_ids()
        assert "call-1" not in pending_ids

        history = await tracker.get_history()
        assert len(history) == 1
        assert history[0].call_id == "call-1"
        assert history[0].state == ToolCallState.COMPLETED

    @pytest.mark.asyncio
    async def test_update_state_to_failed_moves_to_history(self, tracker):
        """Test that FAILED state moves record to history (via RUNNING)."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        await tracker.update_state("call-1", ToolCallState.RUNNING)
        result = await tracker.update_state(
            "call-1",
            ToolCallState.FAILED,
            error_message="Tool execution failed",
        )

        assert result is True
        pending_ids = await tracker.get_pending_ids()
        assert "call-1" not in pending_ids

        history = await tracker.get_history()
        assert len(history) == 1
        assert history[0].state == ToolCallState.FAILED
        assert history[0].error_message == "Tool execution failed"

    @pytest.mark.asyncio
    async def test_update_state_nonexistent_call(self, tracker):
        """Test updating nonexistent call returns False."""
        result = await tracker.update_state("nonexistent", ToolCallState.COMPLETED)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_pending_ids(self, tracker):
        """Test getting pending call IDs."""
        for i in range(3):
            record = ToolCallRecord(
                call_id=f"call-{i}",
                session_id="test-session",
                tool_name="test_tool",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record)

        pending_ids = await tracker.get_pending_ids()
        assert len(pending_ids) == 3
        assert "call-0" in pending_ids
        assert "call-1" in pending_ids
        assert "call-2" in pending_ids

    @pytest.mark.asyncio
    async def test_max_history_limit(self, tracker):
        """Test that history respects max_history limit."""
        for i in range(10):
            record = ToolCallRecord(
                call_id=f"call-{i}",
                session_id="test-session",
                tool_name="test_tool",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record)
            await tracker.update_state(f"call-{i}", ToolCallState.RUNNING)
            await tracker.update_state(f"call-{i}", ToolCallState.COMPLETED)

        history = await tracker.get_history()
        assert len(history) == 5
        assert history[0].call_id == "call-5"
        assert history[4].call_id == "call-9"

    @pytest.mark.asyncio
    async def test_close_marks_pending_as_orphaned(self, tracker):
        """Test that close marks pending calls as orphaned."""
        for i in range(3):
            record = ToolCallRecord(
                call_id=f"call-{i}",
                session_id="test-session",
                tool_name="test_tool",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record)

        await tracker.close(mark_orphaned=True)

        pending_ids = await tracker.get_pending_ids()
        assert len(pending_ids) == 0

        history = await tracker.get_history()
        assert len(history) == 3
        for record in history:
            assert record.state == ToolCallState.ORPHANED

    @pytest.mark.asyncio
    async def test_get_pending_count(self, tracker):
        """Test getting pending count."""
        assert await tracker.get_pending_count() == 0

        for i in range(3):
            record = ToolCallRecord(
                call_id=f"call-{i}",
                session_id="test-session",
                tool_name="test_tool",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record)

        assert await tracker.get_pending_count() == 3

    @pytest.mark.asyncio
    async def test_get_pending_record(self, tracker):
        """Test getting a specific pending record."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={"key": "value"},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        found = await tracker.get_pending_record("call-1")
        assert found is not None
        assert found.call_id == "call-1"
        assert found.arguments["key"] == "value"

        not_found = await tracker.get_pending_record("nonexistent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_duration_ms_calculation(self, tracker):
        """Test that duration_ms is calculated when started_at is set before completion."""
        from datetime import datetime, timezone

        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        await tracker.update_state("call-1", ToolCallState.RUNNING)
        record.started_at = datetime.now(timezone.utc)
        await tracker.update_state("call-1", ToolCallState.COMPLETED)

        history = await tracker.get_history()
        assert len(history) == 1
        assert history[0].duration_ms is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_error(self, tracker):
        """Test that invalid state transitions raise errors."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        with pytest.raises(InvalidStateTransitionError):
            await tracker.update_state("call-1", ToolCallState.COMPLETED)

    @pytest.mark.asyncio
    async def test_transition_record_helper(self, tracker):
        """Test the transition_record helper method."""
        record = ToolCallRecord(
            call_id="call-1",
            session_id="test-session",
            tool_name="test_tool",
            arguments={},
            state=ToolCallState.PENDING,
        )
        await tracker.add_pending(record)

        result = await tracker.transition_record("call-1", ToolCallState.RUNNING)
        assert result is True

        result = await tracker.transition_record("call-1", ToolCallState.COMPLETED)
        assert result is True
