"""Tests for circuit breaker."""

import asyncio
import time

import pytest
from src.infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create a fresh circuit breaker for each test."""
        return CircuitBreaker(
            name="test-server",
            failure_threshold=3,
            timeout_seconds=60.0,
        )

    @pytest.mark.asyncio
    async def test_success_closes_circuit(self, breaker):
        """Test that successful calls keep circuit closed."""
        async def success():
            return 42

        result = await breaker.call(success)
        assert result == 42
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_transient_failure_increments_count(self, breaker):
        """Test that transient failures increment failure count."""

        async def fail():
            raise ConnectionError("Connection refused")

        with pytest.raises(ConnectionError):
            await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_non_transient_failure_does_not_count(self, breaker):
        """Test that non-transient failures don't affect circuit."""

        async def fail():
            raise ValueError("Invalid argument")

        with pytest.raises(ValueError):
            await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self, breaker):
        """Test circuit opens after failure threshold reached."""

        async def fail():
            raise ConnectionError("Connection refused")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 3

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(lambda: 42)

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Test circuit moves to half-open after timeout."""
        breaker = CircuitBreaker(
            name="test-server",
            failure_threshold=3,
            timeout_seconds=0.1,
        )

        async def fail():
            raise ConnectionError("Connection refused")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.OPEN

        await asyncio.sleep(0.15)

        async def success():
            return 42

        result = await breaker.call(success)
        assert result == 42
        assert breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_probe_failure(self):
        """Test that half-open probe failure reopens circuit."""
        breaker = CircuitBreaker(
            name="test-server",
            failure_threshold=3,
            timeout_seconds=0.1,
        )

        async def fail():
            raise ConnectionError("Connection refused")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.OPEN

        await asyncio.sleep(0.15)

        async def still_fail():
            raise ConnectionError("Still failing")

        with pytest.raises(ConnectionError):
            await breaker.call(still_fail)

        assert breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_reset(self, breaker):
        """Test circuit breaker reset."""

        async def fail():
            raise ConnectionError("fail")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitBreakerState.OPEN

        breaker.reset()

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

        async def success():
            return 42

        result = await breaker.call(success)
        assert result == 42


class TestTransientFailureDetection:
    """Tests for transient failure detection."""

    @pytest.mark.asyncio
    async def test_connection_errors_are_transient(self):
        """Test that connection-related errors are transient."""
        cb = CircuitBreaker(name="test", failure_threshold=1)

        errors = [
            ConnectionError("Connection refused"),
            ConnectionRefusedError(),
            BrokenPipeError("Broken pipe"),
            ConnectionResetError(),
            TimeoutError("Timed out"),
        ]

        for error in errors:
            cb.reset()
            with pytest.raises(Exception):
                await cb.call(lambda: (_ for _ in ()).throw(error))

            assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_custom_transient_codes(self):
        """Test that custom error codes are detected as transient."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            transient_error_codes=["MCP_ERROR", "TIMEOUT"],
        )

        cb.reset()

        async def raise_mcp_error():
            raise Exception("MCP_ERROR: Server unavailable")

        with pytest.raises(Exception):
            await cb.call(raise_mcp_error)

        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_permission_errors_not_transient(self):
        """Test that permission errors are not transient."""
        cb = CircuitBreaker(name="test", failure_threshold=1)

        async def raise_permission_error():
            raise PermissionError("Access denied")

        with pytest.raises(PermissionError):
            await cb.call(raise_permission_error)

        assert cb.failure_count == 0
