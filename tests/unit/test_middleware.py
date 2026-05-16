"""Unit tests for Phase 2C middleware module."""

from __future__ import annotations

import asyncio
import pytest

from domain.models.execution import ExecutionRequest, ExecutionContext, ToolExecutionResult
from application.orchestration.tool_execution.middleware import (
    RateLimitMiddleware,
    RateLimitRules,
    RateLimitConfig,
    SlidingWindowRateLimiter,
    OwnershipMiddleware,
    AuditMiddleware,
    CancellationMiddleware,
    RetryMiddleware,
    Pipeline,
    MiddlewareBuilder,
)


def make_request(
    call_id: str = "call-1",
    tool_name: str = "test_tool",
    session_id: str = "session-1",
    client_id: str = "client-1",
) -> ExecutionRequest:
    """Helper to create test execution request."""
    context = ExecutionContext(
        session_id=session_id,
        trace_id="trace-1",
        client_id=client_id,
    )
    return ExecutionRequest(
        call_id=call_id,
        tool_name=tool_name,
        arguments={},
        context=context,
    )


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = SlidingWindowRateLimiter(max_calls=3, period=10.0)

        assert await limiter.acquire("key-1")
        assert await limiter.acquire("key-1")
        assert await limiter.acquire("key-1")

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self):
        """Test that requests at limit are blocked."""
        limiter = SlidingWindowRateLimiter(max_calls=2, period=10.0)

        assert await limiter.acquire("key-1")
        assert await limiter.acquire("key-1")
        assert not await limiter.acquire("key-1")

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        """Test that different keys have independent limits."""
        limiter = SlidingWindowRateLimiter(max_calls=1, period=10.0)

        assert await limiter.acquire("key-1")
        assert await limiter.acquire("key-2")
        assert not await limiter.acquire("key-1")
        assert not await limiter.acquire("key-2")

    @pytest.mark.asyncio
    async def test_window_expiry(self):
        """Test that old timestamps are expired."""
        limiter = SlidingWindowRateLimiter(max_calls=1, period=0.05)

        assert await limiter.acquire("key-1")
        assert not await limiter.acquire("key-1")

        await asyncio.sleep(0.1)

        assert await limiter.acquire("key-1")

    @pytest.mark.asyncio
    async def test_get_remaining(self):
        """Test getting remaining calls."""
        limiter = SlidingWindowRateLimiter(max_calls=3, period=10.0)

        remaining = await limiter.get_remaining("key-1")
        assert remaining == 3

        await limiter.acquire("key-1")
        remaining = await limiter.get_remaining("key-1")
        assert remaining == 2


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_allows_within_session_limit(self):
        """Test that requests within session limit pass."""
        rules = RateLimitRules(
            per_session=RateLimitConfig(calls=10, period=60.0),
        )
        middleware = RateLimitMiddleware(rules)

        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        for i in range(5):
            request = make_request()
            result = await middleware(request, handler)
            assert result.success, f"Failed at iteration {i}, error: {result.error}"
            assert call_count == i + 1, f"Expected call_count={i+1}, got {call_count}"

    @pytest.mark.asyncio
    async def test_blocks_session_limit(self):
        """Test that session rate limit is enforced."""
        rules = RateLimitRules(
            per_session=RateLimitConfig(calls=2, period=60.0),
        )
        middleware = RateLimitMiddleware(rules)

        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        request1 = make_request()
        result1 = await middleware(request1, handler)
        assert result1.success
        assert call_count == 1

        request2 = make_request()
        result2 = await middleware(request2, handler)
        assert result2.success
        assert call_count == 2

        request3 = make_request()
        result3 = await middleware(request3, handler)
        assert not result3.success
        assert result3.error_code == "RATE_LIMITED"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_per_tool_limits(self):
        """Test per-tool rate limits."""
        rules = RateLimitRules(
            per_session=RateLimitConfig(calls=100, period=60.0),
            per_tool={
                "specific_tool": RateLimitConfig(calls=1, period=60.0),
            },
        )
        middleware = RateLimitMiddleware(rules)

        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        request1 = make_request(tool_name="specific_tool")
        result1 = await middleware(request1, handler)
        assert result1.success
        assert call_count == 1

        request2 = make_request(tool_name="specific_tool")
        result2 = await middleware(request2, handler)
        assert not result2.success
        assert result2.error_code == "RATE_LIMITED"


