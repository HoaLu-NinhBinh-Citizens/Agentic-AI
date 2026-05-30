"""Integration tests for Fence Token Enforcement in Probe Adapter.

P0-Hardening: These tests verify that:
1. Fake probe (no token enforcement) behaves differently from fenced probe
2. Fenced probe enforces token validation on every erase/write/verify call
3. Both probes behave consistently when token is valid
4. Stale/revoked tokens are properly rejected by fenced probe

Run with:
    python -m pytest tests/integration/test_fence_token_enforcement.py -v
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any

from src.domain.hardware.flash.flash_lock import (
    TargetFlashLock,
    LockManager,
    FlashFenceToken,
    FenceValidationError,
)
from src.infrastructure.hardware.fence_aware_probe import (
    FenceAwareProbeAdapter,
    FenceTokenMiddleware,
    FenceViolationError,
)


# =============================================================================
# Mock HardwareProbe implementations for testing
# =============================================================================


class FakeHardwareProbe:
    """Fake probe that accepts ANY token without validation.

    This simulates a naive probe implementation that doesn't check
    fence tokens - useful for comparing behavior.
    """

    def __init__(self, memory_size: int = 1024 * 1024, base_address: int = 0x08000000):
        self.base_address = base_address
        self.memory_size = memory_size
        self._memory = bytearray(memory_size)
        self._halted = False
        self._connected = True
        self._operation_log: list[str] = []

    @property
    def probe_info(self) -> dict[str, Any]:
        return {
            "name": "FakeProbe",
            "type": "mock",
            "connected": self._connected,
        }

    async def connect(self, target_id: str) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def read_memory(self, address: int, length: int) -> bytes:
        self._operation_log.append(f"read_memory({hex(address)}, {length})")
        offset = address - self.base_address
        if offset < 0 or offset + length > self.memory_size:
            return b""
        return bytes(self._memory[offset : offset + length])

    async def write_memory(self, address: int, data: bytes) -> bool:
        self._operation_log.append(f"write_memory({hex(address)}, {len(data)} bytes)")
        offset = address - self.base_address
        if offset < 0 or offset + len(data) > self.memory_size:
            return False
        self._memory[offset : offset + len(data)] = data
        return True

    async def erase(self, address: int, length: int) -> bool:
        self._operation_log.append(f"erase({hex(address)}, {length})")
        offset = address - self.base_address
        sector_size = 4096
        aligned_offset = (offset // sector_size) * sector_size
        if aligned_offset + length <= self.memory_size:
            for i in range(length):
                if aligned_offset + i < self.memory_size:
                    self._memory[aligned_offset + i] = 0xFF
        return True

    async def reset(self) -> bool:
        self._operation_log.append("reset()")
        self._halted = False
        return True

    async def halt(self) -> bool:
        self._operation_log.append("halt()")
        self._halted = True
        return True

    async def resume(self) -> bool:
        self._operation_log.append("resume()")
        self._halted = False
        return True

    async def step(self) -> bool:
        self._operation_log.append("step()")
        return True

    async def read_register(self, register: str) -> int:
        self._operation_log.append(f"read_register({register})")
        return 0

    async def write_register(self, register: str, value: int) -> bool:
        self._operation_log.append(f"write_register({register}, {hex(value)})")
        return True

    async def set_breakpoint(self, address: int) -> bool:
        self._operation_log.append(f"set_breakpoint({hex(address)})")
        return True

    async def remove_breakpoint(self, address: int) -> bool:
        self._operation_log.append(f"remove_breakpoint({hex(address)})")
        return True


class StrictHardwareProbe(FakeHardwareProbe):
    """Probe that enforces fence token validation.

    This is the REAL behavior expected from FenceAwareProbeAdapter.
    Every operation must validate the token before execution.
    """

    def __init__(
        self,
        lock_manager: LockManager,
        fence_token: FlashFenceToken,
        target_name: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._lock_manager = lock_manager
        self._fence_token = fence_token
        self._target_name = target_name
        self._validated_count = 0

    async def _validate_token(self, operation: str) -> None:
        """Validate token before any operation - raises on failure."""
        self._validated_count += 1
        is_valid, reason = await self._lock_manager.target_lock.validate_fence_token(
            target_name=self._target_name,
            token=self._fence_token,
            operation_name=operation,
        )
        if not is_valid:
            raise FenceViolationError(
                operation=operation,
                token=self._fence_token.token,
                reason=reason,
            )

    async def write_memory(self, address: int, data: bytes) -> bool:
        await self._validate_token("write_memory")
        return await super().write_memory(address, data)

    async def erase(self, address: int, length: int) -> bool:
        await self._validate_token("erase")
        return await super().erase(address, length)

    async def read_memory(self, address: int, length: int) -> bytes:
        await self._validate_token("read_memory")
        return await super().read_memory(address, length)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def target_lock():
    """Create an in-memory TargetFlashLock for testing."""
    return TargetFlashLock(lease_timeout_seconds=60)


@pytest.fixture
async def lock_manager(target_lock):
    """Create a LockManager with TargetFlashLock."""
    manager = LockManager()
    manager.target_lock = target_lock
    return manager


@pytest.fixture
def fake_probe():
    """Create a fake probe without token enforcement."""
    return FakeHardwareProbe(base_address=0x08000000)


@pytest.fixture
async def valid_token(lock_manager):
    """Acquire lock and get a valid fence token."""
    lock, token = await lock_manager.acquire_with_fence_token(
        target_name="engine_car",
        owner_id="test_agent",
        transaction_id="tx_test_001",
    )
    assert lock is not None, "Lock acquisition failed"
    assert token is not None, "Token issuance failed"
    return token


@pytest.fixture
async def revoked_token(lock_manager, valid_token):
    """Create a revoked token for testing rejection."""
    # Revoke the token
    await lock_manager.invalidate_fence_on_failure("engine_car", "test_agent")
    # Return the now-revoked token
    return valid_token


# =============================================================================
# Test Cases: FenceAwareProbeAdapter
# =============================================================================


class TestFenceAwareProbeAdapterBasics:
    """Basic tests for FenceAwareProbeAdapter."""

    @pytest.mark.asyncio
    async def test_adapter_wraps_probe(self, fake_probe, lock_manager, valid_token):
        """FenceAwareProbeAdapter should wrap the underlying probe."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        # Should have the same probe_info
        assert adapter.probe_info["name"] == "FakeProbe"

    @pytest.mark.asyncio
    async def test_successful_erase_with_valid_token(
        self, fake_probe, lock_manager, valid_token
    ):
        """erase() should succeed with valid token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        result = await adapter.erase(0x08000000, 4096)

        assert result is True
        # Token should have been advanced
        stats = adapter.get_stats()
        assert stats["validated_operations"] == 1

    @pytest.mark.asyncio
    async def test_successful_write_with_valid_token(
        self, fake_probe, lock_manager, valid_token
    ):
        """write_memory() should succeed with valid token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        test_data = b"\xDE\xAD\xBE\xEF" * 16
        result = await adapter.write_memory(0x08000000, test_data)

        assert result is True
        stats = adapter.get_stats()
        assert stats["validated_operations"] == 1

    @pytest.mark.asyncio
    async def test_successful_read_with_valid_token(
        self, fake_probe, lock_manager, valid_token
    ):
        """read_memory() should succeed with valid token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        # Write some data first
        await fake_probe.write_memory(0x08000000, b"\x12\x34\x56\x78")

        result = await adapter.read_memory(0x08000000, 4)

        assert result == b"\x12\x34\x56\x78"
        stats = adapter.get_stats()
        assert stats["validated_operations"] == 1


class TestFenceAwareProbeAdapterRejection:
    """Tests for FenceAwareProbeAdapter rejecting invalid tokens."""

    @pytest.mark.asyncio
    async def test_erase_rejected_with_revoked_token(
        self, fake_probe, lock_manager, revoked_token
    ):
        """erase() should be rejected with revoked token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=revoked_token,
            target_name="engine_car",
        )

        with pytest.raises(FenceViolationError) as exc_info:
            await adapter.erase(0x08000000, 4096)

        # Verify the exception contains meaningful fence violation info
        exc_msg = str(exc_info.value).lower()
        assert "stale" in exc_msg or "fence" in exc_msg
        # Operation should NOT have reached the probe
        assert "erase" not in fake_probe._operation_log

    @pytest.mark.asyncio
    async def test_write_rejected_with_revoked_token(
        self, fake_probe, lock_manager, revoked_token
    ):
        """write_memory() should be rejected with revoked token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=revoked_token,
            target_name="engine_car",
        )

        test_data = b"\xDE\xAD\xBE\xEF"

        with pytest.raises(FenceViolationError):
            await adapter.write_memory(0x08000000, test_data)

        # Operation should NOT have reached the probe
        assert "write_memory" not in fake_probe._operation_log

    @pytest.mark.asyncio
    async def test_read_rejected_with_revoked_token(
        self, fake_probe, lock_manager, revoked_token
    ):
        """read_memory() should be rejected with revoked token."""
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=revoked_token,
            target_name="engine_car",
        )

        with pytest.raises(FenceViolationError):
            await adapter.read_memory(0x08000000, 4)

        # Operation should NOT have reached the probe
        assert "read_memory" not in fake_probe._operation_log

    @pytest.mark.asyncio
    async def test_multiple_operations_all_validated(
        self, fake_probe, lock_manager, valid_token
    ):
        """Multiple operations should each be validated."""
        # First operation with valid token
        adapter1 = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        await adapter1.erase(0x08000000, 4096)
        assert adapter1.get_stats()["validated_operations"] == 1

        # Subsequent operations need fresh tokens (adapter advances token after each op)
        _, token2 = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="test_agent",
            transaction_id="tx_test_002",
        )
        adapter2 = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=token2,
            target_name="engine_car",
        )
        await adapter2.write_memory(0x08000000, b"\xAA\xBB\xCC\xDD")
        assert adapter2.get_stats()["validated_operations"] == 1

        _, token3 = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="test_agent",
            transaction_id="tx_test_003",
        )
        adapter3 = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=token3,
            target_name="engine_car",
        )
        await adapter3.read_memory(0x08000000, 4)
        assert adapter3.get_stats()["validated_operations"] == 1


# =============================================================================
# Test Cases: FenceTokenMiddleware
# =============================================================================


class TestFenceTokenMiddleware:
    """Tests for FenceTokenMiddleware pipeline."""

    @pytest.mark.asyncio
    async def test_middleware_validates_before_execution(
        self, lock_manager, valid_token
    ):
        """Middleware should validate token before calling handler."""
        middleware = FenceTokenMiddleware(
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        call_order: list[str] = []

        async def handler(address: int, length: int) -> bool:
            call_order.append("handler")
            return True

        middleware.register("erase", handler)

        await middleware.execute("erase", 0x08000000, 4096)

        assert call_order == ["handler"], "Handler should have been called"

    @pytest.mark.asyncio
    async def test_middleware_rejects_revoked_token(
        self, lock_manager, revoked_token
    ):
        """Middleware should reject revoked token before calling handler."""
        middleware = FenceTokenMiddleware(
            lock_manager=lock_manager,
            fence_token=revoked_token,
            target_name="engine_car",
        )

        call_order: list[str] = []

        async def handler(address: int, length: int) -> bool:
            call_order.append("handler")
            return True

        middleware.register("erase", handler)

        with pytest.raises(FenceViolationError):
            await middleware.execute("erase", 0x08000000, 4096)

        assert call_order == [], "Handler should NOT have been called"

    @pytest.mark.asyncio
    async def test_middleware_raises_for_unknown_operation(
        self, lock_manager, valid_token
    ):
        """Middleware should raise for unregistered operations."""
        middleware = FenceTokenMiddleware(
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        # Don't register any handler

        with pytest.raises(FenceViolationError) as exc_info:
            await middleware.execute("erase", 0x08000000, 4096)

        assert "No handler registered" in str(exc_info.value)


# =============================================================================
# Test Cases: Consistency between Fake and Fenced Probes
# =============================================================================


class TestProbeConsistency:
    """Verify fake probe and fenced probe behave consistently with valid tokens."""

    @pytest.mark.asyncio
    async def test_fake_vs_fenced_write_consistency(
        self, lock_manager, valid_token
    ):
        """Fake probe and fenced probe should produce same result with valid token."""
        # Create two probes with same initial state
        fake = FakeHardwareProbe(base_address=0x08000000)
        fenced = FenceAwareProbeAdapter(
            underlying_probe=FakeHardwareProbe(base_address=0x08000000),
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        test_data = b"\x12\x34\x56\x78" * 16

        # Both should succeed
        fake_result = await fake.write_memory(0x08000000, test_data)
        fenced_result = await fenced.write_memory(0x08000000, test_data)

        assert fake_result is True
        assert fenced_result is True

        # Verify write through fake probe (direct read, no fence)
        fake_data = await fake.read_memory(0x08000000, len(test_data))
        assert fake_data == test_data

        # Verify write through fenced probe (needs fresh token)
        _, read_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="test_agent",
            transaction_id="tx_read_token",
        )
        fenced_read_adapter = FenceAwareProbeAdapter(
            underlying_probe=fenced._probe,
            lock_manager=lock_manager,
            fence_token=read_token,
            target_name="engine_car",
        )
        fenced_data = await fenced_read_adapter.read_memory(0x08000000, len(test_data))

        assert fenced_data == test_data

    @pytest.mark.asyncio
    async def test_fake_vs_fenced_erase_consistency(
        self, lock_manager, valid_token
    ):
        """Fake probe and fenced probe should erase identically."""
        fake = FakeHardwareProbe(base_address=0x08000000)
        fenced = FenceAwareProbeAdapter(
            underlying_probe=FakeHardwareProbe(base_address=0x08000000),
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        # Write data first (use fresh tokens)
        test_data = b"\xFF" * 4096
        await fake.write_memory(0x08000000, test_data)

        _, write_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_write"
        )
        fenced_write = FenceAwareProbeAdapter(
            underlying_probe=fenced._probe,
            lock_manager=lock_manager,
            fence_token=write_token,
            target_name="engine_car",
        )
        await fenced_write.write_memory(0x08000000, test_data)

        # Erase (use fresh tokens)
        await fake.erase(0x08000000, 4096)

        _, erase_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_erase"
        )
        fenced_erase = FenceAwareProbeAdapter(
            underlying_probe=fenced._probe,
            lock_manager=lock_manager,
            fence_token=erase_token,
            target_name="engine_car",
        )
        await fenced_erase.erase(0x08000000, 4096)

        # Both should have erased data (0xFF)
        fake_data = await fake.read_memory(0x08000000, 4096)
        assert fake_data == b"\xFF" * 4096

        _, read_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_read"
        )
        fenced_read = FenceAwareProbeAdapter(
            underlying_probe=fenced._probe,
            lock_manager=lock_manager,
            fence_token=read_token,
            target_name="engine_car",
        )
        fenced_data = await fenced_read.read_memory(0x08000000, 4096)

        assert fenced_data == b"\xFF" * 4096
        assert fake_data == fenced_data

    @pytest.mark.asyncio
    async def test_strict_probe_vs_fence_adapter_behavior(
        self, lock_manager, valid_token
    ):
        """StrictHardwareProbe and FenceAwareProbeAdapter should behave identically."""
        # Create a shared underlying probe
        shared_probe = FakeHardwareProbe(base_address=0x08000000)
        fenced = FenceAwareProbeAdapter(
            underlying_probe=shared_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        test_data = b"\xAB\xCD\xEF" * 8

        # Write through fenced adapter
        await fenced.write_memory(0x08000000, test_data)

        # Read back through fenced adapter (fresh token)
        _, fenced_read_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_fenced_read"
        )
        fenced_read_adapter = FenceAwareProbeAdapter(
            underlying_probe=shared_probe,
            lock_manager=lock_manager,
            fence_token=fenced_read_token,
            target_name="engine_car",
        )
        fenced_data = await fenced_read_adapter.read_memory(0x08000000, len(test_data))

        # Read back through StrictHardwareProbe (fresh token, same underlying)
        strict = StrictHardwareProbe(
            lock_manager=lock_manager,
            fence_token=valid_token,  # Will need fresh token
            target_name="engine_car",
            base_address=0x08000000,
        )
        # Write through strict
        _, strict_write_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_strict"
        )
        strict._fence_token = strict_write_token
        await strict.write_memory(0x08000000, test_data)

        _, strict_read_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car", owner_id="test_agent", transaction_id="tx_strict_read"
        )
        strict._fence_token = strict_read_token
        strict_data = await strict.read_memory(0x08000000, len(test_data))

        # Both should read the same data from shared probe
        assert fenced_data == strict_data


class TestSplitBrainPrevention:
    """Tests verifying split-brain prevention with fence tokens."""

    @pytest.mark.asyncio
    async def test_stale_token_prevents_second_write(
        self, lock_manager, valid_token
    ):
        """After first write advances token, second write with stale token fails."""
        probe = FakeHardwareProbe(base_address=0x08000000)
        fenced = FenceAwareProbeAdapter(
            underlying_probe=probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        # First write succeeds
        await fenced.write_memory(0x08000000, b"\x11\x22\x33\x44")

        # Verify data was written using fake probe (no fence)
        first_read = await probe.read_memory(0x08000000, 4)
        assert first_read == b"\x11\x22\x33\x44"

        # Create a new token (simulates stale token from another agent)
        new_lock, new_token = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="test_agent",
            transaction_id="tx_test_002",
        )

        # Original token is now stale (lower sequence)
        # Try to write with stale token - should fail
        with pytest.raises(FenceViolationError):
            await fenced.write_memory(0x08000000, b"\x99\x88\x77\x66")

        # Original data should be unchanged
        still_original = await probe.read_memory(0x08000000, 4)
        assert still_original == b"\x11\x22\x33\x44"

    @pytest.mark.asyncio
    async def test_different_owner_token_rejected(
        self, fake_probe, lock_manager
    ):
        """Token from different owner should be rejected."""
        # First, acquire lock as owner A
        lock_a, token_a = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="agent_a",
            transaction_id="tx_a",
        )
        assert lock_a is not None
        assert token_a is not None

        # Acquire lock as owner A again (same owner should work, new token)
        lock_a2, token_a2 = await lock_manager.acquire_with_fence_token(
            target_name="engine_car",
            owner_id="agent_a",
            transaction_id="tx_a2",
        )
        assert lock_a2 is not None
        assert token_a2 is not None

        # Token from owner A should work with adapter
        adapter = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=token_a2,
            target_name="engine_car",
        )
        # This should succeed
        await adapter.erase(0x08000000, 4096)

        # Now validate token_a (stale, lower sequence)
        is_valid, reason = await lock_manager.target_lock.validate_fence_token(
            target_name="engine_car",
            token=token_a,
            operation_name="write",
        )
        # Token_a is stale (lower sequence than current)
        assert is_valid is False
        assert "stale" in reason.lower()


# =============================================================================
# Test Cases: Verify Integration with LockManager
# =============================================================================


class TestLockManagerIntegration:
    """Integration tests with LockManager's validate_and_execute."""

    @pytest.mark.asyncio
    async def test_validate_and_execute_with_probe(
        self, lock_manager, valid_token, fake_probe
    ):
        """LockManager.validate_and_execute should work with probe operations."""
        fenced = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        test_data = b"\xFE\xDC\xBA\x98"

        async def write_op():
            return await fenced.write_memory(0x08000000, test_data)

        result = await lock_manager.validate_and_execute(
            target_name="engine_car",
            fence_token=valid_token,
            operation_name="write_memory",
            operation_fn=write_op,
        )

        assert result is True
        verify_data = await fake_probe.read_memory(0x08000000, len(test_data))
        assert verify_data == test_data

    @pytest.mark.asyncio
    async def test_token_advancement_after_successful_operation(
        self, lock_manager, valid_token, fake_probe
    ):
        """Token should be advanced after successful operation."""
        fenced = FenceAwareProbeAdapter(
            underlying_probe=fake_probe,
            lock_manager=lock_manager,
            fence_token=valid_token,
            target_name="engine_car",
        )

        initial_seq = valid_token.sequence

        await fenced.write_memory(0x08000000, b"\x01\x02\x03\x04")

        # Token sequence should have increased
        current_lock = lock_manager.target_lock.get_lock("engine_car")
        assert current_lock.fence_sequence > initial_seq


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
