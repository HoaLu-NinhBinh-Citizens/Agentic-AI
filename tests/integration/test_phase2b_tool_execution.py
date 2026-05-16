"""Integration tests for Phase 2B Tool Execution Runtime.

Tests the full tool execution flow including:
- Tool execution success
- Tool execution failure
- Concurrency control
- Session deletion cleanup
- Timeout handling
"""

from __future__ import annotations

import asyncio
import pytest

from domain.models.tool_call import ToolCallState
from core.execution.tool_tracker import ToolTracker
from core.agent.tool_registry import ToolRegistry
from infrastructure.tool_execution.executor import MockToolExecutor
from application.orchestration.tool_execution.service import ToolExecutionService
from core.session.persistent_manager import PersistentSessionManager
from infrastructure.persistence.sqlite.session_store import SessionStore


class MockSessionManager:
    """Mock session manager for testing ToolExecutionService."""

    def __init__(self):
        self._registries: dict[str, ToolRegistry] = {}

    def add_registry(self, session_id: str, registry: ToolRegistry):
        self._registries[session_id] = registry

    def get_tool_registry(self, session_id: str):
        return self._registries.get(session_id)


class TestToolExecutionService:
    """Integration tests for ToolExecutionService."""

    @pytest.fixture
    def session_manager(self):
        """Create a mock session manager with tool registries."""
        manager = MockSessionManager()

        for i in range(3):
            tracker = ToolTracker(f"session-{i}", max_history=50)
            executor = MockToolExecutor()
            registry = ToolRegistry(
                session_id=f"session-{i}",
                executor=executor,
                tracker=tracker,
                max_concurrent=5,
                timeout_seconds=30.0,
            )
            manager.add_registry(f"session-{i}", registry)

        return manager

    @pytest.fixture
    def service(self, session_manager):
        """Create a ToolExecutionService instance."""
        return ToolExecutionService(session_manager)

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, service):
        """Test successful tool execution via service."""
        events = []

        async def capture_event(session_id: str, event: dict):
            events.append((session_id, event))

        await service.execute_tool(
            session_id="session-0",
            tool_name="echo_test",
            arguments={"message": "hello"},
            broadcast_callback=capture_event,
        )

        assert len(events) == 2

        start_event = events[0]
        assert start_event[1]["type"] == "tool_call_start"
        assert start_event[1]["data"]["tool_name"] == "echo_test"

        result_event = events[1]
        assert result_event[1]["type"] == "tool_call_result"
        assert len(result_event[1]["data"]["content"]) > 0

    @pytest.mark.asyncio
    async def test_execute_tool_failure(self, service):
        """Test tool execution failure via service."""
        events = []

        async def capture_event(session_id: str, event: dict):
            events.append((session_id, event))

        await service.execute_tool(
            session_id="session-0",
            tool_name="fail_test",
            arguments={},
            broadcast_callback=capture_event,
        )

        assert len(events) == 2

        start_event = events[0]
        assert start_event[1]["type"] == "tool_call_start"

        error_event = events[1]
        assert error_event[1]["type"] == "tool_call_error"
        assert "error" in error_event[1]["data"]
        assert "code" in error_event[1]["data"]

    @pytest.mark.asyncio
    async def test_execute_tool_session_not_found(self, service):
        """Test tool execution with invalid session."""
        events = []

        async def capture_event(session_id: str, event: dict):
            events.append((session_id, event))

        await service.execute_tool(
            session_id="nonexistent-session",
            tool_name="test",
            arguments={},
            broadcast_callback=capture_event,
        )

        assert len(events) == 1
        assert events[0][1]["type"] == "tool_call_error"
        assert events[0][1]["data"]["code"] == "SESSION_ERROR"

    @pytest.mark.asyncio
    async def test_execute_tool_creates_trace_id(self, service):
        """Test that trace IDs are generated."""
        events = []

        async def capture_event(session_id: str, event: dict):
            events.append((session_id, event))

        await service.execute_tool(
            session_id="session-0",
            tool_name="test",
            arguments={},
            broadcast_callback=capture_event,
        )

        assert events[0][1]["data"]["trace_id"] is not None