class TestOwnershipMiddleware:
    """Tests for OwnershipMiddleware."""

    @pytest.mark.asyncio
    async def test_passes_through(self):
        """Test that middleware passes through to handler."""
        middleware = OwnershipMiddleware()
        request = make_request(client_id="client-1")
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await middleware(request, handler)
        assert result.success
        assert call_count == 1


class TestAuditMiddleware:
    """Tests for AuditMiddleware."""

    @pytest.mark.asyncio
    async def test_logs_execution(self):
        """Test that middleware logs execution."""
        middleware = AuditMiddleware()
        request = make_request()
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await middleware(request, handler)
        assert result.success
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_logs_failure(self):
        """Test that middleware logs failures."""
        middleware = AuditMiddleware()
        request = make_request()

        async def handler(req):
            return ToolExecutionResult.error_result(
                error="Test error",
                error_code="TEST_ERROR",
            )

        result = await middleware(request, handler)
        assert not result.success
        assert result.error_code == "TEST_ERROR"
        assert result.error == "Test error"


class TestCancellationMiddleware:
    """Tests for CancellationMiddleware."""

    @pytest.mark.asyncio
    async def test_creates_token_if_none(self):
        """Test that middleware creates token if none exists."""
        from core.execution.cancellation import CancellationToken

        middleware = CancellationMiddleware()
        request = make_request()
        assert request.cancellation_token is None
        received_request = None

        async def handler(req):
            nonlocal received_request
            received_request = req
            assert req.cancellation_token is not None
            assert isinstance(req.cancellation_token, CancellationToken)
            return ToolExecutionResult.success_result(content=[])

        await middleware(request, handler)
        assert received_request is not None

    @pytest.mark.asyncio
    async def test_preserves_existing_token(self):
        """Test that middleware preserves existing token."""
        from core.execution.cancellation import CancellationToken

        middleware = CancellationMiddleware()
        existing_token = CancellationToken()
        request = make_request().with_cancellation_token(existing_token)
        received_request = None

        async def handler(req):
            nonlocal received_request
            received_request = req
            assert req.cancellation_token is existing_token
            return ToolExecutionResult.success_result(content=[])

        await middleware(request, handler)
        assert received_request is not None
        assert received_request.cancellation_token is existing_token


