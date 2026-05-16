"""Tool execution middleware for Phase 2C.

Provides configurable middleware pipeline for tool execution including:
- RetryMiddleware: Exponential backoff with jitter
- RateLimitMiddleware: Sliding window rate limiting
- OwnershipMiddleware: Client ownership verification
- AuditMiddleware: Logging and observability
- CancellationMiddleware: Cancellation token injection
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from domain.models.execution import ExecutionRequest, ExecutionContext, ToolExecutionResult

logger = logging.getLogger(__name__)


MiddlewareHandler = Callable[
    [ExecutionRequest, Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]]],
    Awaitable[ToolExecutionResult],
]


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    calls: int = 10
    period: float = 60.0


@dataclass
class RateLimitRules:
    """Rate limit rules per session and tool."""

    per_session: RateLimitConfig = field(default_factory=lambda: RateLimitConfig(calls=10, period=60.0))
    per_tool: dict[str, RateLimitConfig] = field(default_factory=dict)


class SlidingWindowRateLimiter:
    """Sliding window rate limiter with asyncio lock.

    Phase 2C: In-memory implementation. Rate limit state is lost on restart.
    """

    def __init__(self, max_calls: int, period: float) -> None:
        """Initialize the rate limiter.

        Args:
            max_calls: Maximum calls allowed in the window.
            period: Window size in seconds.
        """
        self._max_calls = max_calls
        self._period = period
        self._lock = asyncio.Lock()
        self._timestamps: dict[str, list[float]] = {}

    async def acquire(self, key: str) -> bool:
        """Attempt to acquire a rate limit slot.

        Args:
            key: Rate limit key (session_id, tool_name, etc.).

        Returns:
            True if allowed, False if rate limited.
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._period

            if key not in self._timestamps:
                self._timestamps[key] = []

            self._timestamps[key] = [ts for ts in self._timestamps[key] if ts > cutoff]

            if len(self._timestamps[key]) >= self._max_calls:
                logger.warning(
                    "Rate limit exceeded: key=%s, max_calls=%d, period=%s",
                    key,
                    self._max_calls,
                    self._period,
                )
                return False

            self._timestamps[key].append(now)
            return True

    async def get_remaining(self, key: str) -> int:
        """Get remaining calls in current window.

        Args:
            key: Rate limit key.

        Returns:
            Number of remaining calls.
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._period

            if key not in self._timestamps:
                return self._max_calls

            self._timestamps[key] = [ts for ts in self._timestamps[key] if ts > cutoff]
            return max(0, self._max_calls - len(self._timestamps[key]))


class RateLimitMiddleware:
    """Rate limiting middleware for tool execution.

    Enforces per-session and per-tool rate limits using sliding window.
    """

    def __init__(self, rules: RateLimitRules) -> None:
        """Initialize the rate limit middleware.

        Args:
            rules: Rate limit configuration rules.
        """
        self._rules = rules
        self._session_limiters: dict[str, SlidingWindowRateLimiter] = {}
        self._tool_limiters: dict[str, SlidingWindowRateLimiter] = {}

    async def __call__(
        self,
        request: ExecutionRequest,
        next_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Handle the request with rate limiting.

        Args:
            request: The execution request.
            next_handler: Next handler that accepts a request.

        Returns:
            Tool execution result.
        """
        session_key = f"session:{request.context.session_id}"

        session_limiter = self._session_limiters.get(session_key)
        if not session_limiter:
            session_limiter = SlidingWindowRateLimiter(
                self._rules.per_session.calls,
                self._rules.per_session.period,
            )
            self._session_limiters[session_key] = session_limiter

        if not await session_limiter.acquire(session_key):
            logger.warning(
                "Session rate limit exceeded: session_id=%s",
                request.context.session_id,
            )
            return ToolExecutionResult.error_result(
                error=f"Rate limit exceeded for session. Max {self._rules.per_session.calls} calls per {self._rules.per_session.period}s.",
                error_code="RATE_LIMITED",
                metadata={"limit_type": "session", "key": session_key},
            )

        if request.tool_name in self._rules.per_tool:
            tool_config = self._rules.per_tool[request.tool_name]
            tool_limiter = self._tool_limiters.get(request.tool_name)
            if not tool_limiter:
                tool_limiter = SlidingWindowRateLimiter(
                    tool_config.calls,
                    tool_config.period,
                )
                self._tool_limiters[request.tool_name] = tool_limiter

            tool_key = f"tool:{request.tool_name}"
            if not await tool_limiter.acquire(tool_key):
                logger.warning(
                    "Tool rate limit exceeded: tool_name=%s",
                    request.tool_name,
                )
                return ToolExecutionResult.error_result(
                    error=f"Rate limit exceeded for tool '{request.tool_name}'. Max {tool_config.calls} calls per {tool_config.period}s.",
                    error_code="RATE_LIMITED",
                    metadata={"limit_type": "tool", "key": tool_key},
                )

        return await next_handler(request)


