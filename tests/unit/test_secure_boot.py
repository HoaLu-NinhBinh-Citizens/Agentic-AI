"""Unit tests for Secure Boot."""

import pytest
from src.domain.hardware.flash.secure_boot import (
    BootState,
    SecureBootPolicy,
    AntiRollbackChecker,
    MonotonicCounterUpdater,
    SecureBootValidator,
)


class TestBootState:
    """Tests for BootState enum."""
    
    def test_all_states_defined(self):
        """Test all boot states exist."""
        assert BootState.TRUSTED.value == "trusted"
        assert BootState.UNTRUSTED.value == "untrusted"
        assert BootState.DISABLED.value == "disabled"
        assert BootState.UNKNOWN.value == "unknown"


class TestSecureBootPolicy:
    """Tests for SecureBootPolicy."""
    
    def test_disabled_policy(self):
        """Test disabled policy."""
        policy = SecureBootPolicy.disabled()
        
        assert not policy.enabled
        assert not policy.anti_rollback_enabled
    
    def test_stm32_basic_policy(self):
        """Test STM32 basic policy."""
        policy = SecureBootPolicy.stm32_basic()
        
        assert policy.enabled
        assert policy.anti_rollback_enabled
        assert policy.version_storage_address == 0x1FFFF7E0
    
    def test_from_config(self):
        """Test creating from config."""
        config = {
            "enabled": True,
            "anti_rollback": True,
            "min_version": 5,
            "version_address": 0x1FFF8000,
            "monotonic_counter": True,
            "monotonic_counter_addr": 0x1FFFF7E8,
        }
        
        policy = SecureBootPolicy.from_config(config)
        
        assert policy.enabled
        assert policy.anti_rollback_enabled
        assert policy.anti_rollback_version == 5
        assert policy.monotonic_counter_enabled
    
    def test_to_dict(self):
        """Test serialization."""
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            anti_rollback_version=3,
            version_storage_address=0x1FFF8000,
        )
        
        data = policy.to_dict()
        
        assert data["enabled"] is True
        assert data["anti_rollback_enabled"] is True
        assert data["anti_rollback_version"] == 3


class TestAntiRollbackChecker:
    """Tests for AntiRollbackChecker."""
    
    @pytest.mark.asyncio
    async def test_disabled_anti_rollback(self):
        """Test when anti-rollback is disabled."""
        policy = SecureBootPolicy(enabled=True, anti_rollback_enabled=False)
        checker = AntiRollbackChecker(policy)
        
        allowed, reason = await checker.check(new_version=1)
        
        assert allowed
        assert "disabled" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_version_upgrade_allowed(self):
        """Test version upgrade is allowed."""
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            anti_rollback_version=2,
        )
        checker = AntiRollbackChecker(policy)
        
        allowed, reason = await checker.check(
            current_version=3,
            new_version=5,
        )
        
        assert allowed
    
    @pytest.mark.asyncio
    async def test_downgrade_rejected(self):
        """Test version downgrade is rejected."""
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            anti_rollback_version=3,
        )
        checker = AntiRollbackChecker(policy)
        
        allowed, reason = await checker.check(
            current_version=5,
            new_version=2,
        )
        
        assert not allowed
        assert "Anti-rollback" in reason or "downgrade" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_equal_version_allowed(self):
        """Test equal version is allowed."""
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            anti_rollback_version=3,
        )
        checker = AntiRollbackChecker(policy)
        
        allowed, reason = await checker.check(
            current_version=3,
            new_version=3,
        )
        
        assert allowed


class TestMonotonicCounterUpdater:
    """Tests for MonotonicCounterUpdater."""
    
    def test_disabled_counter(self):
        """Test when counter is disabled."""
        policy = SecureBootPolicy(enabled=True, monotonic_counter_enabled=False)
        updater = MonotonicCounterUpdater(policy)
        
        # Should return True without doing anything
        result = asyncio.run(updater.update(new_version=1))
        assert result is True
    
    @pytest.mark.asyncio
    async def test_missing_address(self):
        """Test when address is not configured."""
        policy = SecureBootPolicy(
            enabled=True,
            monotonic_counter_enabled=True,
            monotonic_counter_address=None,
        )
        updater = MonotonicCounterUpdater(policy)
        
        # Should return False
        result = await updater.update(new_version=1)
        assert result is False


class TestSecureBootValidator:
    """Tests for SecureBootValidator."""
    
    @pytest.mark.asyncio
    async def test_disabled_validation(self):
        """Test validation when secure boot is disabled."""
        policy = SecureBootPolicy(enabled=False)
        validator = SecureBootValidator(policy)
        
        allowed, reason = await validator.pre_flash_check(new_version=1)
        
        assert allowed
        assert "disabled" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_anti_rollback_check(self):
        """Test anti-rollback check in validator."""
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            anti_rollback_version=5,
        )
        validator = SecureBootValidator(policy)
        
        # Downgrade should fail
        allowed, reason = await validator.pre_flash_check(new_version=2)
        assert not allowed
        
        # Upgrade should pass
        allowed, reason = await validator.pre_flash_check(new_version=10)
        assert allowed
    
    @pytest.mark.asyncio
    async def test_boot_state(self):
        """Test boot state retrieval."""
        policy = SecureBootPolicy(enabled=False)
        validator = SecureBootValidator(policy)
        
        state = await validator.get_boot_state()
        assert state == BootState.DISABLED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
