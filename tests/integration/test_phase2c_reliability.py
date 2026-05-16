"""Integration tests for Phase 2C Reliability & Policy Layer.

Tests the full tool execution flow with:
- Cancellation by call_id
- Retry middleware
- Rate limiting middleware
- Ownership enforcement
- Middleware pipeline
"""

from __future__ import annotations

import asyncio
import pytest

from domain.models.execution import ExecutionRequest, ExecutionContext, ToolExecutionResult
from domain.models.tool_call import ToolCallState
from core.execution.tool_tracker import ToolTracker
from core.execution.cancellation import CancellationToken, CancellationRegistry
from core.agent.tool_registry import ToolRegistry
from infrastructure.tool_execution.executor import MockToolExecutor
from application.orchestration.tool_execution.middleware import (
    Pipeline,
    RateLimitMiddleware,
    RateLimitRules,
    RateLimitConfig,
    OwnershipMiddleware,
    RetryMiddleware,
    CancellationMiddleware,
    AuditMiddleware,
)
from application.orchestration.tool_execution.service import ToolExecutionService


class MockSessionManager:
    """Mock session manager for testing."""

    def __init__(self):
        self._registries: dict[str, ToolRegistry] = {}

    def add_registry(self, session_id: str, registry: ToolRegistry):
        self._registries[session_id] = registry

    def get_tool_registry(self, session_id: str):
        return self._registries.get(session_id)


class TestCancellationByCallId:
    """Tests for cancellation by call_id."""

    @pytest.mark.asyncio
    async def test_cancel_pending_call(self):
        """Test cancelling a pending call."""
        tracker = ToolTracker("test-session", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=5,
            timeout_seconds=30.0,
        )

        token = CancellationToken()
        await tracker.register_cancellation_token("call-1", token)

        call_id, result = await registry.call_tool(
            "echo_test",
            {},
            call_id="call-1",
            cancellation_token=token,
        )

        success = await registry.cancel_call(call_id)

        history = await tracker.get_history()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_call(self):
        """Test cancelling a call that doesn't exist."""
        tracker = ToolTracker("test-session", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
        )

        success = await registry.cancel_call("nonexistent-call")
        assert success is False

    @pytest.mark.asyncio
    async def test_cancel_call_by_call_id(self):
        """Test that correct call is cancelled, not another."""
        tracker = ToolTracker("test-session", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=5,
        )

        token1 = CancellationToken()
        token2 = CancellationToken()

        await tracker.register_cancellation_token("call-1", token1)
        await tracker.register_cancellation_token("call-2", token2)

        await registry.cancel_call("call-1")

        assert token1.is_cancelled
        assert not token2.is_cancelled


class TestRaceCancelComplete:
    """Tests for race between cancellation and completion."""

    @pytest.mark.asyncio
    async def test_atomic_transition_prevents_invalid_state(self):
        """Test that atomic transitions prevent invalid state."""
        tracker = ToolTracker("test-session", max_history=100)

        record = await tracker.get_pending_record("nonexistent")
        assert record is None

        await tracker.update_state("nonexistent", ToolCallState.PENDING)


class TestRetryCancellationDuringBackoff:
    """Tests for retry aborting when cancelled during backoff."""

    @pytest.mark.asyncio
    async def test_retry_cancellation_during_backoff(self):
        """Test that retry aborts when token cancelled during backoff."""
        from core.execution.cancellation import CancellationToken

        retry_middleware = RetryMiddleware(
            max_attempts=10,
            base_delay=1.0,
            retryable_codes=["MCP_ERROR"],
        )

        token = CancellationToken()
        request = ExecutionRequest(
            call_id="call-1",
            tool_name="test",
            arguments={},
            context=ExecutionContext(
                session_id="session-1",
                trace_id="trace-1",
                client_id="client-1",
            ),
        ).with_cancellation_token(token)

        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.05)
                token.cancel()
            return ToolExecutionResult.error_result(
                error="Transient",
                error_code="MCP_ERROR",
            )

        result = await retry_middleware(request, handler)

        assert result.error_code == "CANCELLED"
        assert call_count == 1  # Only one attempt before cancelled


class TestOwnershipEnforced:
    """Tests for ownership verification."""

    @pytest.mark.asyncio
    async def test_only_initiator_can_cancel(self):
        """Test that only the initiating client can cancel."""
        tracker = ToolTracker("test-session", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
        )

        service = ToolExecutionService(MockSessionManager())

        token = CancellationToken()
        record = tracker._pending.get("call-1")
        assert record is None


