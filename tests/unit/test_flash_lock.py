"""Unit tests for Flash Lock - P0-C: Fencing Token Lock Model.

This module tests the fencing token implementation for split-brain prevention.

P0-C Tests:
1. Deterministic fence token generation
2. Token validation on every operation
3. Split-brain prevention
4. Stale token rejection
5. Operation ledger tracking
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from src.domain.hardware.flash.flash_lock import (
    FlashLock,
    FlashFenceToken,
    TargetFlashLock,
    LockManager,
    FenceValidationError,
    OperationLedger,
    FlashOperationRecord,
    deterministic_fence_token,
)


class TestDeterministicFenceToken:
    """Tests for deterministic fence token generation (P0-A alignment)."""

    def test_deterministic_token_same_seed(self):
        """Same lock_id + sequence must produce same token."""
        token1 = deterministic_fence_token("target_A", 5)
        token2 = deterministic_fence_token("target_A", 5)
        
        assert token1 == token2, "Fence token must be deterministic"

    def test_deterministic_token_different_sequences(self):
        """Different sequences must produce different tokens."""
        token1 = deterministic_fence_token("target_A", 1)
        token2 = deterministic_fence_token("target_A", 2)
        token3 = deterministic_fence_token("target_A", 3)
        
        assert len({token1, token2, token3}) == 3

    def test_deterministic_token_different_targets(self):
        """Different targets must produce different tokens."""
        token1 = deterministic_fence_token("target_A", 1)
        token2 = deterministic_fence_token("target_B", 1)
        
        assert token1 != token2

    def test_deterministic_token_format(self):
        """Token must be valid UUID format."""
        token = deterministic_fence_token("target", 1)
        
        parts = token.split("-")
        assert len(parts) == 5


class TestFlashFenceToken:
    """Tests for FlashFenceToken."""

    def test_token_auto_generates_id(self):
        """Token auto-generates deterministic ID from lock_id + sequence."""
        token = FlashFenceToken(
            sequence=5,
            lock_id="test_target",
            transaction_id="tx_1",
            owner_id="agent_1",
        )
        
        # Token should be auto-generated from lock_id + sequence
        assert token.token is not None
        assert token.token != ""

    def test_token_validation_valid(self):
        """Valid token passes validation."""
        token = FlashFenceToken(
            sequence=1,
            lock_id="test",
            transaction_id="tx_1",
            owner_id="agent_1",
        )
        
        is_valid, reason = token.validate_for_operation("write")
        
        assert is_valid is True
        assert reason == ""

    def test_token_validation_revoked(self):
        """Revoked token fails validation."""
        token = FlashFenceToken(
            sequence=1,
            lock_id="test",
            transaction_id="tx_1",
            owner_id="agent_1",
        )
        token.revoke()
        
        is_valid, reason = token.validate_for_operation("write")
        
        assert is_valid is False
        assert "revoked" in reason.lower()

    def test_token_validation_expired(self):
        """Expired token fails validation."""
        token = FlashFenceToken(
            sequence=1,
            lock_id="test",
            transaction_id="tx_1",
            owner_id="agent_1",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        
        is_valid, reason = token.validate_for_operation("write")
        
        assert is_valid is False
        assert "expired" in reason.lower()


class TestFenceTokenSequence:
    """Tests for fence token sequence enforcement."""

    @pytest.fixture
    def lock_manager(self):
        return TargetFlashLock(lease_timeout_seconds=60)

    @pytest.mark.asyncio
    async def test_token_sequence_increments(self, lock_manager):
        """Each token must have higher sequence."""
        # Acquire lock
        lock = await lock_manager.acquire("test_target", "agent_1")
        assert lock is not None
        
        # Issue multiple tokens
        token1 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        token2 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        token3 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        assert token1.sequence < token2.sequence < token3.sequence

    @pytest.mark.asyncio
    async def test_stale_token_rejected(self, lock_manager):
        """Stale token (lower sequence) must be rejected."""
        # Acquire lock
        lock = await lock_manager.acquire("test_target", "agent_1")
        
        # Get first token
        token1 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        # Advance sequence (simulate other operations)
        await lock_manager.revoke_fence_token("test_target", "agent_1")
        token2 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        # Try to use stale token1
        is_valid, reason = await lock_manager.validate_fence_token(
            "test_target", token1, "write"
        )
        
        assert is_valid is False
        assert "stale" in reason.lower()


class TestSplitBrainPrevention:
    """P0-C: Tests for split-brain prevention."""

    @pytest.fixture
    def lock_manager(self):
        return TargetFlashLock(lease_timeout_seconds=60)

    @pytest.mark.asyncio
    async def test_cannot_flash_without_token(self, lock_manager):
        """Flash operation without token must fail."""
        # Acquire lock but don't get token
        lock = await lock_manager.acquire("test_target", "agent_1")
        assert lock is not None
        
        # Create a fake token
        fake_token = FlashFenceToken(
            sequence=999,  # High sequence
            lock_id="test_target",
            transaction_id="tx_fake",
            owner_id="malicious_agent",
        )
        
        # Validation should fail due to owner mismatch
        is_valid, reason = await lock_manager.validate_fence_token(
            "test_target", fake_token, "write"
        )
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_owner_mismatch_rejected(self, lock_manager):
        """Token from different owner must be rejected."""
        # Agent 1 acquires lock
        lock = await lock_manager.acquire("test_target", "agent_1")
        token1 = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        # Agent 2 tries to use Agent 1's token
        token1.owner_id = "agent_2"
        
        is_valid, reason = await lock_manager.validate_fence_token(
            "test_target", token1, "write"
        )
        
        assert is_valid is False
        assert "mismatch" in reason.lower() or "owner" in reason.lower()

    @pytest.mark.asyncio
    async def test_operation_after_revocation_fails(self, lock_manager):
        """Operation after token revocation must fail."""
        # Acquire and get token
        lock = await lock_manager.acquire("test_target", "agent_1")
        token = await lock_manager.issue_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        # Revoke token
        await lock_manager.revoke_fence_token("test_target", "agent_1")
        
        # Try to use revoked token
        is_valid, reason = await lock_manager.validate_fence_token(
            "test_target", token, "write"
        )
        
        assert is_valid is False


class TestOperationLedger:
    """Tests for operation ledger tracking."""

    @pytest.fixture
    def ledger(self):
        return OperationLedger(max_records=100)

    @pytest.mark.asyncio
    async def test_append_record(self, ledger):
        """Test appending operation record."""
        token = FlashFenceToken(
            sequence=1,
            lock_id="test_target",
            transaction_id="tx_1",
            owner_id="agent_1",
        )
        
        record = await ledger.append(
            target_name="test_target",
            operation="write",
            fence_token=token,
            address=0x08000000,
            length=1024,
        )
        
        assert record.target_name == "test_target"
        assert record.operation == "write"
        assert record.fence_token == token.token
        assert record.fence_sequence == 1

    @pytest.mark.asyncio
    async def test_get_latest_for_target(self, ledger):
        """Test retrieving latest records for target."""
        token1 = FlashFenceToken(
            sequence=1, lock_id="test_target",
            transaction_id="tx_1", owner_id="agent_1"
        )
        token2 = FlashFenceToken(
            sequence=2, lock_id="test_target",
            transaction_id="tx_1", owner_id="agent_1"
        )
        
        await ledger.append("test_target", "erase", token1)
        await ledger.append("test_target", "write", token2)
        
        records = await ledger.get_latest_for_target("test_target")
        
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_staleness_detection(self, ledger):
        """Test detecting stale pending operations."""
        token_low = FlashFenceToken(
            sequence=1, lock_id="test_target",
            transaction_id="tx_1", owner_id="agent_1"
        )
        
        # Append a pending operation with low sequence
        record = await ledger.append(
            target_name="test_target",
            operation="write",
            fence_token=token_low,
        )
        # Note: record is pending by default
        
        # Try to validate with higher sequence (should be safe)
        # The ledger check is informational - actual validation is in TargetFlashLock
        is_safe, reason = await ledger.validate_no_stale_operations(
            "test_target", fence_sequence=5
        )
        
        # Ledger reports stale if there are pending ops with lower sequence
        # This is informational - the actual enforcement is in validate_fence_token
        # The test checks that the logic works correctly
        assert is_safe is False  # There IS a pending op with lower sequence

    @pytest.mark.asyncio
    async def test_ledger_max_records(self, ledger):
        """Test ledger respects max records limit."""
        token = FlashFenceToken(
            sequence=1, lock_id="test_target",
            transaction_id="tx_1", owner_id="agent_1"
        )
        
        # Append more than max records
        for i in range(150):
            token.sequence = i
            await ledger.append(
                target_name="test_target",
                operation="write",
                fence_token=token,
            )
        
        # Should be trimmed to max_records
        assert len(ledger._records) <= ledger.max_records


class TestRedisFailFast:
    """P0-C: Tests for Redis fail-fast behavior."""

    @pytest.mark.asyncio
    async def test_memory_fallback_with_flag(self):
        """Test that memory fallback works when explicitly enabled."""
        # Skip if aioredis is not available
        pytest.importorskip("aioredis", reason="aioredis not installed")
        
        lock = TargetFlashLock(
            lock_storage="redis",
            redis_url="redis://invalid:6379",
            fail_if_redis_unavailable=False,  # Explicitly allow fallback
        )
        
        # Should not raise
        try:
            await lock._init_redis()
        except RuntimeError:
            pytest.fail("Should not raise when fail_if_redis_unavailable=False")

    @pytest.mark.asyncio
    async def test_redis_required_for_distributed(self):
        """Test that distributed mode requires Redis."""
        # Skip if aioredis is not available
        pytest.importorskip("aioredis", reason="aioredis not installed")
        
        lock = TargetFlashLock(
            lock_storage="redis",
            redis_url="redis://invalid:6379",
            fail_if_redis_unavailable=True,  # Default for production
        )
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Redis"):
            await lock._init_redis()


class TestLockManagerFenceIntegration:
    """Tests for LockManager with fence token integration."""

    @pytest.fixture
    def target_lock(self):
        return TargetFlashLock(lease_timeout_seconds=60)

    @pytest.fixture
    def manager(self, target_lock):
        return LockManager(target_lock=target_lock)

    @pytest.mark.asyncio
    async def test_acquire_with_fence_token(self, manager):
        """Test atomic acquire + fence token."""
        lock, token = await manager.acquire_with_fence_token(
            target_name="test_target",
            owner_id="agent_1",
            transaction_id="tx_1",
        )
        
        assert lock is not None
        assert token is not None
        assert token.sequence >= 1

    @pytest.mark.asyncio
    async def test_validate_and_execute_success(self, manager):
        """Test successful validation and execution."""
        lock, token = await manager.acquire_with_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        executed = False
        async def mock_write():
            nonlocal executed
            executed = True
            return "success"
        
        result = await manager.validate_and_execute(
            "test_target", token, "write", mock_write
        )
        
        assert executed is True
        assert result == "success"

    @pytest.mark.asyncio
    async def test_validate_and_execute_fails_on_stale_token(self, manager):
        """Test that stale token causes FenceValidationError."""
        lock, token = await manager.acquire_with_fence_token(
            "test_target", "agent_1", "tx_1"
        )
        
        # Revoke the token
        await manager.invalidate_fence_on_failure("test_target", "agent_1")
        
        async def mock_write():
            return "should not execute"
        
        with pytest.raises(FenceValidationError):
            await manager.validate_and_execute(
                "test_target", token, "write", mock_write
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
