"""Unit tests for Flash Transaction Model."""

import pytest
import asyncio
from datetime import datetime
from src.domain.hardware.flash.flash_transaction import (
    TransactionStatus,
    FlashTransaction,
    FlashTransactionManager,
    PartialFlashDetector,
    PartialFlashInfo,
)


class TestFlashTransaction:
    """Tests for FlashTransaction dataclass."""
    
    def test_transaction_creation(self):
        """Test transaction creation with defaults."""
        tx = FlashTransaction(
            target_name="test_target",
            target_id="target_001",
            new_firmware_hash="abc123",
            new_firmware_version="1.0.0",
            new_firmware_size=1024,
        )
        
        assert tx.transaction_id is not None
        assert tx.target_name == "test_target"
        assert tx.status == TransactionStatus.PENDING
        assert tx.created_at is not None
        assert tx.bytes_written == 0
    
    def test_transaction_to_dict(self):
        """Test transaction serialization."""
        tx = FlashTransaction(
            target_name="test_target",
            target_id="target_001",
            new_firmware_hash="abc123",
            new_firmware_version="1.0.0",
            new_firmware_size=1024,
        )
        
        data = tx.to_dict()
        
        assert data["target_name"] == "test_target"
        assert data["status"] == "pending"
        assert data["new_firmware_hash"] == "abc123"
    
    def test_is_terminal(self):
        """Test terminal state detection."""
        tx = FlashTransaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        assert not tx.is_terminal()
        
        tx.status = TransactionStatus.COMMITTED
        assert tx.is_terminal()
        
        tx.status = TransactionStatus.ROLLED_BACK
        assert tx.is_terminal()
    
    def test_can_rollback(self):
        """Test rollback eligibility."""
        tx = FlashTransaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        # Cannot rollback when not failed
        assert not tx.can_rollback()
        
        # Can rollback when failed with snapshot
        tx.status = TransactionStatus.FAILED
        tx.rollback_snapshot_id = "snap_123"
        assert tx.can_rollback()
        
        # Cannot rollback when failed without snapshot
        tx.rollback_snapshot_id = None
        assert not tx.can_rollback()
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        tx = FlashTransaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        tx.started_at = datetime.now()
        
        # Without completion, returns current duration
        duration = tx.duration_seconds()
        assert duration >= 0


class TestTransactionStatus:
    """Tests for TransactionStatus enum."""
    
    def test_all_statuses_defined(self):
        """Test all expected statuses exist."""
        expected = [
            "pending", "flashing", "verifying", "committed",
            "failed", "rolled_back", "interrupted"
        ]
        
        for status in expected:
            assert hasattr(TransactionStatus, status.upper())
    
    def test_status_values(self):
        """Test status enum values."""
        assert TransactionStatus.PENDING.value == "pending"
        assert TransactionStatus.FAILED.value == "failed"


class TestPartialFlashInfo:
    """Tests for PartialFlashInfo."""
    
    def test_creation(self):
        """Test partial flash info creation."""
        info = PartialFlashInfo(
            transaction_id="tx_123",
            target_name="test_target",
            interrupted_at=datetime.now(),
            bytes_written=500,
            resume_state={"last_sector": 5},
            old_firmware_hash="old123",
            new_firmware_hash="new456",
        )
        
        assert info.transaction_id == "tx_123"
        assert info.bytes_written == 500
        assert info.detected_at is not None
    
    def test_to_dict(self):
        """Test serialization."""
        info = PartialFlashInfo(
            transaction_id="tx_123",
            target_name="test_target",
            interrupted_at=None,
            bytes_written=500,
            resume_state=None,
            old_firmware_hash="old",
            new_firmware_hash="new",
        )
        
        data = info.to_dict()
        
        assert data["transaction_id"] == "tx_123"
        assert data["interrupted_at"] is None


class TestFlashTransactionManager:
    """Tests for FlashTransactionManager."""
    
    @pytest.fixture
    async def manager(self, tmp_path):
        """Create manager with temporary database."""
        db_path = str(tmp_path / "test_transactions.db")
        manager = FlashTransactionManager(db_path=db_path)
        await manager.initialize()
        yield manager
        await manager.close()
    
    @pytest.mark.asyncio
    async def test_create_transaction(self, manager):
        """Test transaction creation."""
        tx = await manager.create_transaction(
            target_name="test_target",
            target_id="target_001",
            new_firmware_hash="abc123",
            new_firmware_version="1.0.0",
            new_firmware_size=1024,
        )
        
        assert tx.transaction_id is not None
        assert tx.status == TransactionStatus.PENDING
        assert tx.target_name == "test_target"
    
    @pytest.mark.asyncio
    async def test_start_transaction(self, manager):
        """Test starting a transaction."""
        tx = await manager.create_transaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        started = await manager.start_transaction(tx.transaction_id)
        
        assert started is not None
        assert started.status == TransactionStatus.FLASING
        assert started.started_at is not None
    
    @pytest.mark.asyncio
    async def test_commit_transaction(self, manager):
        """Test committing a transaction."""
        tx = await manager.create_transaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        await manager.start_transaction(tx.transaction_id)
        committed = await manager.commit_transaction(tx.transaction_id)
        
        assert committed is not None
        assert committed.status == TransactionStatus.COMMITTED
        assert committed.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_fail_transaction(self, manager):
        """Test failing a transaction."""
        tx = await manager.create_transaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        await manager.start_transaction(tx.transaction_id)
        failed = await manager.fail_transaction(
            tx.transaction_id,
            error_code="TEST_ERROR",
            error_message="Test failure",
        )
        
        assert failed is not None
        assert failed.status == TransactionStatus.FAILED
        assert failed.error_code == "TEST_ERROR"
    
    @pytest.mark.asyncio
    async def test_get_pending_transaction(self, manager):
        """Test getting pending transaction."""
        tx = await manager.create_transaction(
            target_name="test_target",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        
        pending = await manager.get_pending_transaction("test_target")
        
        assert pending is not None
        assert pending.transaction_id == tx.transaction_id
    
    @pytest.mark.asyncio
    async def test_update_progress(self, manager):
        """Test updating transaction progress."""
        tx = await manager.create_transaction(
            target_name="test",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=1000,
        )
        
        await manager.start_transaction(tx.transaction_id)
        await manager.update_progress(
            tx.transaction_id,
            bytes_written=500,
            sectors_erased=5,
        )
        
        updated = await manager.get_transaction(tx.transaction_id)
        assert updated.bytes_written == 500
        assert updated.sectors_erased == 5
    
    @pytest.mark.asyncio
    async def test_list_transactions(self, manager):
        """Test listing transactions."""
        await manager.create_transaction(
            target_name="test1",
            target_id="001",
            new_firmware_hash="abc",
            new_firmware_version="1.0",
            new_firmware_size=100,
        )
        await manager.create_transaction(
            target_name="test2",
            target_id="002",
            new_firmware_hash="def",
            new_firmware_version="1.1",
            new_firmware_size=200,
        )
        
        all_tx = await manager.list_transactions()
        assert len(all_tx) == 2
        
        filtered = await manager.list_transactions(target_name="test1")
        assert len(filtered) == 1
        assert filtered[0].target_name == "test1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
