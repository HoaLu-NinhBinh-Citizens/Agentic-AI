"""Unit tests for Phase 2C cancellation module."""

from __future__ import annotations

import asyncio
import pytest

from core.execution.cancellation import (
    CancellationToken,
    ProcessHandle,
    SubprocessHandle,
    NoOpProcessHandle,
    CancellationRegistry,
    RetryPolicy,
)


class TestCancellationToken:
    """Tests for CancellationToken."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test that token starts uncancelled."""
        token = CancellationToken()
        assert not token.is_cancelled

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self):
        """Test that cancel() sets the cancelled flag."""
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled

    @pytest.mark.asyncio
    async def test_cancel_multiple_times(self):
        """Test that cancel() is safe to call multiple times."""
        token = CancellationToken()
        token.cancel()
        token.cancel()
        token.cancel()
        assert token.is_cancelled

    @pytest.mark.asyncio
    async def test_wait_blocks_until_cancel(self):
        """Test that wait() blocks until cancel() is called."""
        token = CancellationToken()
        wait_returned = False

        async def wait_task():
            nonlocal wait_returned
            await token.wait()
            wait_returned = True

        async def cancel_after_delay():
            await asyncio.sleep(0.05)
            token.cancel()

        wait_task_handle = asyncio.create_task(wait_task())
        cancel_task_handle = asyncio.create_task(cancel_after_delay())

        await cancel_task_handle
        await wait_task_handle

        assert wait_returned  # Wait should have returned after cancel

    @pytest.mark.asyncio
    async def test_wait_raises_if_already_cancelled(self):
        """Test that wait() raises CancelledError if already cancelled."""
        token = CancellationToken()
        token.cancel()

        with pytest.raises(asyncio.CancelledError):
            await token.wait()

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test that reset() returns token to initial state."""
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled

        token.reset()
        assert not token.is_cancelled


class TestSubprocessHandle:
    """Tests for SubprocessHandle."""

    @pytest.mark.asyncio
    async def test_noop_handle(self):
        """Test that NoOpProcessHandle does nothing."""
        handle = NoOpProcessHandle()
        await handle.terminate()
        await handle.kill()


class TestCancellationRegistry:
    """Tests for CancellationRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving tokens."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-1")

        retrieved = registry.get_token("call-1")
        assert retrieved is token

    def test_get_initiator_client_id(self):
        """Test retrieving initiator client ID."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-abc")

        client_id = registry.get_initiator_client_id("call-1")
        assert client_id == "client-abc"

    def test_register_process_handle(self):
        """Test registering process handles."""
        registry = CancellationRegistry()
        token = CancellationToken()
        handle = NoOpProcessHandle()
        registry.register("call-1", token, "client-1", handle)

        retrieved = registry.get_handle("call-1")
        assert retrieved is handle

    def test_is_registered(self):
        """Test checking registration."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-1")

        assert registry.is_registered("call-1")
        assert not registry.is_registered("call-999")

    def test_unregister(self):
        """Test unregistering tokens."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-1")

        registry.unregister("call-1")
        assert not registry.is_registered("call-1")

    @pytest.mark.asyncio
    async def test_cancel(self):
        """Test cancelling via registry."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-1")

        result = await registry.cancel("call-1")
        assert result is True
        assert token.is_cancelled

    @pytest.mark.asyncio
    async def test_cancel_not_found(self):
        """Test cancelling non-existent call."""
        registry = CancellationRegistry()

        result = await registry.cancel("call-999")
        assert result is False

    def test_get_registered_ids(self):
        """Test getting all registered IDs."""
        registry = CancellationRegistry()
        token1 = CancellationToken()
        token2 = CancellationToken()
        registry.register("call-1", token1, "client-1")
        registry.register("call-2", token2, "client-2")

        ids = registry.get_registered_ids()
        assert set(ids) == {"call-1", "call-2"}

    def test_clear(self):
        """Test clearing all registrations."""
        registry = CancellationRegistry()
        token = CancellationToken()
        registry.register("call-1", token, "client-1")

        registry.clear()
        assert not registry.is_registered("call-1")


class TestRetryPolicy:
    """Tests for RetryPolicy."""

    def test_should_retry_within_attempts(self):
        """Test that retry is allowed within max attempts."""
        policy = RetryPolicy(max_attempts=3)

        assert policy.should_retry("MCP_ERROR", 1)  # attempt 1 < max 3
        assert policy.should_retry("MCP_ERROR", 2)  # attempt 2 < max 3

    def test_should_not_retry_at_max_attempts(self):
        """Test that retry is not allowed at max attempts."""
        policy = RetryPolicy(max_attempts=3)

        assert not policy.should_retry("MCP_ERROR", 3)  # attempt 3 == max 3

    def test_should_not_retry_non_retryable_code(self):
        """Test that non-retryable codes are not retried."""
        policy = RetryPolicy(retryable_codes=["MCP_ERROR"])

        assert not policy.should_retry("PERMISSION_DENIED", 1)

    def test_should_not_retry_none_code(self):
        """Test that None error code is not retried."""
        policy = RetryPolicy()

        assert not policy.should_retry(None, 1)

    def test_get_delay_exponential_backoff(self):
        """Test exponential backoff calculation."""
        policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=30.0)

        delay1 = policy.get_delay(1)
        delay2 = policy.get_delay(2)
        delay3 = policy.get_delay(3)

        assert delay1 == pytest.approx(1.0, rel=0.2)
        assert delay2 == pytest.approx(2.0, rel=0.2)
        assert delay3 == pytest.approx(4.0, rel=0.2)

    def test_get_delay_respects_max(self):
        """Test that delay respects max_delay cap."""
        policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=5.0)

        delay = policy.get_delay(10)  # Would be 512 without cap
        assert delay <= 5.0 + (5.0 * policy.jitter_factor)

    def test_get_delay_with_jitter(self):
        """Test that jitter is added to delay."""
        policy = RetryPolicy(base_delay_seconds=1.0, jitter_factor=0.5)

        delays = [policy.get_delay(1) for _ in range(10)]
        assert len(set(delays)) > 1  # Jitter should produce different values

    def test_get_delay_no_jitter(self):
        """Test delay without jitter."""
        policy = RetryPolicy(base_delay_seconds=1.0, jitter_factor=0.0)

        delays = [policy.get_delay(1) for _ in range(10)]
        assert len(set(delays)) == 1  # All same without jitter

    def test_from_dict(self):
        """Test creating policy from dictionary."""
        data = {
            "max_attempts": 5,
            "base_delay_seconds": 2.0,
            "max_delay_seconds": 60.0,
            "retryable_codes": ["TIMEOUT"],
            "jitter_factor": 0.2,
        }

        policy = RetryPolicy.from_dict(data)

        assert policy.max_attempts == 5
        assert policy.base_delay_seconds == 2.0
        assert policy.max_delay_seconds == 60.0
        assert policy.retryable_codes == ["TIMEOUT"]
        assert policy.jitter_factor == 0.2
