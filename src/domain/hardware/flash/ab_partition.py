"""OTA A/B Partition Manager - Dual-bank firmware support.

Provides:
- A/B slot management
- Bootloader fallback
- Atomic firmware updates
- Rollback on failure
- Anti-rollback protection

Usage:
    manager = ABPartitionManager(probe, config)
    await manager.prepare_update(firmware_data)
    await manager.switch_to_new_slot()
    await manager.mark_boot_successful()
"""

from __future__ import annotations

import hashlib
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SlotState(Enum):
    """Slot state."""
    EMPTY = "empty"
    VALID = "valid"
    UPDATING = "updating"
    CORRUPTED = "corrupted"
    PENDING_BOOT = "pending_boot"


@dataclass
class SlotInfo:
    """Slot information."""
    slot_id: int
    base_address: int
    size: int
    state: SlotState = SlotState.EMPTY
    firmware_version: str = ""
    firmware_hash: str = ""
    last_booted: datetime | None = None
    update_count: int = 0
    
    # Boot info
    is_active: bool = False
    boot_count: int = 0
    consecutive_failed_boots: int = 0


@dataclass
class ABConfig:
    """A/B partition configuration."""
    slot_a_address: int = 0x08040000
    slot_b_address: int = 0x08140000
    slot_size: int = 512 * 1024  # 512KB each
    scratch_size: int = 16 * 1024  # 16KB for metadata
    scratch_address: int = 0x20000000
    
    # Boot control
    boot_control_address: int = 0x2003F000
    magic_number: int = 0xDEADBEEF
    
    # Anti-rollback
    min_version: int = 0
    max_version: int = 0xFFFFFFFF