class TestRetryMiddleware:
    """Tests for RetryMiddleware."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Test that successful execution returns immediately."""
        middleware = RetryMiddleware(max_attempts=3)
        request = make_request()
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await middleware(request, handler)
        assert result.success
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self):
        """Test that retryable errors trigger retry."""
        middleware = RetryMiddleware(
            max_attempts=3,
            base_delay=0.01,
            retryable_codes=["MCP_ERROR"],
        )
        request = make_request()
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ToolExecutionResult.error_result(
                    error="Transient error",
                    error_code="MCP_ERROR",
                )
            return ToolExecutionResult.success_result(content=[])

        result = await middleware(request, handler)
        assert result.success
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_gives_up_on_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retry."""
        middleware = RetryMiddleware(
            max_attempts=3,
            base_delay=0.01,
            retryable_codes=["MCP_ERROR"],
        )
        request = make_request()
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.error_result(
                error="Permanent error",
                error_code="PERMISSION_DENIED",
            )

        result = await middleware(request, handler)
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_stops_at_max_attempts(self):
        """Test that retry stops at max attempts."""
        middleware = RetryMiddleware(
            max_attempts=3,
            base_delay=0.01,
            retryable_codes=["MCP_ERROR"],
        )
        request = make_request()
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.error_result(
                error="Always fails",
                error_code="MCP_ERROR",
            )

        result = await middleware(request, handler)
        assert not result.success
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_aborts_on_cancellation(self):
        """Test that retry aborts when cancelled."""
        from core.execution.cancellation import CancellationToken

        middleware = RetryMiddleware(
            max_attempts=10,
            base_delay=1.0,
            retryable_codes=["MCP_ERROR"],
        )

        token = CancellationToken()
        token.cancel()  # Cancel immediately

        request = make_request().with_cancellation_token(token)
        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.error_result(
                error="Would retry",
                error_code="MCP_ERROR",
            )

        result = await middleware(request, handler)
        assert not result.success
        assert result.error_code == "CANCELLED"
        assert call_count == 0  # Never executed because already cancelled

    @pytest.mark.asyncio
    async def test_retry_count_increments(self):
        """Test that retry_count is incremented on each attempt."""
        middleware = RetryMiddleware(
            max_attempts=3,
            base_delay=0.01,
            retryable_codes=["MCP_ERROR"],
        )
        request = make_request()
        retry_counts = []

        async def handler(req):
            retry_counts.append(req.retry_count)
            return ToolExecutionResult.error_result(
                error="Fail",
                error_code="MCP_ERROR",
            )

        await middleware(request, handler)

        assert retry_counts == [0, 1, 2]  # 3 attempts with retry_count 0, 1, 2


class TestPipeline:
    """Tests for Pipeline."""

    @pytest.mark.asyncio
    async def test_executes_middlewares_in_order(self):
        """Test that middlewares execute in order."""
        order = []

        async def middleware_a(request, next_handler):
            order.append("A_before")
            result = await next_handler(request)
            order.append("A_after")
            return result

        async def middleware_b(request, next_handler):
            order.append("B_before")
            result = await next_handler(request)
            order.append("B_after")
            return result

        pipeline = Pipeline([middleware_a, middleware_b])
        request = make_request()
        call_count = 0

        async def final_handler(req):
            nonlocal call_count
            order.append("handler")
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await pipeline.execute(request, final_handler)
        assert result.success

        expected = ["A_before", "B_before", "handler", "B_after", "A_after"]
        assert order == expected

    @pytest.mark.asyncio
    async def test_empty_pipeline(self):
        """Test pipeline with no middlewares."""
        pipeline = Pipeline([])
        request = make_request()
        call_count = 0

        async def final_handler(req):
            nonlocal call_count
            call_count += 1
            return ToolExecutionResult.success_result(content=[])

        result = await pipeline.execute(request, final_handler)
        assert result.success
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_pipeline_with_modifying_middleware(self):
        """Test that middleware can modify request and pass to next."""
        order = []

        async def modifier_middleware(request, next_handler):
            order.append("modifier_before")
            modified_request = request.with_retry_count(99)
            result = await next_handler(modified_request)
            order.append("modifier_after")
            return result

        pipeline = Pipeline([modifier_middleware])
        request = make_request()
        received_retry_count = None

        async def final_handler(req):
            nonlocal received_retry_count
            order.append("final")
            received_retry_count = req.retry_count
            return ToolExecutionResult.success_result(content=[])

        result = await pipeline.execute(request, final_handler)
        assert result.success
        assert received_retry_count == 99
        assert order == ["modifier_before", "final", "modifier_after"]


class TestMiddlewareBuilder:
    """Tests for MiddlewareBuilder."""

    def test_add_middleware(self):
        """Test adding middleware by instance."""
        builder = MiddlewareBuilder()

        async def custom_middleware(request, next_handler):
            return await next_handler()

        builder.add(custom_middleware)
        pipeline = builder.build()

        assert len(pipeline._middlewares) == 1

    def test_add_by_name_rate_limit(self):
        """Test adding rate_limit middleware by name."""
        builder = MiddlewareBuilder()
        rules = RateLimitRules()

        builder.add_by_name("rate_limit", rules)
        pipeline = builder.build()

        assert len(pipeline._middlewares) == 1

    def test_add_by_name_retry(self):
        """Test adding retry middleware by name."""
        builder = MiddlewareBuilder()

        builder.add_by_name("retry", {"max_attempts": 5})
        pipeline = builder.build()

        assert len(pipeline._middlewares) == 1

    def test_add_by_name_unknown(self):
        """Test adding unknown middleware raises error."""
        builder = MiddlewareBuilder()

        with pytest.raises(ValueError, match="Unknown middleware"):
            builder.add_by_name("unknown_middleware")

    def test_chaining(self):
        """Test builder method chaining."""
        builder = MiddlewareBuilder()

        builder.add_by_name("ownership")
        builder.add_by_name("audit")
        pipeline = builder.build()

        assert len(pipeline._middlewares) == 2
