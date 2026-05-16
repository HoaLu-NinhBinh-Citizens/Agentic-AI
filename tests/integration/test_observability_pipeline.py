"""Integration tests for observability pipeline (Phase 2D.1)."""

import asyncio
import json
import os
import tempfile

import pytest

from domain.models.execution import ExecutionContext, ExecutionRequest
from domain.models.tool_call import ToolCallState
from infrastructure.observability.health import HealthChecker, HealthStatus
from infrastructure.observability.metrics import MetricsRegistry
from infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
)
from shared.logging import (
    redact_sensitive_data,
    set_log_level,
    get_current_log_level,
)


class TestRedactionFilter:
    """Tests for sensitive data redaction."""

    def test_redact_password(self):
        """Test that password fields are redacted."""
        data = {"username": "john", "password": "secret123"}
        result = redact_sensitive_data(data)

        assert result["username"] == "john"
        assert result["password"] == "[REDACTED]"

    def test_redact_nested_password(self):
        """Test that nested password fields are redacted."""
        data = {
            "user": {
                "name": "john",
                "credentials": {
                    "password": "secret123",
                    "api_key": "key123",
                }
            }
        }
        result = redact_sensitive_data(data)

        assert result["user"]["name"] == "john"
        assert result["user"]["credentials"]["password"] == "[REDACTED]"
        assert result["user"]["credentials"]["api_key"] == "[REDACTED]"

    def test_redact_in_list(self):
        """Test that password fields in lists are redacted."""
        data = {
            "users": [
                {"name": "john", "password": "secret1"},
                {"name": "jane", "password": "secret2"},
            ]
        }
        result = redact_sensitive_data(data)

        assert result["users"][0]["name"] == "john"
        assert result["users"][0]["password"] == "[REDACTED]"
        assert result["users"][1]["name"] == "jane"
        assert result["users"][1]["password"] == "[REDACTED]"

    def test_custom_redacted_fields(self):
        """Test custom redaction fields."""
        data = {"custom_field": "sensitive"}
        result = redact_sensitive_data(data, redacted_fields={"custom_field"})

        assert result["custom_field"] == "[REDACTED]"

    def test_no_redaction_needed(self):
        """Test that normal fields are not redacted."""
        data = {"name": "john", "age": 30, "email": "john@example.com"}
        result = redact_sensitive_data(data)

        assert result == data


class TestCircuitBreakerSlidingWindow:
    """Tests for circuit breaker with sliding time window."""

    @pytest.fixture
    def breaker(self):
        """Create a fresh circuit breaker with short window."""
        return CircuitBreaker(
            name="test-server",
            failure_threshold=3,
            window_seconds=2.0,
            timeout_seconds=1.0,
        )

    @pytest.mark.asyncio
    async def test_failures_expire_after_window(self, breaker):
        """Test that failures expire after the sliding window."""
        async def fail():
            raise ConnectionError("fail")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.OPEN

        await asyncio.sleep(2.5)

        async def success():
            return 42

        result = await breaker.call(success)
        assert result == 42
        assert breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_partial_failures_in_window(self, breaker):
        """Test partial failures within window don't trip circuit."""
        async def fail():
            raise ValueError("non-transient")

        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_count_resets_after_window(self, breaker):
        """Test failure count resets after window expires."""
        async def fail():
            raise ConnectionError("fail")

        for _ in range(2):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.failure_count == 2
        assert breaker.state == CircuitBreakerState.CLOSED

        await asyncio.sleep(2.5)

        async def success():
            return 42

        result = await breaker.call(success)
        assert result == 42
        assert breaker.failure_count == 0


class TestEventLoopHealth:
    """Tests for event loop health monitoring."""

    @pytest.mark.asyncio
    async def test_heartbeat_updates(self):
        """Test that heartbeat updates."""
        from infrastructure.observability.health import EventLoopHealth

        health = EventLoopHealth(max_lag_seconds=5.0)
        await health.start()

        await asyncio.sleep(0.1)

        assert health.is_alive()
        assert health.get_lag() < 1.0

        await health.stop()

    @pytest.mark.asyncio
    async def test_health_checker_includes_event_loop(self):
        """Test that health checker includes event loop status."""
        checker = HealthChecker(event_loop_max_lag=5.0)
        await checker.start()

        report = await checker.get_readiness()

        assert report.event_loop_healthy
        assert report.details["event_loop_healthy"]
        assert "event_loop_lag_seconds" in report.details

        await checker.stop()


