"""Tests for Flash Rate Limit - Fleet safety."""

import pytest
import asyncio
from datetime import datetime, timedelta

from src.domain.hardware.flash.flash_rate_limit import (
    ThermalState,
    ThermalConfig,
    PowerConfig,
    RateLimitConfig,
    DeviceThermalState,
    FlashRateLimiter,
    ThermalMonitor,
    PowerBudgetManager,
    FleetSafetyController,
)


class TestThermalState:
    """Test thermal state tracking."""
    
    def test_create_device_state(self):
        """Test creating device thermal state."""
        device = DeviceThermalState(device_id="test_probe_001")
        
        assert device.device_id == "test_probe_001"
        assert device.thermal_state == ThermalState.COOL
        assert device.current_temp == 25.0
    
    def test_update_temperature(self):
        """Test temperature update."""
        device = DeviceThermalState(device_id="test")
        
        device.update_temperature(45.0)
        
        assert device.current_temp == 45.0
        assert device.max_temp >= 45.0
    
    def test_thermal_state_transitions(self):
        """Test thermal state transitions."""
        device = DeviceThermalState(device_id="test")
        config = ThermalConfig()
        
        # Cool -> Warm
        device.update_temperature(41.0)
        assert device.thermal_state == ThermalState.WARM
        
        # Warm -> Hot
        device.update_temperature(55.0)
        assert device.thermal_state == ThermalState.HOT
        
        # Hot -> Critical
        device.update_temperature(65.0)
        assert device.thermal_state == ThermalState.CRITICAL
    
    def test_needs_cooldown_warm(self):
        """Test cooldown not needed when warm."""
        device = DeviceThermalState(device_id="test")
        device.update_temperature(45.0)
        
        assert device.needs_cooldown() is False
    
    def test_needs_cooldown_hot(self):
        """Test cooldown needed when hot."""
        device = DeviceThermalState(device_id="test")
        device.update_temperature(55.0)
        
        assert device.needs_cooldown() is True
    
    def test_start_cooldown(self):
        """Test starting cooldown."""
        device = DeviceThermalState(device_id="test")
        device.update_temperature(55.0)
        
        device.start_cooldown(30000)  # 30 seconds
        
        assert device.cooldown_until is not None
        assert device.flashes_since_cooldown == 0
        assert device.needs_cooldown() is True  # Still in cooldown
    
    def test_record_flash(self):
        """Test recording flash operation."""
        device = DeviceThermalState(device_id="test")
        
        device.record_flash(5000)  # 5 second flash
        
        assert device.flashes_since_cooldown == 1
        assert device.last_flash_time is not None


class TestFlashRateLimiter:
    """Test FlashRateLimiter class."""
    
    @pytest.fixture
    def limiter(self):
        """Create rate limiter."""
        config = RateLimitConfig(
            max_concurrent_flashes=4,
            max_flashes_per_minute=60,
        )
        return FlashRateLimiter(config=config)
    
    @pytest.mark.asyncio
    async def test_acquire_slot(self, limiter):
        """Test acquiring flash slot."""
        result = await limiter.acquire_flash_slot(timeout_ms=1000)
        
        assert result is True
        assert limiter._active_flashes == 1
    
    @pytest.mark.asyncio
    async def test_release_slot(self, limiter):
        """Test releasing flash slot."""
        await limiter.acquire_flash_slot()
        await limiter.release_flash_slot()
        
        assert limiter._active_flashes == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_limit(self, limiter):
        """Test concurrent flash limit."""
        # Acquire all slots
        for _ in range(4):
            result = await limiter.acquire_flash_slot(timeout_ms=100)
            assert result is True
        
        # Should fail on 5th
        result = await limiter.acquire_flash_slot(timeout_ms=100)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_status(self, limiter):
        """Test getting status."""
        await limiter.acquire_flash_slot()
        
        status = limiter.get_status()
        
        assert "active_flashes" in status
        assert status["active_flashes"] == 1