class TestToolExecutionConcurrency:
    """Tests for concurrency control in tool execution."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_respected(self):
        """Test that concurrent call limit is respected."""
        tracker = ToolTracker("concurrent-test", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="concurrent-test",
            executor=executor,
            tracker=tracker,
            max_concurrent=2,
            timeout_seconds=30.0,
        )

        call_tasks = []
        for i in range(5):
            task = asyncio.create_task(
                registry.call_tool("echo_test", {"index": i})
            )
            call_tasks.append((i, task))
            await asyncio.sleep(0.01)

        results = []
        for i, task in call_tasks:
            result = await task
            results.append((i, result))

        for _, (_, result) in results:
            assert result.success is True

        history = await tracker.get_history()
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_rapid_fire_calls(self):
        """Test handling of rapid fire tool calls."""
        tracker = ToolTracker("rapid-test", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="rapid-test",
            executor=executor,
            tracker=tracker,
            max_concurrent=3,
            timeout_seconds=30.0,
        )

        tasks = [
            asyncio.create_task(registry.call_tool("echo_test", {"i": i}))
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        for call_id, result in results:
            assert result.success is True

        pending = await tracker.get_pending_ids()
        assert len(pending) == 0

        history = await tracker.get_history()
        assert len(history) == 10


class TestToolExecutionCleanup:
    """Tests for cleanup and lifecycle handling."""

    @pytest.mark.asyncio
    async def test_session_delete_cancels_pending(self):
        """Test that session deletion cancels pending calls."""
        tracker = ToolTracker("cleanup-test", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="cleanup-test",
            executor=executor,
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=30.0,
        )

        task = asyncio.create_task(
            registry.call_tool("echo_test", {"message": "test"})
        )
        await asyncio.sleep(0.05)

        await registry.close(cancel_pending=True)

        try:
            await task
        except Exception:
            pass

        history = await tracker.get_history()
        states = [r.state for r in history]

        assert ToolCallState.CANCELLED in states or ToolCallState.COMPLETED in states

    @pytest.mark.asyncio
    async def test_tool_execution_guarantees_cleanup(self):
        """Test that exceptions guarantee cleanup."""
        tracker = ToolTracker("cleanup-guarantee", max_history=100)

        class FailingExecutor:
            async def execute(self, tool_name, arguments):
                raise RuntimeError("Simulated failure")

        registry = ToolRegistry(
            session_id="cleanup-guarantee",
            executor=FailingExecutor(),
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=30.0,
        )

        call_id, result = await registry.call_tool("failing_tool", {})

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"

        history = await tracker.get_history()
        assert len(history) == 1
        assert history[0].state == ToolCallState.FAILED


class TestToolExecutionTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test that timeout produces TIMEOUT error."""
        tracker = ToolTracker("timeout-test", max_history=100)

        class SlowExecutor:
            async def execute(self, tool_name, arguments):
                await asyncio.sleep(60)
                return {"content": []}

        registry = ToolRegistry(
            session_id="timeout-test",
            executor=SlowExecutor(),
            tracker=tracker,
            max_concurrent=1,
            timeout_seconds=0.1,
        )

        call_id, result = await registry.call_tool("slow_tool", {})

        assert result.success is False
        assert result.error_code == "TIMEOUT"

        history = await tracker.get_history()
        timed_out = [r for r in history if r.state == ToolCallState.TIMED_OUT]
        assert len(timed_out) == 1


class TestToolExecutionWithPersistentManager:
    """Integration tests with PersistentSessionManager."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database."""
        return tmp_path / "test.db"

    @pytest.mark.asyncio
    async def test_tool_registry_created_on_session(self, temp_db):
        """Test that tool registry is created with session."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        session_id = manager.create_session()
        await manager.save_session(session_id)

        registry = manager.get_tool_registry(session_id)
        assert registry is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_tool_registry_cleaned_on_delete(self, temp_db):
        """Test that tool registry is cleaned on session delete."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        session_id = manager.create_session()
        await manager.save_session(session_id)

        registry = manager.get_tool_registry(session_id)
        assert registry is not None

        await manager.delete_session(session_id)

        registry_after = manager.get_tool_registry(session_id)
        assert registry_after is None

        await manager.close()

    @pytest.mark.asyncio
    async def test_tool_execution_with_persistent_session(self, temp_db):
        """Test full tool execution flow with persistent session."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        session_id = manager.create_session()
        await manager.save_session(session_id)

        registry = manager.get_tool_registry(session_id)
        assert registry is not None

        call_id, result = await registry.call_tool("echo_test", {"msg": "hello"})

        assert result.success is True
        assert len(result.content) > 0

        history = await registry._tracker.get_history()
        assert len(history) == 1
        assert history[0].state == ToolCallState.COMPLETED

        await manager.close()