class TestDynamicLogLevel:
    """Tests for dynamic log level adjustment."""

    def test_set_log_level_valid(self):
        """Test setting a valid log level."""
        original = get_current_log_level()

        new_level = set_log_level("DEBUG")
        assert new_level == "DEBUG"
        assert get_current_log_level() == "DEBUG"

        set_log_level(original)

    def test_set_log_level_invalid(self):
        """Test setting an invalid log level."""
        with pytest.raises(ValueError):
            set_log_level("INVALID")

    def test_get_current_log_level(self):
        """Test getting current log level."""
        level = get_current_log_level()
        assert level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class TestMetricsRegistryIntegration:
    """Tests for metrics registry integration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        MetricsRegistry.reset_instance()
        yield
        MetricsRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_tool_call_metrics(self):
        """Test recording tool call metrics."""
        registry = MetricsRegistry.get_instance()

        await registry.inc_counter(
            "tool_calls_total",
            {"tool": "echo", "success": "true"}
        )
        await registry.inc_counter(
            "tool_calls_total",
            {"tool": "echo", "success": "true"}
        )
        await registry.inc_counter(
            "tool_calls_total",
            {"tool": "echo", "success": "false"}
        )

        count_success = await registry.get_counter(
            "tool_calls_total",
            {"tool": "echo", "success": "true"}
        )
        count_failure = await registry.get_counter(
            "tool_calls_total",
            {"tool": "echo", "success": "false"}
        )

        assert count_success == 2
        assert count_failure == 1

    @pytest.mark.asyncio
    async def test_prometheus_format(self):
        """Test Prometheus text format export."""
        registry = MetricsRegistry.get_instance()

        await registry.inc_counter(
            "requests_total",
            {"method": "GET", "status": "200"}
        )
        await registry.observe_histogram(
            "request_duration",
            0.5,
            {"method": "GET"}
        )

        output = await registry.export_text()

        assert "# HELP requests_total" in output
        assert "# TYPE requests_total counter" in output
        assert 'method="GET"' in output
        assert "# HELP request_duration" in output
        assert "# TYPE request_duration histogram" in output


class TestObservabilityPipeline:
    """End-to-end observability pipeline tests."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        MetricsRegistry.reset_instance()
        yield
        MetricsRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_execution_with_metrics(self):
        """Test tool execution with metrics collection."""
        registry = MetricsRegistry.get_instance()

        await registry.inc_counter(
            "tool_calls_total",
            {"tool": "test_tool", "success": "true"}
        )

        output = await registry.export_text()

        assert "tool_calls_total" in output
        assert 'tool="test_tool"' in output

    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """Test health check with server status."""
        checker = HealthChecker()
        await checker.start()

        await checker.update_server_health(
            "filesystem",
            HealthStatus.HEALTHY,
        )

        report = await checker.get_readiness()

        assert report.status == HealthStatus.HEALTHY
        assert report.servers["filesystem"] == "healthy"

        await checker.stop()

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_metrics(self):
        """Test circuit breaker failure tracking."""
        registry = MetricsRegistry.get_instance()

        cb = CircuitBreaker(
            name="test-mcp",
            failure_threshold=2,
            window_seconds=60.0,
        )

        async def fail_once():
            raise ConnectionError("connection failed")

        with pytest.raises(ConnectionError):
            await cb.call(fail_once)
        await registry.inc_counter(
            "circuit_breaker_failures_total",
            {"server": "test-mcp"}
        )

        with pytest.raises(ConnectionError):
            await cb.call(fail_once)
        await registry.inc_counter(
            "circuit_breaker_failures_total",
            {"server": "test-mcp"}
        )

        assert cb.state == CircuitBreakerState.OPEN

        count = await registry.get_counter(
            "circuit_breaker_failures_total",
            {"server": "test-mcp"}
        )

        assert count == 2


class TestHealthCheckerWithEventLoop:
    """Tests for health checker with event loop integration."""

    @pytest.mark.asyncio
    async def test_readiness_includes_event_loop(self):
        """Test readiness includes event loop health."""
        checker = HealthChecker(event_loop_max_lag=5.0)
        await checker.start()

        report = await checker.get_readiness()

        assert "event_loop_healthy" in report.details
        assert report.details["event_loop_healthy"] is True

        await checker.stop()

    @pytest.mark.asyncio
    async def test_unhealthy_when_event_loop_stalled(self):
        """Test readiness returns unhealthy when event loop is slow."""
        checker = HealthChecker(event_loop_max_lag=0.1)
        await checker.start()

        await asyncio.sleep(0.2)

        report = await checker.get_readiness()

        assert report.status == HealthStatus.UNHEALTHY
        assert "stalled" in report.reason.lower()

        await checker.stop()
