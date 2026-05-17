"""Unit tests for ExecutionEngine."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.router.execution_engine import (
    ExecutionEngine,
    HandlerConfig,
    LambdaHandler,
    create_handler,
)
from src.infrastructure.router.observation.health_monitor import HealthMonitor
from src.infrastructure.router.types import (
    IntentConfig,
    Request,
    RequestContext,
    RouteResult,
    RouterConfig,
    RoutingType,
    Snapshot,
)


class TestExecutionEngineBasic:
    """Test basic ExecutionEngine functionality."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor(window_size=100)

    @pytest.fixture
    def execution_engine(
        self,
        health_monitor: HealthMonitor,
    ) -> ExecutionEngine:
        """Create execution engine."""
        return ExecutionEngine(health_monitor=health_monitor)

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler."""
        return AsyncMock(return_value={"result": "success"})

    @pytest.fixture
    def snapshot(self) -> Snapshot:
        """Create test snapshot."""
        return Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

    @pytest.fixture
    def context(self, snapshot: Snapshot) -> RequestContext:
        """Create test context."""
        return RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test query"),
        )

    def test_register_handler(self, execution_engine: ExecutionEngine, mock_handler):
        """Test handler registration."""
        execution_engine.register_handler("test_intent", mock_handler)

        assert execution_engine.has_handler("test_intent")
        assert "test_intent" in execution_engine.get_registered_intents()

    def test_unregister_handler(self, execution_engine: ExecutionEngine, mock_handler):
        """Test handler unregistration."""
        execution_engine.register_handler("test_intent", mock_handler)
        execution_engine.unregister_handler("test_intent")

        assert not execution_engine.has_handler("test_intent")

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
        mock_handler,
    ):
        """Test successful execution."""
        execution_engine.register_handler("test_intent", mock_handler)

        route_result = RouteResult(
            intent="test_intent",
            confidence=0.9,
            routing_type=RoutingType.RULE,
        )

        result = await execution_engine.execute(context, route_result)

        assert result.success is True
        assert result.intent == "test_intent"
        assert result.result == {"result": "success"}
        assert result.error is None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_no_handler(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
    ):
        """Test execution with no handler."""
        route_result = RouteResult(
            intent="nonexistent_intent",
            confidence=0.9,
        )

        result = await execution_engine.execute(context, route_result)

        assert result.success is False
        assert result.error == "No handler registered for intent: nonexistent_intent"

    @pytest.mark.asyncio
    async def test_execute_with_timeout(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
    ):
        """Test execution with timeout."""
        async def slow_handler(ctx):
            await asyncio.sleep(2)
            return "done"

        execution_engine.register_handler(
            "slow_intent",
            slow_handler,
            config=HandlerConfig(timeout_seconds=0.1),
        )

        route_result = RouteResult(
            intent="slow_intent",
            confidence=0.9,
        )

        result = await execution_engine.execute(context, route_result)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_exception(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
    ):
        """Test execution with exception."""
        async def failing_handler(ctx):
            raise ValueError("Handler failed")

        execution_engine.register_handler("failing_intent", failing_handler)

        route_result = RouteResult(
            intent="failing_intent",
            confidence=0.9,
        )

        result = await execution_engine.execute(context, route_result)

        assert result.success is False
        assert "Handler failed" in result.error

    @pytest.mark.asyncio
    async def test_health_tracking_on_success(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
        mock_handler,
        health_monitor: HealthMonitor,
    ):
        """Test that health is tracked on success."""
        execution_engine.register_handler("tracked_intent", mock_handler)

        route_result = RouteResult(
            intent="tracked_intent",
            confidence=0.9,
        )

        await execution_engine.execute(context, route_result)

        # Check health monitor recorded the success
        rate = await health_monitor.get_success_rate("tracked_intent")
        assert rate == 1.0

    @pytest.mark.asyncio
    async def test_health_tracking_on_failure(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
        health_monitor: HealthMonitor,
    ):
        """Test that health is tracked on failure."""
        async def failing_handler(ctx):
            raise ValueError("Failed")

        execution_engine.register_handler("failing_intent", failing_handler)

        route_result = RouteResult(
            intent="failing_intent",
            confidence=0.9,
        )

        await execution_engine.execute(context, route_result)
        await execution_engine.execute(context, route_result)

        # Check health monitor recorded failures
        rate = await health_monitor.get_success_rate("failing_intent")
        assert rate == 0.0


class TestParameterExtraction:
    """Test parameter extraction for handler configuration."""

    def test_handler_config_defaults(self):
        """Test handler config defaults."""
        config = HandlerConfig()

        assert config.timeout_seconds == 30.0
        assert config.retry_on_failure is True
        assert config.max_retries == 3

    def test_handler_config_custom(self):
        """Test custom handler config."""
        config = HandlerConfig(
            timeout_seconds=60.0,
            retry_on_failure=False,
            max_retries=5,
        )

        assert config.timeout_seconds == 60.0
        assert config.retry_on_failure is False
        assert config.max_retries == 5

    def test_register_with_custom_config(self):
        """Test registration with custom config."""
        engine = ExecutionEngine()
        config = HandlerConfig(timeout_seconds=10.0)
        mock_handler = AsyncMock(return_value="result")

        engine.register_handler("custom_intent", mock_handler, config)

        assert engine.has_handler("custom_intent")


class TestLambdaHandler:
    """Test LambdaHandler wrapper."""

    @pytest.mark.asyncio
    async def test_lambda_handler_calls_function(self):
        """Test that LambdaHandler calls the wrapped function."""
        called = False

        async def my_handler(ctx):
            nonlocal called
            called = True
            return "result"

        wrapper = LambdaHandler(my_handler)
        await wrapper(MagicMock())

        assert called

    @pytest.mark.asyncio
    async def test_create_handler_utility(self):
        """Test create_handler utility function."""
        async def handler_func(ctx):
            return {"data": "value"}

        handler = create_handler(handler_func)

        assert isinstance(handler, LambdaHandler)
        result = await handler(MagicMock())
        assert result == {"data": "value"}


class TestExecutionWithMultipleHandlers:
    """Test execution with multiple registered handlers."""

    @pytest.fixture
    def execution_engine(self) -> ExecutionEngine:
        """Create execution engine."""
        return ExecutionEngine()

    @pytest.fixture
    def snapshot(self) -> Snapshot:
        """Create test snapshot."""
        return Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

    @pytest.fixture
    def context(self, snapshot: Snapshot) -> RequestContext:
        """Create test context."""
        return RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test"),
        )

    @pytest.mark.asyncio
    async def test_multiple_handlers_registration(self, execution_engine: ExecutionEngine):
        """Test multiple handlers can be registered."""
        async def handler_a(ctx): return "a"
        async def handler_b(ctx): return "b"
        async def handler_c(ctx): return "c"

        execution_engine.register_handler("intent_a", handler_a)
        execution_engine.register_handler("intent_b", handler_b)
        execution_engine.register_handler("intent_c", handler_c)

        intents = execution_engine.get_registered_intents()
        assert len(intents) == 3
        assert "intent_a" in intents
        assert "intent_b" in intents
        assert "intent_c" in intents

    @pytest.mark.asyncio
    async def test_dispatch_to_correct_handler(
        self,
        execution_engine: ExecutionEngine,
        context: RequestContext,
    ):
        """Test that correct handler is dispatched."""
        results = {}

        async def handler_a(ctx):
            results["a"] = True
            return "result_a"

        async def handler_b(ctx):
            results["b"] = True
            return "result_b"

        execution_engine.register_handler("intent_a", handler_a)
        execution_engine.register_handler("intent_b", handler_b)

        # Dispatch to intent_a
        result_a = await execution_engine.execute(
            context,
            RouteResult(intent="intent_a", confidence=0.9),
        )
        assert result_a.success is True
        assert result_a.result == "result_a"
        assert results["a"] is True
        assert results.get("b") is None

        # Dispatch to intent_b
        result_b = await execution_engine.execute(
            context,
            RouteResult(intent="intent_b", confidence=0.9),
        )
        assert result_b.success is True
        assert result_b.result == "result_b"
        assert results["b"] is True

    @pytest.mark.asyncio
    async def test_handler_override(self, execution_engine: ExecutionEngine):
        """Test that handlers can be overridden."""
        call_count = [0]

        async def handler_v1(ctx):
            call_count[0] += 1
            return "v1"

        async def handler_v2(ctx):
            call_count[0] += 1
            return "v2"

        execution_engine.register_handler("intent", handler_v1)
        execution_engine.register_handler("intent", handler_v2)

        # Only v2 should be called (override)
        context = RequestContext.create(
            snapshot=Snapshot(
                snapshot_id="test",
                config=RouterConfig(),
                index=MagicMock(),
                frequency_version=1,
                freq_snapshot_time=0.0,
                created_at=0.0,
            ),
            request=Request(query="test"),
        )

        result = await execution_engine.execute(
            context,
            RouteResult(intent="intent", confidence=0.9),
        )

        assert result.success is True
        assert result.result == "v2"
        assert call_count[0] == 1


class TestExecutionLatency:
    """Test execution latency tracking."""

    @pytest.mark.asyncio
    async def test_latency_tracked_on_success(self):
        """Test that latency is tracked on successful execution."""
        engine = ExecutionEngine()

        async def quick_handler(ctx):
            await asyncio.sleep(0.05)  # 50ms
            return "done"

        engine.register_handler("quick", quick_handler)

        context = RequestContext.create(
            snapshot=Snapshot(
                snapshot_id="test",
                config=RouterConfig(),
                index=MagicMock(),
                frequency_version=1,
                freq_snapshot_time=0.0,
                created_at=0.0,
            ),
            request=Request(query="test"),
        )

        result = await engine.execute(
            context,
            RouteResult(intent="quick", confidence=0.9),
        )

        assert result.latency_ms >= 50  # At least 50ms
        assert result.latency_ms < 1000  # But less than 1 second

    @pytest.mark.asyncio
    async def test_latency_tracked_on_timeout(self):
        """Test that latency is tracked on timeout."""
        engine = ExecutionEngine()

        async def slow_handler(ctx):
            await asyncio.sleep(2)
            return "done"

        engine.register_handler("slow", slow_handler, HandlerConfig(timeout_seconds=0.1))

        context = RequestContext.create(
            snapshot=Snapshot(
                snapshot_id="test",
                config=RouterConfig(),
                index=MagicMock(),
                frequency_version=1,
                freq_snapshot_time=0.0,
                created_at=0.0,
            ),
            request=Request(query="test"),
        )

        result = await engine.execute(
            context,
            RouteResult(intent="slow", confidence=0.9),
        )

        assert result.success is False
        assert result.latency_ms >= 100  # At least timeout duration
        assert result.latency_ms < 2000  # But completed within reasonable time


class TestExecutionWithoutHealthMonitor:
    """Test execution engine without health monitor."""

    @pytest.mark.asyncio
    async def test_works_without_health_monitor(self):
        """Test that engine works without health monitor."""
        engine = ExecutionEngine()  # No health monitor

        async def my_handler(ctx):
            return "success"

        engine.register_handler("test", my_handler)

        context = RequestContext.create(
            snapshot=Snapshot(
                snapshot_id="test",
                config=RouterConfig(),
                index=MagicMock(),
                frequency_version=1,
                freq_snapshot_time=0.0,
                created_at=0.0,
            ),
            request=Request(query="test"),
        )

        result = await engine.execute(
            context,
            RouteResult(intent="test", confidence=0.9),
        )

        assert result.success is True
        assert result.result == "success"