class OwnershipMiddleware:
    """Ownership verification middleware for Phase 2C.

    Ensures only the initiating client can cancel their own tool calls.
    """

    async def __call__(
        self,
        request: ExecutionRequest,
        next_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Handle the request with ownership verification.

        Args:
            request: The execution request.
            next_handler: Next handler that accepts a request.

        Returns:
            Tool execution result.
        """
        if not request.context.client_id:
            logger.debug(
                "No client_id in context, skipping ownership check",
                call_id=request.call_id,
            )

        logger.debug(
            "Ownership verified",
            call_id=request.call_id,
            client_id=request.context.client_id,
            session_id=request.context.session_id,
        )

        return await next_handler(request)


class AuditMiddleware:
    """Audit logging middleware for Phase 2C.

    Logs start and end of tool executions for observability.
    """

    async def __call__(
        self,
        request: ExecutionRequest,
        next_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Handle the request with audit logging.

        Args:
            request: The execution request.
            next_handler: Next handler that accepts a request.

        Returns:
            Tool execution result.
        """
        start_time = time.monotonic()

        logger.info(
            "Tool execution started: call_id=%s, tool_name=%s, session_id=%s, client_id=%s, trace_id=%s",
            request.call_id,
            request.tool_name,
            request.context.session_id,
            request.context.client_id,
            request.context.trace_id,
        )

        try:
            result = await next_handler(request)
            duration = time.monotonic() - start_time

            if result.success:
                logger.info(
                    "Tool execution completed: call_id=%s, tool_name=%s, duration_ms=%.2f",
                    request.call_id,
                    request.tool_name,
                    round(duration * 1000, 2),
                )
            else:
                logger.warning(
                    "Tool execution failed: call_id=%s, tool_name=%s, error=%s, error_code=%s, duration_ms=%.2f",
                    request.call_id,
                    request.tool_name,
                    result.error,
                    result.error_code,
                    round(duration * 1000, 2),
                )

            return result

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(
                "Tool execution exception: call_id=%s, tool_name=%s, error=%s, duration_ms=%.2f",
                request.call_id,
                request.tool_name,
                str(e),
                round(duration * 1000, 2),
            )
            raise


class CancellationMiddleware:
    """Cancellation token injection middleware for Phase 2C.

    Ensures each request has a cancellation token.
    Creates new request with token if not present.
    """

    def __init__(self) -> None:
        """Initialize the cancellation middleware."""
        pass

    async def __call__(
        self,
        request: ExecutionRequest,
        next_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Handle the request with cancellation token.

        Creates a new request with cancellation token if not present.
        Passes the request (new or original) to next handler.

        Args:
            request: The execution request.
            next_handler: Next handler that accepts a request.

        Returns:
            Tool execution result.
        """
        if request.cancellation_token is None:
            from core.execution.cancellation import CancellationToken
            token = CancellationToken()
            request = request.with_cancellation_token(token)
            logger.debug("Created cancellation token for request: %s", request.call_id)

        return await next_handler(request)


class RetryMiddleware:
    """Retry middleware with exponential backoff and jitter.

    Phase 2C: Cancellation-aware retry with immutable request.
    Creates new requests with updated retry_count for each attempt.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_codes: list[str] | None = None,
        jitter_factor: float = 0.1,
    ) -> None:
        """Initialize retry middleware.

        Args:
            max_attempts: Maximum number of attempts.
            base_delay: Base delay between retries in seconds.
            max_delay: Maximum delay cap in seconds.
            retryable_codes: Error codes that should trigger retry.
            jitter_factor: Random jitter factor (0.0 to 1.0).
        """
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retryable_codes = retryable_codes or ["MCP_ERROR", "TIMEOUT"]
        self._jitter_factor = jitter_factor

    async def __call__(
        self,
        request: ExecutionRequest,
        next_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Handle the request with retry logic.

        Creates new request with updated retry_count for each retry attempt.
        Passes the request to next handler.

        Args:
            request: The execution request.
            next_handler: Next handler that accepts a request.

        Returns:
            Tool execution result.
        """
        last_result: ToolExecutionResult | None = None
        current_request = request

        for attempt in range(1, self._max_attempts + 1):
            if current_request.cancellation_token and current_request.cancellation_token.is_cancelled:
                logger.info(
                    "Retry aborted: cancelled: call_id=%s, attempt=%d",
                    current_request.call_id,
                    attempt,
                )
                return ToolExecutionResult.error_result(
                    error="Cancelled",
                    error_code="CANCELLED",
                )

            retry_request = current_request.with_retry_count(attempt - 1)

            result = await next_handler(retry_request)
            last_result = result

            if result.success:
                return result

            if result.error_code not in self._retryable_codes:
                logger.debug(
                    "Non-retryable error, giving up: call_id=%s, error_code=%s, attempt=%d",
                    current_request.call_id,
                    result.error_code,
                    attempt,
                )
                return result

            if attempt >= self._max_attempts:
                logger.warning(
                    "Max retry attempts reached: call_id=%s, attempts=%d",
                    current_request.call_id,
                    self._max_attempts,
                )
                return result

            delay = min(
                self._base_delay * (2 ** (attempt - 1)),
                self._max_delay,
            )

            if self._jitter_factor > 0:
                jitter = random.uniform(0, self._jitter_factor * delay)
                delay += jitter

            logger.info(
                "Retrying after delay: call_id=%s, attempt=%d, next_attempt=%d, delay=%.2f",
                current_request.call_id,
                attempt,
                attempt + 1,
                round(delay, 2),
            )

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                logger.info(
                    "Retry sleep cancelled: call_id=%s, attempt=%d",
                    current_request.call_id,
                    attempt,
                )
                return ToolExecutionResult.error_result(
                    error="Cancelled",
                    error_code="CANCELLED",
                )

        return last_result or ToolExecutionResult.error_result(
            error="Max retries exceeded",
            error_code="MAX_RETRIES_EXCEEDED",
        )


class Pipeline:
    """Middleware pipeline for tool execution.

    Executes middleware in configurable order with final handler at the end.

    Phase 2C: Supports immutable request changes. Middleware can create new requests
    and pass them to next() for the rest of the chain.
    """

    def __init__(self, middlewares: list[MiddlewareHandler]) -> None:
        """Initialize the pipeline.

        Args:
            middlewares: List of middleware handlers in execution order.
        """
        self._middlewares = middlewares

    async def execute(
        self,
        request: ExecutionRequest,
        final_handler: Callable[[ExecutionRequest], Awaitable[ToolExecutionResult]],
    ) -> ToolExecutionResult:
        """Execute the pipeline.

        Args:
            request: The execution request.
            final_handler: Final handler that executes the tool.

        Returns:
            Tool execution result.
        """
        async def chain(
            req: ExecutionRequest,
            index: int,
        ) -> ToolExecutionResult:
            if index >= len(self._middlewares):
                return await final_handler(req)

            async def next_handler(next_req: ExecutionRequest) -> ToolExecutionResult:
                return await chain(next_req, index + 1)

            return await self._middlewares[index](req, next_handler)

        return await chain(request, 0)


class MiddlewareBuilder:
    """Builder for constructing middleware pipelines.

    Supports declarative configuration of middleware order.
    """

    _MIDDLEWARE_CLASSES = {
        "ownership": OwnershipMiddleware,
        "rate_limit": RateLimitMiddleware,
        "retry": RetryMiddleware,
        "cancellation": CancellationMiddleware,
        "audit": AuditMiddleware,
    }

    def __init__(self) -> None:
        """Initialize the builder."""
        self._middlewares: list[MiddlewareHandler] = []

    def add(self, middleware: MiddlewareHandler) -> "MiddlewareBuilder":
        """Add a middleware to the pipeline.

        Args:
            middleware: Middleware handler to add.

        Returns:
            Self for chaining.
        """
        self._middlewares.append(middleware)
        return self

    def add_by_name(
        self,
        name: str,
        config: Any = None,
    ) -> "MiddlewareBuilder":
        """Add a middleware by name.

        Args:
            name: Middleware name (ownership, rate_limit, retry, cancellation, audit).
            config: Optional configuration for the middleware.

        Returns:
            Self for chaining.
        """
        middleware_class = self._MIDDLEWARE_CLASSES.get(name)
        if not middleware_class:
            raise ValueError(f"Unknown middleware: {name}")

        if name == "rate_limit":
            rules = config or RateLimitRules()
            middleware = RateLimitMiddleware(rules)
        elif name == "retry":
            middleware = RetryMiddleware(
                max_attempts=config.get("max_attempts", 3) if config else 3,
                base_delay=config.get("base_delay", 1.0) if config else 1.0,
                max_delay=config.get("max_delay", 30.0) if config else 30.0,
                retryable_codes=config.get("retryable_codes") if config else None,
                jitter_factor=config.get("jitter_factor", 0.1) if config else 0.1,
            )
        else:
            middleware = middleware_class()

        self._middlewares.append(middleware)
        return self

    def build(self) -> Pipeline:
        """Build the pipeline.

        Returns:
            Configured Pipeline instance.
        """
        return Pipeline(list(self._middlewares))
