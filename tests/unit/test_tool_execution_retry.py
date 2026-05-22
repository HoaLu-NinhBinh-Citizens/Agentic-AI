"""Unit tests for retry infrastructure - Phase 2.3."""

import asyncio
import pytest

from infrastructure.tool_execution.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    RetryConfig,
    RetryExecutor,
    RetryMetrics,
    RetryStrategy,
    create_retry_config,
    retry_with_backoff,
)


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.jitter_factor == 0.1
        assert config.strategy == RetryStrategy.EXPONENTIAL

    def test_should_retry_within_attempts(self):
        """Test should_retry returns True within attempt limit."""
        config = RetryConfig(max_attempts=3)
        assert config.should_retry("TIMEOUT", 1) is True
        assert config.should_retry("MCP_ERROR", 2) is True

    def test_should_not_retry_at_limit(self):
        """Test should_retry returns False at attempt limit."""
        config = RetryConfig(max_attempts=3)
        assert config.should_retry("TIMEOUT", 3) is False

    def test_should_not_retry_non_retryable_error(self):
        """Test non-retryable errors are rejected."""
        config = RetryConfig()
        assert config.should_retry("VALIDATION_ERROR", 1) is False
        assert config.should_retry("PERMISSION_DENIED", 1) is False

    def test_should_not_retry_none_error_code(self):
        """Test None error code is not retried."""
        config = RetryConfig()
        assert config.should_retry(None, 1) is False

    def test_exponential_delay(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(base_delay=1.0, strategy=RetryStrategy.EXPONENTIAL, jitter_factor=0.0)
        delay1 = config.get_delay(1)
        delay2 = config.get_delay(2)
        delay3 = config.get_delay(3)

        assert delay1 == pytest.approx(1.0, rel=0.01)
        assert delay2 == pytest.approx(2.0, rel=0.01)
        assert delay3 == pytest.approx(4.0, rel=0.01)

    def test_linear_delay(self):
        """Test linear backoff calculation."""
        config = RetryConfig(base_delay=1.0, strategy=RetryStrategy.LINEAR, jitter_factor=0.0)
        delay1 = config.get_delay(1)
        delay2 = config.get_delay(2)
        delay3 = config.get_delay(3)

        assert delay1 == pytest.approx(1.0, rel=0.01)
        assert delay2 == pytest.approx(2.0, rel=0.01)
        assert delay3 == pytest.approx(3.0, rel=0.01)

    def test_fixed_delay(self):
        """Test fixed delay calculation."""
        config = RetryConfig(base_delay=2.0, strategy=RetryStrategy.FIXED, jitter_factor=0.0)
        delay1 = config.get_delay(1)
        delay2 = config.get_delay(2)

        assert delay1 == pytest.approx(2.0, rel=0.01)
        assert delay2 == pytest.approx(2.0, rel=0.01)

    def test_max_delay_cap(self):
        """Test maximum delay is capped."""
        config = RetryConfig(
            base_delay=10.0,
            max_delay=15.0,
            strategy=RetryStrategy.EXPONENTIAL,
            jitter_factor=0.0,
        )
        delay = config.get_delay(10)
        assert delay <= 15.0

    def test_jitter_added(self):
        """Test jitter is added to delay."""
        config = RetryConfig(base_delay=1.0, jitter_factor=0.5, strategy=RetryStrategy.FIXED)
        delays = [config.get_delay(1) for _ in range(10)]
        assert any(d > 1.0 for d in delays)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        """Test circuit starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_allows_execution_when_closed(self):
        """Test execution allowed when circuit is closed."""
        cb = CircuitBreaker()
        can_exec = await cb.can_execute()
        assert can_exec is True

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        """Test circuit opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)

        for _ in range(3):
            await cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert await cb.can_execute() is False

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Test circuit transitions to half-open after timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0.01)
        cb = CircuitBreaker(config)

        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.02)
        can_exec = await cb.can_execute()
        assert can_exec is True
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self):
        """Test circuit closes after success threshold in half-open."""
        config = CircuitBreakerConfig(failure_threshold=2, success_threshold=2, timeout_seconds=0.01)
        cb = CircuitBreaker(config)

        await cb.record_failure()
        await cb.record_failure()

        await asyncio.sleep(0.02)
        await cb.can_execute()

        await cb.record_success()
        await cb.record_success()

        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_on_half_open_failure(self):
        """Test circuit reopens on failure in half-open state."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0.01)
        cb = CircuitBreaker(config)

        await cb.record_failure()
        await cb.record_failure()

        await asyncio.sleep(0.02)
        await cb.can_execute()

        await cb.record_failure()

        assert cb.state == CircuitState.OPEN


class TestRetryMetrics:
    """Tests for RetryMetrics."""

    def test_initial_state(self):
        """Test metrics start at zero."""
        metrics = RetryMetrics()
        assert metrics.total_attempts == 0
        assert metrics.successful_retries == 0
        assert metrics.failed_retries == 0
        assert metrics.circuit_breaker_opens == 0
        assert metrics.retry_rate == 0.0

    def test_record_attempt(self):
        """Test recording attempts."""
        metrics = RetryMetrics()
        metrics.record_attempt()
        metrics.record_attempt()
        assert metrics.total_attempts == 2

    def test_retry_rate_calculation(self):
        """Test retry rate calculation."""
        metrics = RetryMetrics()
        metrics.record_attempt()
        metrics.record_attempt()
        metrics.record_attempt()
        metrics.record_success()
        metrics.record_success()

        assert metrics.retry_rate == pytest.approx(2 / 3, rel=0.01)


class MockExecutor:
    """Mock executor for testing."""

    def __init__(self, should_fail: bool = False, fail_count: int = 1):
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.attempt_count = 0
        self.success_count = 0

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """Execute mock tool."""
        self.attempt_count += 1
        if self.should_fail and self.attempt_count <= self.fail_count:
            raise RuntimeError("Mock failure")
        self.success_count += 1
        return {"content": [{"type": "text", "text": f"Result for {tool_name}"}]}


class TestRetryExecutor:
    """Tests for RetryExecutor."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful execution without retry."""
        executor = MockExecutor(should_fail=False)
        retry_executor = RetryExecutor(executor, RetryConfig(max_attempts=3))

        result = await retry_executor.execute("test_tool", {})

        assert executor.attempt_count == 1
        assert "content" in result
        assert retry_executor.metrics.total_attempts == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Test retry succeeds after transient failure."""
        executor = MockExecutor(should_fail=True, fail_count=2)
        retry_executor = RetryExecutor(executor, RetryConfig(max_attempts=3))

        result = await retry_executor.execute("test_tool", {})

        assert executor.attempt_count == 3
        assert executor.success_count == 1
        assert retry_executor.metrics.successful_retries == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """Test exception raised after all retries exhausted."""
        executor = MockExecutor(should_fail=True, fail_count=10)
        retry_executor = RetryExecutor(executor, RetryConfig(max_attempts=3))

        with pytest.raises(RuntimeError, match="Mock failure"):
            await retry_executor.execute("test_tool", {})

        assert executor.attempt_count == 3
        assert retry_executor.metrics.failed_retries == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_execution(self):
        """Test circuit breaker records when failures exceed threshold."""
        executor = MockExecutor(should_fail=True, fail_count=10)
        circuit_config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.01)
        retry_executor = RetryExecutor(
            executor,
            RetryConfig(max_attempts=3),
            circuit_config,
        )

        with pytest.raises(RuntimeError, match="Mock failure"):
            await retry_executor.execute("test_tool", {})

        assert retry_executor.metrics.total_attempts == 3
        assert retry_executor.metrics.failed_retries == 1

    @pytest.mark.asyncio
    async def test_cancellation_during_retry(self):
        """Test cancellation stops retry loop."""
        from core.execution.cancellation import CancellationToken

        executor = MockExecutor(should_fail=True, fail_count=10)
        retry_executor = RetryExecutor(executor, RetryConfig(max_attempts=5))
        token = CancellationToken()

        async def cancel_after_delay():
            await asyncio.sleep(0.05)
            token.cancel()

        asyncio.create_task(cancel_after_delay())

        with pytest.raises(asyncio.CancelledError):
            await retry_executor.execute("test_tool", {}, token)


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Test successful call without retry."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_with_backoff(func, RetryConfig(max_attempts=3))
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_args_kwargs(self):
        """Test retry with function arguments."""
        call_count = 0

        async def func(a, b, c=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient error")
            return f"{a}-{b}-{c}"

        result = await retry_with_backoff(
            func,
            RetryConfig(max_attempts=3),
            "hello",
            "world",
            c="test",
        )
        assert result == "hello-world-test"
        assert call_count == 3


class TestCreateRetryConfig:
    """Tests for create_retry_config factory."""

    def test_default_factory(self):
        """Test default config from factory."""
        config = create_retry_config()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0

    def test_custom_factory(self):
        """Test custom config from factory."""
        config = create_retry_config(
            max_attempts=5,
            base_delay=2.0,
            max_delay=60.0,
            strategy=RetryStrategy.LINEAR,
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.strategy == RetryStrategy.LINEAR
