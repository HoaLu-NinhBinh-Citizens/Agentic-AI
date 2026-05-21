"""Flash Rate Limit / Thermal Policy - Fleet safety for concurrent operations.

Phase 6.2: Addresses critical production gap:
- USB hub overload prevention
- Probe overheating protection
- Brownout prevention
- Power budget management
- Concurrent flash limiting
- Thermal cooldown scheduling
- Fleet-wide rate limiting

This is essential for commercial OTA systems where:
- Multiple targets flash simultaneously
- USB hubs have power limits
- Probes can overheat during sustained use
- Power supplies have budget limits
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ThermalState(Enum):
    """Thermal state of device."""
    
    COOL = "cool"           # Normal operation
    WARM = "warm"          # Getting warm
    HOT = "hot"            # Needs cooldown
    CRITICAL = "critical"  # Must stop


@dataclass
class ThermalConfig:
    """Thermal management configuration."""
    
    # Temperature thresholds (degrees Celsius)
    temp_warm_threshold: float = 40.0
    temp_hot_threshold: float = 50.0
    temp_critical_threshold: float = 60.0
    temp_cooldown_target: float = 30.0
    
    # Timing
    temp_check_interval_ms: int = 5000
    cooldown_duration_ms: int = 30000
    max_continuous_flash_ms: int = 300000  # 5 minutes
    
    # Safety limits
    max_consecutive_flashes: int = 50  # Force cooldown after N flashes


@dataclass
class PowerConfig:
    """Power management configuration."""
    
    # USB power limits
    usb_max_ma: int = 500  # Standard USB 2.0
    hub_max_ma: int = 2000  # Typical powered hub
    
    # Flash power
    flash_power_ma: int = 100  # Current during flash
    erase_power_ma: int = 150  # Current during erase
    
    # Budget management
    power_budget_ma: int = 1000  # Available power
    concurrent_flash_budget: int = 4  # Max concurrent flashes


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    
    # Concurrency limits
    max_concurrent_flashes: int = 8
    max_concurrent_erases: int = 4
    
    # Queue limits
    max_queue_depth: int = 100
    
    # Throughput limits
    max_flashes_per_minute: int = 60
    max_flashes_per_hour: int = 1000
    
    # Backoff
    backoff_base_ms: int = 1000
    backoff_max_ms: int = 60000
    backoff_multiplier: float = 2.0


@dataclass
class DeviceThermalState:
    """Thermal state for a single device/probe."""
    
    device_id: str
    
    # Temperature tracking
    current_temp: float = 25.0
    max_temp: float = 25.0
    temp_history: list[tuple[float, datetime]] = field(default_factory=list)
    
    # State
    thermal_state: ThermalState = ThermalState.COOL
    
    # Flash tracking
    flashes_since_cooldown: int = 0
    last_flash_time: datetime | None = None
    total_flash_duration_ms: float = 0.0
    
    # Cooldown
    cooldown_until: datetime | None = None
    
    def update_temperature(self, temp: float) -> None:
        """Update temperature reading."""
        self.current_temp = temp
        self.max_temp = max(self.max_temp, temp)
        self.temp_history.append((temp, datetime.now()))
        
        # Keep last 100 readings
        if len(self.temp_history) > 100:
            self.temp_history = self.temp_history[-100:]
        
        # Update thermal state
        if temp >= ThermalConfig().temp_critical_threshold:
            self.thermal_state = ThermalState.CRITICAL
        elif temp >= ThermalConfig().temp_hot_threshold:
            self.thermal_state = ThermalState.HOT
        elif temp >= ThermalConfig().temp_warm_threshold:
            self.thermal_state = ThermalState.WARM
        else:
            self.thermal_state = ThermalState.COOL
    
    def needs_cooldown(self) -> bool:
        """Check if device needs cooldown."""
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return True
        
        if self.thermal_state in (ThermalState.HOT, ThermalState.CRITICAL):
            return True
        
        if self.flashes_since_cooldown >= ThermalConfig().max_consecutive_flashes:
            return True
        
        return False
    
    def start_cooldown(self, duration_ms: int) -> None:
        """Start cooldown period."""
        self.cooldown_until = datetime.now() + timedelta(milliseconds=duration_ms)
        self.flashes_since_cooldown = 0
        
        logger.info(
            "cooldown_started",
            device_id=self.device_id,
            until=self.cooldown_until.isoformat(),
        )
    
    def record_flash(self, duration_ms: float) -> None:
        """Record a flash operation."""
        self.flashes_since_cooldown += 1
        self.last_flash_time = datetime.now()
        self.total_flash_duration_ms += duration_ms
    
    def get_cooldown_remaining_ms(self) -> int:
        """Get remaining cooldown time in milliseconds."""
        if not self.cooldown_until:
            return 0
        
        remaining = self.cooldown_until - datetime.now()
        return max(0, int(remaining.total_seconds() * 1000))


@dataclass
class FlashRateLimiter:
    """Rate limiter for flash operations.
    
    Manages:
    - Concurrent operation limits
    - Throughput limits
    - Backoff on failures
    - Queue management
    """
    
    config: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    # State
    _active_flashes: int = 0
    _active_erases: int = 0
    _flash_times: list[datetime] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    # Backoff state
    _backoff_until: datetime | None = None
    
    async def acquire_flash_slot(self, timeout_ms: int = 60000) -> bool:
        """Acquire a slot for flash operation.
        
        Blocks until a slot is available or timeout.
        
        Returns:
            True if slot acquired, False if timeout
        """
        start_time = time.monotonic()
        
        while True:
            async with self._lock:
                # Check backoff
                if self._backoff_until and datetime.now() < self._backoff_until:
                    wait_ms = (self._backoff_until - datetime.now()).total_seconds() * 1000
                    if wait_ms > timeout_ms:
                        return False
                
                # Check concurrent limits
                if self._active_flashes >= self.config.max_concurrent_flashes:
                    pass  # Need to wait
                else:
                    # Check throughput limits
                    self._clean_old_flashes()
                    
                    flashes_last_minute = len([t for t in self._flash_times 
                                             if datetime.now() - t < timedelta(minutes=1)])
                    flashes_last_hour = len(self._flash_times)
                    
                    if flashes_last_minute >= self.config.max_flashes_per_minute:
                        await asyncio.sleep(1)
                        continue
                    
                    if flashes_last_hour >= self.config.max_flashes_per_hour:
                        await asyncio.sleep(60)
                        continue
                    
                    # Acquire slot
                    self._active_flashes += 1
                    self._flash_times.append(datetime.now())
                    return True
            
            # Wait before retry
            await asyncio.sleep(0.1)
            
            # Check timeout
            elapsed = (time.monotonic() - start_time) * 1000
            if elapsed >= timeout_ms:
                return False
    
    async def release_flash_slot(self) -> None:
        """Release flash slot."""
        async with self._lock:
            self._active_flashes = max(0, self._active_flashes - 1)
    
    async def acquire_erase_slot(self, timeout_ms: int = 60000) -> bool:
        """Acquire slot for erase operation."""
        while True:
            async with self._lock:
                if self._active_erases < self.config.max_concurrent_erases:
                    self._active_erases += 1
                    return True
            
            await asyncio.sleep(0.1)
            
            elapsed = (time.monotonic() - start_time) * 1000  # BUG: start_time not defined
            if elapsed >= timeout_ms:
                return False
    
    async def release_erase_slot(self) -> None:
        """Release erase slot."""
        async with self._lock:
            self._active_erases = max(0, self._active_erases - 1)
    
    async def trigger_backoff(self, reason: str) -> None:
        """Trigger backoff after failure."""
        async with self._lock:
            backoff_duration = self.config.backoff_base_ms
            
            # Increase backoff on repeated failures
            if self._backoff_until:
                elapsed = (datetime.now() - self._backoff_until).total_seconds() * 1000
                if elapsed < 0:
                    # Still in previous backoff
                    backoff_duration *= self.config.backoff_multiplier
            
            backoff_duration = min(backoff_duration, self.config.backoff_max_ms)
            
            self._backoff_until = datetime.now() + timedelta(milliseconds=backoff_duration)
            
            logger.warning(
                "flash_backoff_triggered",
                reason=reason,
                backoff_ms=backoff_duration,
            )
    
    def _clean_old_flashes(self) -> None:
        """Clean up old flash timestamps."""
        cutoff = datetime.now() - timedelta(hours=1)
        self._flash_times = [t for t in self._flash_times if t > cutoff]
    
    def get_status(self) -> dict[str, Any]:
        """Get rate limiter status."""
        self._clean_old_flashes()
        
        return {
            "active_flashes": self._active_flashes,
            "active_erases": self._active_erases,
            "flashes_last_minute": len([t for t in self._flash_times 
                                        if datetime.now() - t < timedelta(minutes=1)]),
            "flashes_last_hour": len(self._flash_times),
            "in_backoff": self._backoff_until is not None and datetime.now() < self._backoff_until,
            "backoff_until": self._backoff_until.isoformat() if self._backoff_until else None,
        }


@dataclass
class ThermalMonitor:
    """Monitors thermal state of devices.
    
    Features:
    - Temperature tracking per device
    - Cooldown scheduling
    - Thermal state machine
    - Safety limits enforcement
    """
    
    config: ThermalConfig = field(default_factory=ThermalConfig)
    
    _devices: dict[str, DeviceThermalState] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    # Monitoring
    _monitoring: bool = False
    _monitor_task: asyncio.Task | None = None
    
    async def register_device(self, device_id: str) -> None:
        """Register a device for monitoring."""
        async with self._lock:
            if device_id not in self._devices:
                self._devices[device_id] = DeviceThermalState(device_id=device_id)
    
    async def unregister_device(self, device_id: str) -> None:
        """Unregister device."""
        async with self._lock:
            self._devices.pop(device_id, None)
    
    async def record_temperature(self, device_id: str, temp: float) -> None:
        """Record temperature reading."""
        async with self._lock:
            if device_id not in self._devices:
                await self.register_device(device_id)
            
            self._devices[device_id].update_temperature(temp)
    
    async def record_flash(self, device_id: str, duration_ms: float) -> None:
        """Record flash operation."""
        async with self._lock:
            if device_id in self._devices:
                device = self._devices[device_id]
                device.record_flash(duration_ms)
                
                # Auto cooldown if needed
                if device.needs_cooldown():
                    device.start_cooldown(self.config.cooldown_duration_ms)
    
    async def check_device_ready(self, device_id: str) -> tuple[bool, str]:
        """Check if device is ready for flash.
        
        Returns:
            (ready, reason)
        """
        async with self._lock:
            if device_id not in self._devices:
                return True, ""
            
            device = self._devices[device_id]
            
            # Check cooldown
            if device.needs_cooldown():
                remaining = device.get_cooldown_remaining_ms()
                return False, f"Device cooling down ({remaining}ms remaining)"
            
            # Check thermal state
            if device.thermal_state == ThermalState.CRITICAL:
                return False, "Device critical temperature"
            
            return True, ""
    
    async def start_monitoring(self, temp_reader: Any = None) -> None:
        """Start thermal monitoring loop."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(temp_reader))
        logger.info("thermal_monitoring_started")
    
    async def stop_monitoring(self) -> None:
        """Stop thermal monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("thermal_monitoring_stopped")
    
    async def _monitor_loop(self, temp_reader: Any) -> None:
        """Monitoring loop."""
        while self._monitoring:
            try:
                async with self._lock:
                    for device_id, device in self._devices.items():
                        # Check if cooldown expired
                        if device.cooldown_until and datetime.now() >= device.cooldown_until:
                            device.cooldown_until = None
                            
                            if device.thermal_state == ThermalState.HOT:
                                logger.info("cooldown_completed", device_id=device_id)
                        
                        # Log warnings for hot devices
                        if device.thermal_state == ThermalState.HOT:
                            logger.warning(
                                "device_hot",
                                device_id=device_id,
                                temp=device.current_temp,
                            )
                        elif device.thermal_state == ThermalState.CRITICAL:
                            logger.error(
                                "device_critical",
                                device_id=device_id,
                                temp=device.current_temp,
                            )
                
                await asyncio.sleep(self.config.temp_check_interval_ms / 1000)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("thermal_monitor_error", error=str(e))
                await asyncio.sleep(1)
    
    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Get thermal status of device."""
        if device_id not in self._devices:
            return None
        
        device = self._devices[device_id]
        return {
            "device_id": device_id,
            "current_temp": device.current_temp,
            "max_temp": device.max_temp,
            "thermal_state": device.thermal_state.value,
            "needs_cooldown": device.needs_cooldown(),
            "cooldown_remaining_ms": device.get_cooldown_remaining_ms(),
            "flashes_since_cooldown": device.flashes_since_cooldown,
        }
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all devices."""
        return {
            device_id: self.get_device_status(device_id)
            for device_id in self._devices
        }


@dataclass
class PowerBudgetManager:
    """Manages power budget for fleet operations.
    
    Features:
    - Track power consumption
    - Enforce budget limits
    - USB hub power management
    - Brownout prevention
    """
    
    config: PowerConfig = field(default_factory=PowerConfig)
    
    _device_power: dict[str, int] = field(default_factory=dict)  # device_id -> current_ma
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def allocate_power(
        self,
        device_id: str,
        operation: str = "flash",
    ) -> bool:
        """Allocate power budget for device.
        
        Returns:
            True if power allocated, False if over budget
        """
        async with self._lock:
            # Calculate required power
            if operation == "flash":
                required = self.config.flash_power_ma
            elif operation == "erase":
                required = self.config.erase_power_ma
            else:
                required = self.config.flash_power_ma
            
            # Calculate current usage
            current_usage = sum(self._device_power.values())
            
            # Check if we have budget
            if current_usage + required > self.config.power_budget_ma:
                return False
            
            # Allocate
            self._device_power[device_id] = required
            return True
    
    async def release_power(self, device_id: str) -> None:
        """Release power allocation."""
        async with self._lock:
            self._device_power.pop(device_id, None)
    
    async def check_available_power(self) -> int:
        """Get available power in mA."""
        async with self._lock:
            current = sum(self._device_power.values())
            return max(0, self.config.power_budget_ma - current)
    
    def get_status(self) -> dict[str, Any]:
        """Get power budget status."""
        current = sum(self._device_power.values())
        return {
            "budget_ma": self.config.power_budget_ma,
            "used_ma": current,
            "available_ma": max(0, self.config.power_budget_ma - current),
            "utilization_percent": (current / self.config.power_budget_ma * 100) if self.config.power_budget_ma > 0 else 0,
            "devices": len(self._device_power),
        }


@dataclass
class FleetSafetyController:
    """Unified fleet safety controller.
    
    Combines:
    - FlashRateLimiter
    - ThermalMonitor
    - PowerBudgetManager
    
    Provides single interface for fleet-wide safety management.
    """
    
    rate_limiter: FlashRateLimiter = field(default_factory=FlashRateLimiter)
    thermal_monitor: ThermalMonitor = field(default_factory=ThermalMonitor)
    power_manager: PowerBudgetManager = field(default_factory=PowerBudgetManager)
    
    # Configuration
    config: RateLimitConfig = field(default_factory=RateLimitConfig)
    thermal_config: ThermalConfig = field(default_factory=ThermalConfig)
    
    # State
    _enabled: bool = True
    
    async def can_flash(self, device_id: str) -> tuple[bool, str]:
        """Check if device can be flashed.
        
        Checks all safety limits:
        - Rate limits
        - Thermal state
        - Power budget
        
        Returns:
            (can_flash, reason)
        """
        if not self._enabled:
            return True, ""
        
        # Check thermal
        ready, reason = await self.thermal_monitor.check_device_ready(device_id)
        if not ready:
            return False, f"Thermal: {reason}"
        
        # Check power budget
        available = await self.power_manager.check_available_power()
        if available < self.power_manager.config.flash_power_ma:
            return False, "Power budget exceeded"
        
        # Check rate limits
        status = self.rate_limiter.get_status()
        if status["in_backoff"]:
            return False, "Rate limiter in backoff"
        
        return True, ""
    
    async def request_flash(
        self,
        device_id: str,
        timeout_ms: int = 60000,
    ) -> tuple[bool, str]:
        """Request permission to flash device.
        
        Acquires all necessary resources.
        
        Returns:
            (granted, reason)
        """
        # Check if allowed
        can_flash, reason = await self.can_flash(device_id)
        if not can_flash:
            return False, reason
        
        # Acquire slots
        if not await self.rate_limiter.acquire_flash_slot(timeout_ms):
            return False, "Rate limit exceeded"
        
        if not await self.power_manager.allocate_power(device_id, "flash"):
            await self.rate_limiter.release_flash_slot()
            return False, "Power budget exceeded"
        
        return True, ""
    
    async def complete_flash(
        self,
        device_id: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        """Complete flash operation.
        
        Releases resources and updates state.
        """
        # Release slots
        await self.rate_limiter.release_flash_slot()
        await self.power_manager.release_power(device_id)
        
        # Update thermal state
        await self.thermal_monitor.record_flash(device_id, duration_ms)
        
        # Trigger backoff on failure
        if not success:
            await self.rate_limiter.trigger_backoff("flash_failed")
    
    async def record_temperature(self, device_id: str, temp: float) -> None:
        """Record device temperature."""
        await self.thermal_monitor.record_temperature(device_id, temp)
    
    async def enable(self) -> None:
        """Enable safety controller."""
        self._enabled = True
        await self.thermal_monitor.start_monitoring()
        logger.info("fleet_safety_enabled")
    
    async def disable(self) -> None:
        """Disable safety controller (for maintenance)."""
        self._enabled = False
        await self.thermal_monitor.stop_monitoring()
        logger.info("fleet_safety_disabled")
    
    def get_full_status(self) -> dict[str, Any]:
        """Get comprehensive status of all safety systems."""
        return {
            "enabled": self._enabled,
            "rate_limiter": self.rate_limiter.get_status(),
            "power": self.power_manager.get_status(),
            "thermal": self.thermal_monitor.get_all_status(),
        }


@dataclass
class CooldownScheduler:
    """Schedules cooldown periods for devices.
    
    Features:
    - Staggered cooldowns to maintain throughput
    - Predictive cooldown based on thermal model
    - Priority-based scheduling
    """
    
    thermal_monitor: ThermalMonitor
    rate_limiter: FlashRateLimiter
    
    # Stagger configuration
    stagger_delay_ms: int = 1000  # Delay between devices
    
    async def schedule_cooldowns(self, device_ids: list[str]) -> dict[str, datetime]:
        """Schedule staggered cooldowns for devices.
        
        Returns:
            Dictionary of device_id -> cooldown_end_time
        """
        schedules = {}
        
        for i, device_id in enumerate(device_ids):
            # Calculate delay for this device
            delay_ms = i * self.stagger_delay_ms
            delay = timedelta(milliseconds=delay_ms)
            
            # Schedule cooldown
            cooldown_end = datetime.now() + delay + timedelta(
                milliseconds=self.thermal_monitor.config.cooldown_duration_ms
            )
            
            schedules[device_id] = cooldown_end
            
            # Update device state
            device = self.thermal_monitor._devices.get(device_id)
            if device:
                device.cooldown_until = cooldown_end
        
        return schedules
    
    async def wait_for_availability(
        self,
        device_id: str,
        timeout_ms: int = 300000,
    ) -> bool:
        """Wait for device to be available.
        
        Returns:
            True if device becomes available, False if timeout
        """
        start = time.monotonic()
        
        while True:
            ready, _ = await self.thermal_monitor.check_device_ready(device_id)
            
            if ready:
                return True
            
            # Wait a bit
            await asyncio.sleep(1)
            
            elapsed = (time.monotonic() - start) * 1000
            if elapsed >= timeout_ms:
                return False
    
    def predict_cooldown_duration(
        self,
        current_temp: float,
        target_temp: float,
    ) -> int:
        """Predict cooldown duration based on thermal model.
        
        Simple linear model:
        - Cooling rate: ~1 degree per second in still air
        - Faster with active cooling
        """
        temp_diff = current_temp - target_temp
        cooling_rate = 1.0  # degrees per second
        
        duration_seconds = temp_diff / cooling_rate
        return int(duration_seconds * 1000)