class TestThermalMonitor:
    """Test ThermalMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create thermal monitor."""
        config = ThermalConfig(
            temp_warm_threshold=40.0,
            temp_hot_threshold=50.0,
        )
        return ThermalMonitor(config=config)
    
    @pytest.mark.asyncio
    async def test_register_device(self, monitor):
        """Test registering device."""
        await monitor.register_device("probe_001")
        
        status = monitor.get_device_status("probe_001")
        
        assert status is not None
        assert status["device_id"] == "probe_001"
    
    @pytest.mark.asyncio
    async def test_record_temperature(self, monitor):
        """Test recording temperature."""
        await monitor.register_device("probe_001")
        await monitor.record_temperature("probe_001", 55.0)
        
        status = monitor.get_device_status("probe_001")
        
        assert status["current_temp"] == 55.0
        assert status["thermal_state"] == "hot"
    
    @pytest.mark.asyncio
    async def test_check_device_ready(self, monitor):
        """Test checking device readiness."""
        await monitor.register_device("probe_001")
        await monitor.record_temperature("probe_001", 60.0)  # Critical
        
        ready, reason = await monitor.check_device_ready("probe_001")
        
        assert ready is False
        assert "critical" in reason.lower() or "cooling" in reason.lower()


class TestPowerBudgetManager:
    """Test PowerBudgetManager class."""
    
    @pytest.fixture
    def power_manager(self):
        """Create power manager."""
        config = PowerConfig(
            power_budget_ma=1000,
            flash_power_ma=100,
        )
        return PowerBudgetManager(config=config)
    
    @pytest.mark.asyncio
    async def test_allocate_power(self, power_manager):
        """Test power allocation."""
        result = await power_manager.allocate_power("probe_001", "flash")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_power_budget_exceeded(self, power_manager):
        """Test power budget limit."""
        # Allocate budget
        for i in range(10):
            await power_manager.allocate_power(f"probe_{i:03d}", "flash")
        
        # Should fail on 11th (10 * 100ma = 1000ma budget)
        result = await power_manager.allocate_power("probe_over", "flash")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_release_power(self, power_manager):
        """Test releasing power."""
        await power_manager.allocate_power("probe_001", "flash")
        await power_manager.release_power("probe_001")
        
        available = await power_manager.check_available_power()
        
        assert available == 1000  # Full budget available
    
    @pytest.mark.asyncio
    async def test_get_status(self, power_manager):
        """Test getting power status."""
        await power_manager.allocate_power("probe_001", "flash")
        
        status = power_manager.get_status()
        
        assert "budget_ma" in status
        assert status["used_ma"] == 100


class TestFleetSafetyController:
    """Test FleetSafetyController class."""
    
    @pytest.fixture
    def controller(self):
        """Create fleet safety controller."""
        rate_config = RateLimitConfig(
            max_concurrent_flashes=8,
        )
        rate_limiter = FlashRateLimiter(config=rate_config)
        
        thermal_config = ThermalConfig()
        thermal_monitor = ThermalMonitor(config=thermal_config)
        
        power_config = PowerConfig(
            power_budget_ma=1000,
            flash_power_ma=100,
        )
        power_manager = PowerBudgetManager(config=power_config)
        
        return FleetSafetyController(
            rate_limiter=rate_limiter,
            thermal_monitor=thermal_monitor,
            power_manager=power_manager,
        )
    
    @pytest.mark.asyncio
    async def test_can_flash_all_ok(self, controller):
        """Test can_flash when all systems OK."""
        can_flash, reason = await controller.can_flash("probe_001")
        
        assert can_flash is True
        assert reason == ""
    
    @pytest.mark.asyncio
    async def test_can_flash_power_exceeded(self, controller):
        """Test can_flash when power exceeded."""
        # Exhaust power budget
        for i in range(10):
            await controller.power_manager.allocate_power(f"probe_{i:03d}", "flash")
        
        can_flash, reason = await controller.can_flash("probe_over")
        
        assert can_flash is False
        assert "power" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_request_flash(self, controller):
        """Test requesting flash slot."""
        granted, reason = await controller.request_flash("probe_001")
        
        assert granted is True
    
    @pytest.mark.asyncio
    async def test_complete_flash(self, controller):
        """Test completing flash operation."""
        await controller.request_flash("probe_001")
        
        await controller.complete_flash("probe_001", 5000, success=True)
        
        status = controller.get_full_status()
        
        assert "rate_limiter" in status
        assert status["rate_limiter"]["active_flashes"] == 0