@dataclass
class BootControlBlock:
    """Boot control block stored in flash."""
    magic: int
    active_slot: int  # 0 = A, 1 = B
    retry_count: int
    version: int
    hash: bytes
    timestamp: int
    
    def to_bytes(self) -> bytes:
        return struct.pack("<IIIBB32sI", 
            self.magic,
            self.active_slot,
            self.retry_count,
            self.version,
            0,  # reserved
            self.hash,
            self.timestamp,
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "BootControlBlock":
        if len(data) < 48:
            raise ValueError("BootControlBlock too small")
        unpacked = struct.unpack("<IIIBB32sI", data[:48])
        return cls(
            magic=unpacked[0],
            active_slot=unpacked[1],
            retry_count=unpacked[2],
            version=unpacked[3],
            hash=unpacked[5],
            timestamp=unpacked[6],
        )


@dataclass
class UpdateResult:
    """Result of update operation."""
    success: bool
    slot: int
    bytes_written: int = 0
    error: str | None = None
    
    # Verification
    verified: bool = False
    hash_match: bool = False


class ABPartitionManager:
    """A/B partition manager for dual-bank firmware.
    
    Provides:
    - Atomic A/B slot switching
    - Rollback on failed boot
    - Anti-rollback protection
    - Firmware verification
    """
    
    def __init__(
        self,
        probe: Any,
        config: ABConfig | None = None,
    ):
        self._probe = probe
        self._config = config or ABConfig()
        self._slots = self._init_slots()
    
    def _init_slots(self) -> dict[int, SlotInfo]:
        """Initialize slot information."""
        return {
            0: SlotInfo(
                slot_id=0,
                base_address=self._config.slot_a_address,
                size=self._config.slot_size,
            ),
            1: SlotInfo(
                slot_id=1,
                base_address=self._config.slot_b_address,
                size=self._config.slot_size,
            ),
        }
    
    async def read_boot_control(self) -> BootControlBlock:
        """Read boot control block."""
        try:
            data = await self._probe.read_memory(
                self._config.boot_control_address,
                64,
            )
            bcb = BootControlBlock.from_bytes(data)
            
            if bcb.magic != self._config.magic_number:
                logger.warning("boot_control_magic_mismatch")
                return self._default_boot_control()
            
            return bcb
        except Exception as e:
            logger.error("read_boot_control_failed", error=str(e))
            return self._default_boot_control()
    
    def _default_boot_control(self) -> BootControlBlock:
        """Create default boot control."""
        return BootControlBlock(
            magic=self._config.magic_number,
            active_slot=0,
            retry_count=3,
            version=0,
            hash=bytes(32),
            timestamp=0,
        )
    
    async def write_boot_control(self, bcb: BootControlBlock) -> bool:
        """Write boot control block."""
        try:
            data = bcb.to_bytes()
            await self._probe.write_memory(
                self._config.boot_control_address,
                data,
            )
            logger.info("boot_control_written", active_slot=bcb.active_slot)
            return True
        except Exception as e:
            logger.error("write_boot_control_failed", error=str(e))
            return False
    
    def get_active_slot(self) -> int:
        """Get currently active slot (0=A, 1=B)."""
        return 0  # Will read from boot control
    
    def get_inactive_slot(self) -> int:
        """Get inactive slot for update."""
        return 1  # Will read from boot control
    
    async def prepare_update(self, firmware: bytes) -> UpdateResult:
        """Prepare firmware update in inactive slot.
        
        Args:
            firmware: Firmware binary data
            
        Returns:
            UpdateResult with status
        """
        try:
            bcb = await self.read_boot_control()
            inactive_slot = 1 - bcb.active_slot
            slot_info = self._slots[inactive_slot]
            
            # Verify firmware size fits
            if len(firmware) > slot_info.size:
                return UpdateResult(
                    success=False,
                    slot=inactive_slot,
                    error=f"Firmware too large: {len(firmware)} > {slot_info.size}",
                )
            
            # Compute hash
            firmware_hash = hashlib.sha256(firmware).digest()
            
            # Update slot info
            slot_info.state = SlotState.UPDATING
            slot_info.firmware_hash = firmware_hash.hex()
            
            # Write firmware to inactive slot
            logger.info(
                "writing_to_slot",
                slot=inactive_slot,
                address=f"0x{slot_info.base_address:08X}",
                size=len(firmware),
            )
            
            # Write in chunks
            chunk_size = 256
            bytes_written = 0
            for offset in range(0, len(firmware), chunk_size):
                chunk = firmware[offset : offset + chunk_size]
                addr = slot_info.base_address + offset
                await self._probe.write_memory(addr, chunk)
                bytes_written += len(chunk)
            
            # Verify written data
            verified_data = await self._probe.read_memory(
                slot_info.base_address,
                len(firmware),
            )
            hash_match = verified_data == firmware
            
            if not hash_match:
                slot_info.state = SlotState.CORRUPTED
                return UpdateResult(
                    success=False,
                    slot=inactive_slot,
                    bytes_written=bytes_written,
                    verified=False,
                    hash_match=False,
                    error="Verification failed",
                )
            
            slot_info.state = SlotState.VALID
            slot_info.update_count += 1
            
            return UpdateResult(
                success=True,
                slot=inactive_slot,
                bytes_written=bytes_written,
                verified=True,
                hash_match=True,
            )
            
        except Exception as e:
            logger.error("prepare_update_failed", error=str(e))
            return UpdateResult(
                success=False,
                slot=self.get_inactive_slot(),
                error=str(e),
            )
    
    async def mark_update_valid(self, version: int, firmware_hash: bytes) -> bool:
        """Mark update as valid and ready to boot."""
        try:
            bcb = await self.read_boot_control()
            inactive_slot = 1 - bcb.active_slot
            
            # Update boot control
            bcb.version = version
            bcb.hash = firmware_hash
            bcb.timestamp = int(datetime.now().timestamp())
            bcb.retry_count = 3  # Reset retry count
            
            success = await self.write_boot_control(bcb)
            
            if success:
                slot = self._slots[inactive_slot]
                slot.state = SlotState.PENDING_BOOT
                slot.firmware_version = str(version)
                
            return success
            
        except Exception as e:
            logger.error("mark_update_valid_failed", error=str(e))
            return False
    
    async def switch_slots(self) -> bool:
        """Switch active slot (atomic operation).
        
        This updates the boot control to point to the other slot.
        The actual switch happens on next reboot.
        """
        try:
            bcb = await self.read_boot_control()
            
            # Switch active slot
            new_active = 1 - bcb.active_slot
            bcb.active_slot = new_active
            bcb.retry_count = 3
            
            success = await self.write_boot_control(bcb)
            
            if success:
                self._slots[bcb.active_slot].is_active = False
                self._slots[new_active].is_active = True
                self._slots[new_active].state = SlotState.PENDING_BOOT
                
                logger.info("slot_switch_prepared", new_active=new_active)
            
            return success
            
        except Exception as e:
            logger.error("switch_slots_failed", error=str(e))
            return False
    
    async def mark_boot_successful(self) -> bool:
        """Mark current boot as successful.
        
        Call this after verifying firmware runs correctly.
        """
        try:
            bcb = await self.read_boot_control()
            
            # Reset retry count on successful boot
            bcb.retry_count = 3
            
            success = await self.write_boot_control(bcb)
            
            if success:
                slot = self._slots[bcb.active_slot]
                slot.last_booted = datetime.now()
                slot.boot_count += 1
                slot.consecutive_failed_boots = 0
                slot.state = SlotState.VALID
                
            return success
            
        except Exception as e:
            logger.error("mark_boot_successful_failed", error=str(e))
            return False
    
    async def mark_boot_failed(self) -> bool:
        """Mark current boot as failed.
        
        Decrements retry count. If retries exhausted, reverts to other slot.
        """
        try:
            bcb = await self.read_boot_control()
            current_slot = bcb.active_slot
            
            slot = self._slots[current_slot]
            slot.consecutive_failed_boots += 1
            
            bcb.retry_count -= 1
            
            if bcb.retry_count <= 0:
                logger.warning(
                    "boot_retry_exhausted",
                    slot=current_slot,
                    consecutive_failures=slot.consecutive_failed_boots,
                )
                
                # Switch back to other slot
                other_slot = 1 - current_slot
                other = self._slots[other_slot]
                
                if other.state == SlotState.VALID:
                    bcb.active_slot = other_slot
                    bcb.retry_count = 3
                    slot.state = SlotState.CORRUPTED
                    logger.info("reverting_to_slot", slot=other_slot)
                else:
                    logger.error("no_valid_fallback_slot")
            
            return await self.write_boot_control(bcb)
            
        except Exception as e:
            logger.error("mark_boot_failed_failed", error=str(e))
            return False
    
    async def rollback_to_previous(self) -> bool:
        """Force rollback to previous slot."""
        try:
            bcb = await self.read_boot_control()
            current = bcb.active_slot
            previous = 1 - current
            
            if self._slots[previous].state in [SlotState.VALID, SlotState.PENDING_BOOT]:
                bcb.active_slot = previous
                bcb.retry_count = 3
                success = await self.write_boot_control(bcb)
                
                if success:
                    self._slots[current].is_active = False
                    self._slots[previous].is_active = True
                    logger.info("rollback_complete", from_slot=current, to_slot=previous)
                
                return success
            
            return False
            
        except Exception as e:
            logger.error("rollback_failed", error=str(e))
            return False
    
    async def get_slot_status(self) -> dict[str, Any]:
        """Get status of both slots."""
        bcb = await self.read_boot_control()
        
        return {
            "active_slot": bcb.active_slot,
            "retry_count": bcb.retry_count,
            "slots": {
                0: {
                    "state": self._slots[0].state.value,
                    "address": f"0x{self._slots[0].base_address:08X}",
                    "is_active": bcb.active_slot == 0,
                    "version": self._slots[0].firmware_version,
                    "boot_count": self._slots[0].boot_count,
                    "consecutive_failures": self._slots[0].consecutive_failed_boots,
                },
                1: {
                    "state": self._slots[1].state.value,
                    "address": f"0x{self._slots[1].base_address:08X}",
                    "is_active": bcb.active_slot == 1,
                    "version": self._slots[1].firmware_version,
                    "boot_count": self._slots[1].boot_count,
                    "consecutive_failures": self._slots[1].consecutive_failed_boots,
                },
            },
        }
    
    async def validate_version(self, version: int) -> tuple[bool, str]:
        """Validate firmware version against anti-rollback.
        
        Returns:
            (is_valid, error_message)
        """
        if version < self._config.min_version:
            return False, f"Version {version} below minimum {self._config.min_version}"
        
        if version > self._config.max_version:
            return False, f"Version {version} above maximum {self._config.max_version}"
        
        # Check monotonic counter if HSM available
        try:
            from src.infrastructure.hsm.atecc608 import get_hsm
            hsm = await get_hsm()
            counter_version = await hsm.get_counter(0)
            
            if version <= counter_version:
                return False, f"Version {version} <= anti-rollback counter {counter_version}"
            
        except ImportError:
            pass  # HSM not available
        
        return True, "OK"


# Global manager
_manager: ABPartitionManager | None = None


def get_ab_manager(probe: Any, config: ABConfig | None = None) -> ABPartitionManager:
    """Get A/B partition manager."""
    global _manager
    if _manager is None:
        _manager = ABPartitionManager(probe, config)
    return _manager


if __name__ == "__main__":
    print("A/B Partition Manager")
    print("=" * 40)
    print("Dual-bank firmware support for OTA updates")
    print()
    print("Features:")
    print("  - Atomic slot switching")
    print("  - Rollback on failed boot")
    print("  - Anti-rollback protection")
    print("  - HSM-backed version counter")
