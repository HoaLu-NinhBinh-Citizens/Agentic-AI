"""Unit tests for Flash Lock."""

import pytest
import asyncio
from datetime import datetime, timedelta
from src.domain.hardware.flash.flash_lock import (
    FlashLock,
    TargetFlashLock,
    LockManager,
)


class TestFlashLock:
    """Tests for FlashLock."""
    
    def test_lock_creation(self):
        """Test lock creation."""
        lock = FlashLock(
            target_name="test_target",
            owner_id="agent_001",
        )
        
        assert lock.target_name == "test_target"
        assert lock.owner_id == "agent_001"
        assert lock.acquired_at is not None
        assert lock.version == 1
    
    def test_is_valid(self):
        """Test lock validity check."""
        lock = FlashLock(
            target_name="test",
            owner_id="agent",
            expires_at=datetime.now() + timedelta(seconds=60),
        )
        
        assert lock.is_valid()
        
        # Expired lock
        lock.expires_at = datetime.now() - timedelta(seconds=1)
        assert not lock.is_valid()
    
    def test_renew(self):
        """Test lock renewal."""
        lock = FlashLock(
            target_name="test",
            owner_id="agent",
            expires_at=datetime.now() + timedelta(seconds=10),
        )
        
        result = lock.renew()
        
        assert result is True
        assert lock.version == 2
        assert lock.expires_at > datetime.now()
    
    def test_renew_invalid_lock(self):
        """Test renewal of invalid lock fails."""
        lock = FlashLock(
            target_name="test",
            owner_id="agent",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        
        result = lock.renew()
        
        assert result is False
    
    def test_to_dict(self):
        """Test serialization."""
        lock = FlashLock(
            target_name="test_target",
            owner_id="agent_001",
        )
        
        data = lock.to_dict()
        
        assert data["target_name"] == "test_target"
        assert data["owner_id"] == "agent_001"


class TestTargetFlashLock:
    """Tests for TargetFlashLock."""
    
    @pytest.fixture
    def lock_manager(self):
        """Create lock manager."""
        return TargetFlashLock(
            lease_timeout_seconds=5,
            renew_interval_seconds=2,
        )
    
    def test_not_locked_initially(self, lock_manager):
        """Test target is not locked initially."""
        assert not lock_manager.is_locked("test_target")
        assert lock_manager.get_lock_owner("test_target") is None
    
    @pytest.mark.asyncio
    async def test_acquire_lock(self, lock_manager):
        """Test acquiring a lock."""
        lock = await lock_manager.acquire("test_target", "agent_001")
        
        assert lock is not None
        assert lock.target_name == "test_target"
        assert lock.owner_id == "agent_001"
        assert lock_manager.is_locked("test_target")
    
    @pytest.mark.asyncio
    async def test_release_lock(self, lock_manager):
        """Test releasing a lock."""
        await lock_manager.acquire("test_target", "agent_001")
        
        result = await lock_manager.release("test_target", "agent_001")
        
        assert result is True
        assert not lock_manager.is_locked("test_target")
    
    @pytest.mark.asyncio
    async def test_cannot_release_other_owner(self, lock_manager):
        """Test other owner cannot release lock."""
        await lock_manager.acquire("test_target", "agent_001")
        
        result = await lock_manager.release("test_target", "agent_002")
        
        assert result is False
        assert lock_manager.is_locked("test_target")
    
    @pytest.mark.asyncio
    async def test_same_owner_reacquire(self, lock_manager):
        """Test same owner can reacquire."""
        await lock_manager.acquire("test_target", "agent_001")
        
        lock2 = await lock_manager.acquire("test_target", "agent_001")
        
        assert lock2 is not None
        assert lock2.owner_id == "agent_001"
    
    @pytest.mark.asyncio
    async def test_different_owner_blocked(self, lock_manager):
        """Test different owner is blocked."""
        await lock_manager.acquire("test_target", "agent_001")
        
        # Try with very short timeout
        lock2 = await lock_manager.acquire(
            "test_target",
            "agent_002",
            timeout_seconds=0.1,
        )
        
        assert lock2 is None
    
    @pytest.mark.asyncio
    async def test_extend_lock(self, lock_manager):
        """Test extending lock timeout."""
        await lock_manager.acquire("test_target", "agent_001")
        
        result = await lock_manager.extend(
            "test_target",
            "agent_001",
            additional_seconds=30,
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_force_release(self, lock_manager):
        """Test force releasing a lock."""
        await lock_manager.acquire("test_target", "agent_001")
        
        result = await lock_manager.force_release("test_target")
        
        assert result is True
        assert not lock_manager.is_locked("test_target")
    
    @pytest.mark.asyncio
    async def test_get_all_locks(self, lock_manager):
        """Test getting all locks."""
        await lock_manager.acquire("target1", "agent_001")
        await lock_manager.acquire("target2", "agent_002")
        
        locks = lock_manager.get_all_locks()
        
        assert len(locks) == 2
        assert "target1" in locks
        assert "target2" in locks


class TestLockManager:
    """Tests for LockManager."""
    
    @pytest.fixture
    def lock_manager(self):
        """Create lock manager."""
        return TargetFlashLock()
    
    @pytest.fixture
    def manager(self, lock_manager):
        """Create manager."""
        return LockManager(target_lock=lock_manager)
    
    @pytest.mark.asyncio
    async def test_acquire_and_publish(self, manager, lock_manager):
        """Test acquire with event publishing."""
        lock = await manager.acquire_and_publish("test_target", "agent_001")
        
        assert lock is not None
        assert lock.target_name == "test_target"
    
    @pytest.mark.asyncio
    async def test_release_and_publish(self, manager, lock_manager):
        """Test release with event publishing."""
        await manager.acquire_and_publish("test_target", "agent_001")
        
        released = await manager.release_and_publish("test_target", "agent_001")
        
        assert released
        assert not lock_manager.is_locked("test_target")
    
    @pytest.mark.asyncio
    async def test_get_lock_status(self, manager, lock_manager):
        """Test getting lock status."""
        await manager.acquire_and_publish("test_target", "agent_001")
        
        status = await manager.get_lock_status("test_target")
        
        assert status["locked"] is True
        assert status["owner_id"] == "agent_001"
        assert "expires_at" in status
    
    @pytest.mark.asyncio
    async def test_unlocked_status(self, manager, lock_manager):
        """Test status of unlocked target."""
        status = await manager.get_lock_status("test_target")
        
        assert status["locked"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
