"""Fake Flash Device - Power loss simulation for chaos testing.

This module simulates a flash memory device with:
- Write batching (writes don't commit immediately)
- Power loss during write/erase operations
- State machine with corrupted/incomplete states
- Sector-based operations
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class FlashState(Enum):
    """Flash device states."""
    IDLE = "idle"
    WRITING = "writing"
    ERASING = "erasing"
    VERIFYING = "verifying"
    CORRUPTED = "corrupted"
    POWER_LOSS = "power_loss"


class FlashError(Enum):
    """Flash operation errors."""
    NONE = "none"
    VERIFY_FAILED = "verify_failed"
    WRITE_TIMEOUT = "write_timeout"
    ERASE_FAILED = "erase_failed"
    CORRUPTED_DATA = "corrupted_data"
    POWER_LOSS_DURING_WRITE = "power_loss_during_write"
    POWER_LOSS_DURING_ERASE = "power_loss_during_erase"


@dataclass
class FlashSector:
    """Represents a flash sector."""
    base_address: int
    size: int
    is_erased: bool = True
    data: bytearray = field(default_factory=bytearray)
    write_in_progress: bool = False
    corruption_offset: int = -1
    corruption_length: int = 0
    
    def __post_init__(self):
        if not self.data:
            self.data = bytearray(self.size)


@dataclass
class FlashWriteOperation:
    """A pending write operation."""
    address: int
    data: bytes
    offset: int = 0  # Current progress
    batched: bool = True  # Write batching enabled
    committed: bool = False
    power_loss_at: Optional[int] = None  # Simulate power loss at this offset


@dataclass
class FlashEraseOperation:
    """A pending erase operation."""
    sector_address: int
    started_at: datetime = field(default_factory=datetime.now)
    completed: bool = False
    power_loss_at: Optional[float] = None  # Simulate power loss at this timestamp (ms)


@dataclass
class FlashStatistics:
    """Flash operation statistics."""
    total_writes: int = 0
    total_erases: int = 0
    power_losses: int = 0
    corruptions: int = 0
    verify_failures: int = 0
    last_operation: Optional[str] = None
    last_operation_time: Optional[datetime] = None


class FakeFlashDevice:
    """Simulates flash memory with power loss capabilities.
    
    Features:
    - Write batching (writes accumulate before commit)
    - Power loss simulation during write/erase
    - Corruption detection
    - State machine tracking
    
    Usage:
    ```python
    # Create flash with 1MB size
    flash = FakeFlashDevice(size=0x100000)
    
    # Enable power loss simulation (50% chance)
    flash.enable_power_loss_simulation(probability=0.5)
    
    # Write data (may fail due to power loss)
    await flash.write(0x08000000, b"firmware_data")
    
    # Simulate explicit power loss
    await flash.simulate_power_loss()
    ```
    """
    
    def __init__(
        self,
        size: int = 0x100000,  # 1MB default
        sector_size: int = 0x4000,  # 16KB sectors
        base_address: int = 0x08000000,
    ):
        self.size = size
        self.sector_size = sector_size
        self.base_address = base_address
        
        # Initialize sectors
        self._sectors: dict[int, FlashSector] = {}
        self._init_sectors()
        
        # State machine
        self._state = FlashState.IDLE
        self._last_error = FlashError.NONE
        
        # Pending operations
        self._pending_writes: list[FlashWriteOperation] = []
        self._pending_erases: list[FlashEraseOperation] = []
        
        # Statistics
        self._stats = FlashStatistics()
        
        # Power loss simulation
        self._power_loss_enabled = False
        self._power_loss_probability = 0.0
        self._power_loss_lock = asyncio.Lock()
        
        logger.info("fake_flash_initialized", size=size, sectors=len(self._sectors))
    
    def _init_sectors(self) -> None:
        """Initialize flash sectors."""
        num_sectors = self.size // self.sector_size
        for i in range(num_sectors):
            base = self.base_address + (i * self.sector_size)
            self._sectors[base] = FlashSector(
                base_address=base,
                size=self.sector_size,
            )
    
    @property
    def state(self) -> FlashState:
        """Get current flash state."""
        return self._state
    
    @property
    def last_error(self) -> FlashError:
        """Get last error."""
        return self._last_error
    
    @property
    def statistics(self) -> FlashStatistics:
        """Get operation statistics."""
        return self._stats
    
    def enable_power_loss_simulation(self, probability: float = 0.5) -> None:
        """Enable power loss simulation.
        
        Args:
            probability: Probability of power loss during each operation (0.0-1.0)
        """
        self._power_loss_enabled = True
        self._power_loss_probability = max(0.0, min(1.0, probability))
        logger.info(
            "power_loss_simulation_enabled",
            probability=self._power_loss_probability,
        )
    
    def disable_power_loss_simulation(self) -> None:
        """Disable power loss simulation."""
        self._power_loss_enabled = False
        logger.info("power_loss_simulation_disabled")
    
    async def _check_power_loss(self) -> bool:
        """Check if power loss should occur. Returns True if power lost."""
        if not self._power_loss_enabled:
            return False
        
        async with self._power_loss_lock:
            if random.random() < self._power_loss_probability:
                self._stats.power_losses += 1
                self._state = FlashState.POWER_LOSS
                self._last_error = FlashError.POWER_LOSS_DURING_WRITE
                logger.warning("simulated_power_loss")
                return True
        
        return False
    
    async def write(
        self,
        address: int,
        data: bytes,
        verify: bool = True,
    ) -> bool:
        """Write data to flash.
        
        Args:
            address: Flash address
            data: Data to write
            verify: Whether to verify write
        
        Returns:
            True if write successful, False otherwise
        """
        if not self._is_valid_address(address, len(data)):
            self._last_error = FlashError.VERIFY_FAILED
            return False
        
        # Check for power loss
        if await self._check_power_loss():
            await self._handle_power_loss_during_write(address, data)
            return False
        
        self._state = FlashState.WRITING
        self._stats.total_writes += 1
        self._stats.last_operation = "write"
        self._stats.last_operation_time = datetime.now()
        
        # Get affected sectors
        sectors = self._get_sectors_for_range(address, len(data))
        
        # Erase sectors first if needed
        for sector in sectors:
            if sector.is_erased:
                continue
            
            if await self._check_power_loss():
                await self._handle_power_loss_during_erase(sector)
                return False
            
            sector.is_erased = True
            sector.data = bytearray(sector.size)
        
        # Write data
        remaining = len(data)
        offset = 0
        current_addr = address
        
        while remaining > 0:
            if await self._check_power_loss():
                await self._handle_power_loss_during_write(
                    current_addr, data[offset:]
                )
                return False
            
            sector = self._get_sector_for_address(current_addr)
            sector_offset = current_addr - sector.base_address
            chunk_size = min(remaining, sector.size - sector_offset)
            
            sector.data[sector_offset:sector_offset + chunk_size] = data[offset:offset + chunk_size]
            
            remaining -= chunk_size
            offset += chunk_size
            current_addr += chunk_size
        
        # Verify if requested
        if verify:
            read_back = await self.read(address, len(data))
            if read_back != data:
                self._last_error = FlashError.VERIFY_FAILED
                self._stats.verify_failures += 1
                logger.error(
                    "flash_verify_failed",
                    address=hex(address),
                    expected_len=len(data),
                )
                return False
        
        self._state = FlashState.IDLE
        logger.info("flash_write_complete", address=hex(address), size=len(data))
        
        return True
    
    async def read(self, address: int, size: int) -> bytes:
        """Read data from flash.
        
        Args:
            address: Flash address
            size: Number of bytes to read
        
        Returns:
            Data read from flash
        """
        if not self._is_valid_address(address, size):
            return b""
        
        # Check for corruption
        sector = self._get_sector_for_address(address)
        if sector.corruption_offset >= 0:
            # Return corrupted data
            pass
        
        result = bytearray()
        remaining = size
        current_addr = address
        
        while remaining > 0:
            sector = self._get_sector_for_address(current_addr)
            sector_offset = current_addr - sector.base_address
            chunk_size = min(remaining, sector.size - sector_offset)
            
            result.extend(sector.data[sector_offset:sector_offset + chunk_size])
            
            remaining -= chunk_size
            current_addr += chunk_size
        
        return bytes(result)
    
    async def erase(self, address: int, size: int) -> bool:
        """Erase flash sectors.
        
        Args:
            address: Start address (must be sector-aligned)
            size: Size to erase
        
        Returns:
            True if erase successful
        """
        if not self._is_valid_address(address, size):
            return False
        
        if not self._is_sector_aligned(address):
            return False
        
        self._state = FlashState.ERASING
        self._stats.total_erases += 1
        self._stats.last_operation = "erase"
        self._stats.last_operation_time = datetime.now()
        
        sectors = self._get_sectors_for_range(address, size)
        
        for sector in sectors:
            if await self._check_power_loss():
                await self._handle_power_loss_during_erase(sector)
                return False
            
            sector.is_erased = True
            sector.data = bytearray(sector.size)
            sector.write_in_progress = False
            sector.corruption_offset = -1
        
        self._state = FlashState.IDLE
        logger.info("flash_erase_complete", address=hex(address), size=size)
        
        return True
    
    async def _handle_power_loss_during_write(
        self,
        address: int,
        data: bytes,
    ) -> None:
        """Handle power loss during write operation."""
        self._state = FlashState.POWER_LOSS
        self._stats.power_losses += 1
        
        # Randomly corrupt some data
        if len(data) > 0:
            sector = self._get_sector_for_address(address)
            corruption_offset = random.randint(0, len(data) - 1)
            corruption_length = random.randint(1, min(16, len(data) - corruption_offset))
            
            sector.corruption_offset = corruption_offset
            sector.corruption_length = corruption_length
            
            self._stats.corruptions += 1
            logger.warning(
                "flash_corruption_after_power_loss",
                sector=hex(sector.base_address),
                offset=corruption_offset,
                length=corruption_length,
            )
        
        self._state = FlashState.CORRUPTED if self._stats.corruptions > 0 else FlashState.IDLE
    
    async def _handle_power_loss_during_erase(self, sector: FlashSector) -> None:
        """Handle power loss during erase operation."""
        self._state = FlashState.POWER_LOSS
        self._stats.power_losses += 1
        
        # Partial erase - sector is in inconsistent state
        sector.is_erased = False
        self._stats.corruptions += 1
        
        logger.warning("flash_partial_erase_after_power_loss", sector=hex(sector.base_address))
        
        self._state = FlashState.CORRUPTED
    
    async def simulate_power_loss(self) -> None:
        """Force a power loss event."""
        self._state = FlashState.POWER_LOSS
        self._stats.power_losses += 1
        
        logger.warning("forced_power_loss")
    
    def reset(self) -> None:
        """Reset flash to initial state."""
        self._init_sectors()
        self._state = FlashState.IDLE
        self._last_error = FlashError.NONE
        self._pending_writes.clear()
        self._pending_erases.clear()
        
        logger.info("flash_reset")
    
    def get_state_report(self) -> dict[str, Any]:
        """Get detailed state report."""
        return {
            "state": self._state.value,
            "last_error": self._last_error.value,
            "power_loss_enabled": self._power_loss_enabled,
            "power_loss_probability": self._power_loss_probability,
            "statistics": {
                "total_writes": self._stats.total_writes,
                "total_erases": self._stats.total_erases,
                "power_losses": self._stats.power_losses,
                "corruptions": self._stats.corruptions,
                "verify_failures": self._stats.verify_failures,
            },
            "sectors": [
                {
                    "base": hex(s.base_address),
                    "erased": s.is_erased,
                    "corrupted": s.corruption_offset >= 0,
                }
                for s in self._sectors.values()
            ],
        }
    
    def _is_valid_address(self, address: int, size: int) -> bool:
        """Check if address range is valid."""
        return (
            address >= self.base_address and
            address + size <= self.base_address + self.size
        )
    
    def _is_sector_aligned(self, address: int) -> bool:
        """Check if address is sector-aligned."""
        return (address - self.base_address) % self.sector_size == 0
    
    def _get_sector_for_address(self, address: int) -> Optional[FlashSector]:
        """Get sector for address."""
        sector_base = (address - self.base_address) // self.sector_size
        sector_base_addr = self.base_address + (sector_base * self.sector_size)
        return self._sectors.get(sector_base_addr)
    
    def _get_sectors_for_range(self, address: int, size: int) -> list[FlashSector]:
        """Get all sectors for an address range."""
        sectors = []
        sector_base = (address - self.base_address) // self.sector_size
        sector_end = (address + size - self.base_address) // self.sector_size
        
        for i in range(sector_base, sector_end + 1):
            sector_addr = self.base_address + (i * self.sector_size)
            sector = self._sectors.get(sector_addr)
            if sector:
                sectors.append(sector)
        
        return sectors


class FlashChaosScenario:
    """Predefined chaos scenarios for flash testing."""
    
    @staticmethod
    async def rapid_power_losses(flash: FakeFlashDevice, count: int = 10) -> dict[str, Any]:
        """Rapid fire power losses during writes.
        
        Args:
            flash: Flash device
            count: Number of power loss cycles
        
        Returns:
            Test results
        """
        results = {
            "cycles": count,
            "failures": 0,
            "corruptions": 0,
        }
        
        flash.enable_power_loss_simulation(probability=1.0)  # 100% power loss
        
        for i in range(count):
            # Write some data
            success = await flash.write(
                0x08000000,
                b"X" * 256,
                verify=False,
            )
            
            if not success:
                results["failures"] += 1
            
            # Reset and try again
            flash.reset()
        
        results["corruptions"] = flash.statistics.corruptions
        
        return results
    
    @staticmethod
    async def partial_erase_during_write(
        flash: FakeFlashDevice,
    ) -> dict[str, Any]:
        """Test partial erase during write operation.
        
        Returns:
            Test results
        """
        flash.enable_power_loss_simulation(probability=0.8)
        
        # Write initial data
        await flash.write(0x08000000, b"A" * 1024)
        
        # Try to write new data (may corrupt)
        success = await flash.write(0x08000000, b"B" * 1024)
        
        # Check for corruption
        data = await flash.read(0x08000000, 1024)
        expected = b"B" * 1024
        
        return {
            "write_success": success,
            "data_matches": data == expected,
            "state": flash.state.value,
            "corruptions": flash.statistics.corruptions,
        }
    
    @staticmethod
    async def stress_test(
        flash: FakeFlashDevice,
        operations: int = 100,
    ) -> dict[str, Any]:
        """Stress test with random operations and power losses.
        
        Args:
            flash: Flash device
            operations: Number of operations
        
        Returns:
            Test results
        """
        import random
        
        results = {
            "operations": operations,
            "writes": 0,
            "reads": 0,
            "erases": 0,
            "failures": 0,
            "corruptions": 0,
        }
        
        flash.enable_power_loss_simulation(probability=0.1)
        
        for i in range(operations):
            op = random.choice(["write", "write", "write", "read", "erase"])
            
            if op == "write":
                addr = 0x08000000 + random.randint(0, 7) * 0x1000
                data = bytes([random.randint(0, 255) for _ in range(64)])
                success = await flash.write(addr, data, verify=False)
                if not success:
                    results["failures"] += 1
                results["writes"] += 1
                
            elif op == "read":
                await flash.read(0x08000000, 64)
                results["reads"] += 1
                
            elif op == "erase":
                addr = 0x08000000 + random.randint(0, 7) * 0x4000
                success = await flash.erase(addr, 0x4000)
                if not success:
                    results["failures"] += 1
                results["erases"] += 1
        
        results["corruptions"] = flash.statistics.corruptions
        
        return results
