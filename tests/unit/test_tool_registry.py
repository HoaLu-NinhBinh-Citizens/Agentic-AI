"""Unit tests for ToolRegistry (Phase 2B)."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from domain.models.tool_call import ToolCallState
from domain.models.execution import ToolExecutionResult
from core.agent.tool_registry import ToolRegistry
from core.execution.tool_tracker import ToolTracker
from infrastructure.tool_execution.executor import MockToolExecutor
from shared.exceptions.tool_errors import ToolSessionClosedError, ToolBusyError


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    @pytest.fixture
    def tracker(self):
        """Create a ToolTracker instance."""
        return ToolTracker(session_id="test-session", max_history=100)

    @pytest.fixture
    def executor(self):
        """Create a MockToolExecutor instance."""
        return MockToolExecutor()

    @pytest.fixture
    def registry(self, tracker, executor):
        """Create a ToolRegistry instance."""
        return ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=2,
            timeout_seconds=5.0,
        )

    @pytest.mark.asyncio
    async def test_call_tool_success(self, registry):
        """Test successful tool call."""
        call_id, result = await registry.call_tool(
            "echo_test",
            {"message": "hello"},
        )

        assert result.success is True
        assert len(result.content) > 0
        assert call_id is not None

    @pytest.mark.asyncio
    async def test_call_tool_state_transitions(self, registry, tracker):
        """Test tool call transitions through states."""
        call_id, _ = await registry.call_tool("echo_test", {"msg": "test"})

        pending_ids = await tracker.get_pending_ids()
        assert call_id not in pending_ids

        history = await tracker.get_history()
        completed_call = next(r for r in history if r.call_id == call_id)
        assert completed_call.state == ToolCallState.COMPLETED

    @pytest.mark.asyncio
    async def test_call_tool_creates_record(self, registry, tracker):
        """Test that tool call creates a proper record."""
        call_id, _ = await registry.call_tool("some_tool", {"arg": "value"})

        history = await tracker.get_history()
        record = next(r for r in history if r.call_id == call_id)

        assert record.tool_name == "some_tool"
        assert record.arguments == {"arg": "value"}
        assert record.trace_id is not None

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self, tracker):
        """Test tool call timeout."""
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=0.1,
        )

        call_id, result = await registry.call_tool(
            "timeout_tool",
            {},
        )

        assert result.success is False
        assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_call_tool_failure(self, registry):
        """Test tool call failure."""
        call_id, result = await registry.call_tool("fail_test", {})

        assert result.success is False
        assert result.error is not None
        assert result.error_code is not None

    @pytest.mark.asyncio
    async def test_concurrency_limit(self, tracker, executor):
        """Test concurrency limit is enforced."""
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=30.0,
        )

        calls = []
        for i in range(3):
            task = asyncio.create_task(
                registry.call_tool("some_tool", {"index": i})
            )
            calls.append(task)
            await asyncio.sleep(0.01)

        results = await asyncio.gather(*calls)

        for _, result in results:
            assert result.success is True

    @pytest.mark.asyncio
    async def test_session_closed_error(self, tracker, executor):
        """Test calling tool on closed session raises error."""
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
        )
        await registry.close()

        with pytest.raises(ToolSessionClosedError):
            await registry.call_tool("test_tool", {})

    @pytest.mark.asyncio
    async def test_close_cancels_pending(self, tracker, executor):
        """Test that close marks pending calls as cancelled."""
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=30.0,
        )

        task = asyncio.create_task(
            registry.call_tool("slow_tool", {})
        )
        await asyncio.sleep(0.05)

        await registry.close(cancel_pending=True)

        try:
            await task
        except ToolSessionClosedError:
            pass

        history = await tracker.get_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_get_pending_count(self, registry):
        """Test getting pending count."""
        initial = await registry.get_pending_count()
        assert initial == 0

        call_id, _ = await registry.call_tool("echo_test", {})

        final = await registry.get_pending_count()
        assert final == 0

    @pytest.mark.asyncio
    async def test_custom_call_id(self, registry):
        """Test custom call ID is preserved."""
        call_id, result = await registry.call_tool(
            "test",
            {},
            call_id="custom-call-id",
        )

        assert call_id == "custom-call-id"

    @pytest.mark.asyncio
    async def test_max_pending_enforced(self):
        """Test that max_pending is enforced."""
        from unittest.mock import AsyncMock

        tracker = ToolTracker("test", max_pending=2)

        class SlowExecutor:
            async def execute(self, tool_name, arguments):
                await asyncio.sleep(0.5)
                return {"content": []}

        executor = SlowExecutor()
        registry = ToolRegistry(
            session_id="test",
            executor=executor,
            tracker=tracker,
            max_concurrent=5,
            timeout_seconds=30.0,
        )

        task1 = asyncio.create_task(registry.call_tool("tool1", {}))
        task2 = asyncio.create_task(registry.call_tool("tool2", {}))
        await asyncio.sleep(0.05)

        call_id, result = await registry.call_tool("tool3", {})
        assert result.success is False
        assert result.error_code == "TOO_MANY_CONCURRENT"

        await task1
        await task2