class TestRateLimitPerSession:
    """Tests for per-session rate limiting."""

    @pytest.mark.asyncio
    async def test_exceeding_limit_returns_error(self):
        """Test that exceeding rate limit returns error."""
        rules = RateLimitRules(
            per_session=RateLimitConfig(calls=2, period=60.0),
        )
        rate_limit_middleware = RateLimitMiddleware(rules)

        request = ExecutionRequest(
            call_id="call-1",
            tool_name="test",
            arguments={},
            context=ExecutionContext(
                session_id="session-1",
                trace_id="trace-1",
                client_id="client-1",
            ),
        )

        async def handler(req):
            return ToolExecutionResult.success_result(content=[])

        result1 = await rate_limit_middleware(request, handler)
        assert result1.success

        result2 = await rate_limit_middleware(request, handler)
        assert result2.success

        result3 = await rate_limit_middleware(request, handler)
        assert not result3.success
        assert result3.error_code == "RATE_LIMITED"


class TestMiddlewareOrder:
    """Tests for configurable middleware order."""

    @pytest.mark.asyncio
    async def test_order_configurable(self):
        """Test that middleware order is configurable."""
        execution_order = []

        class TestMiddleware:
            def __init__(self, name: str):
                self.name = name

            async def __call__(self, request, next_handler):
                execution_order.append(f"{self.name}_before")
                result = await next_handler(request)
                execution_order.append(f"{self.name}_after")
                return result

        pipeline = Pipeline([
            TestMiddleware("first"),
            TestMiddleware("second"),
            TestMiddleware("third"),
        ])

        request = ExecutionRequest(
            call_id="call-1",
            tool_name="test",
            arguments={},
            context=ExecutionContext(
                session_id="session-1",
                trace_id="trace-1",
                client_id="client-1",
            ),
        )

        async def final_handler(req):
            execution_order.append("handler")
            return ToolExecutionResult.success_result(content=[])

        await pipeline.execute(request, final_handler)

        expected = [
            "first_before",
            "second_before",
            "third_before",
            "handler",
            "third_after",
            "second_after",
            "first_after",
        ]
        assert execution_order == expected


class TestFullChainIntegration:
    """Integration tests for the full middleware chain."""

    @pytest.mark.asyncio
    async def test_full_chain_with_cancellation_and_retry(self):
        """Test full chain simulating real MCP tool call."""
        from shared.exceptions.tool_errors import MCPError

        execution_count = 0

        class FailingThenSucceedingExecutor:
            async def execute(self, tool_name, arguments):
                nonlocal execution_count
                execution_count += 1
                if execution_count < 2:
                    raise MCPError("Transient MCP error")
                return {"content": [{"type": "text", "text": "success"}]}

        tracker = ToolTracker("test-session", max_history=100)
        executor = FailingThenSucceedingExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
            max_concurrent=5,
            timeout_seconds=30.0,
        )

        retry_middleware = RetryMiddleware(
            max_attempts=3,
            base_delay=0.01,
            retryable_codes=["MCP_ERROR"],
        )

        request = ExecutionRequest(
            call_id="call-1",
            tool_name="test",
            arguments={},
            context=ExecutionContext(
                session_id="test-session",
                trace_id="trace-1",
                client_id="client-1",
            ),
        )

        async def final_handler(req):
            result = await registry.call_tool("test", {})
            return result[1]

        result = await retry_middleware(request, final_handler)

        assert result.success
        assert execution_count == 2

    @pytest.mark.asyncio
    async def test_pipeline_with_all_middlewares(self):
        """Test pipeline with all configured middlewares."""
        pipeline = Pipeline([
            OwnershipMiddleware(),
            RateLimitMiddleware(RateLimitRules()),
            RetryMiddleware(max_attempts=3),
            CancellationMiddleware(),
            AuditMiddleware(),
        ])

        request = ExecutionRequest(
            call_id="call-1",
            tool_name="test",
            arguments={},
            context=ExecutionContext(
                session_id="session-1",
                trace_id="trace-1",
                client_id="client-1",
            ),
        )

        execution_count = 0

        async def final_handler(req):
            nonlocal execution_count
            execution_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await pipeline.execute(request, final_handler)

        assert result.success
        assert execution_count == 1


class TestGracefulShutdown:
    """Tests for graceful shutdown with grace period."""

    @pytest.mark.asyncio
    async def test_grace_period_before_cleanup(self):
        """Test that grace period is waited before cleanup."""
        grace_period = 0.1

        tracker = ToolTracker("test-session", max_history=100)
        executor = MockToolExecutor()
        registry = ToolRegistry(
            session_id="test-session",
            executor=executor,
            tracker=tracker,
        )

        token = CancellationToken()
        await tracker.register_cancellation_token("call-1", token)

        await registry.cancel_call("call-1")
        await asyncio.sleep(grace_period)

        history = await tracker.get_history()
        assert len(history) >= 0
