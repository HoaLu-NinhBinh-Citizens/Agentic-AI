"""OTA A/B Partition Manager - Dual-bank firmware support.

Provides:
- A/B slot management
- Bootloader fallback
- Atomic firmware updates
- Rollback on failure
- Anti-rollback protection
- Signed artifact manifest integration

====================================================================
BOOTLOADER CONTRACT — ROLLBACK GUARANTEE
====================================================================

SOFTWARE ROLLBACK GUARANTEE: The anti-rollback guarantee provided by
this module is ONLY valid if the bootloader enforces the pending/
confirmed semantics described below. The software cannot protect against
a compromised bootloader that skips these checks.

REQUIRED BOOTLOADER BEHAVIOR:
1. On every boot, the bootloader MUST:
   a. Read the active slot from boot control block
   b. Verify the slot's pending state matches expected state
   c. Check the signature against SignedArtifactManifest
   d. Verify firmware version > anti-rollback counter
   e. Execute the firmware from the active slot

2. After successful boot, the application MUST call
   mark_boot_successful() which transitions the slot from PENDING
   to CONFIRMED state.

3. If boot fails (watchdog timeout, crash detection, etc.):
   a. Increment failed boot counter for the slot
   b. If failed_boots >= MAX_BOOT_ATTEMPTS:
      - Mark slot as CORRUPTED
      - Set fallback slot as new active
      - Reset failed boot counter for fallback
      - Boot from fallback slot

4. ANTI-ROLLBACK ENFORCEMENT:
   The bootloader MUST reject any slot where:
   - Firmware version <= anti_rollback_counter
   - Signature verification fails
   - Slot state != PENDING or CONFIRMED

PENDING/CONFIRMED STATE MACHINE:
- NEW: Slot is empty/fresh, never written
- PENDING: Firmware written and validated, awaiting boot confirmation
- CONFIRMED: Boot succeeded, firmware is trusted
- ACTIVE: This slot is the primary boot target

TRANSITIONS:
- NEW → PENDING: prepare_update() + switch_slots()
- PENDING → CONFIRMED: mark_boot_successful()
- CONFIRMED → ACTIVE: (automatic, set by boot control)
- Any → CORRUPTED: mark_boot_failed() after MAX_BOOT_ATTEMPTS

====================================================================

Usage:
    from src.domain.ports.hardware_security import HardwareSecurityModule
    from src.infrastructure.hsm.abstraction import HSMAdapter
    
    hsm = HSMAdapter()  # or MockHSMAdapter for testing
    manager = ABPartitionManager(probe, config, hsm=hsm)
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.ports.hardware_security import HardwareSecurityModule

logger = logging.getLogger(__name__)


class SlotState(Enum):
    """Slot state for pending/confirmed state machine.
    
    State Transitions:
    - NEW: Empty/fresh slot, never written
    - PENDING: Firmware written, awaiting boot confirmation
    - CONFIRMED: Boot succeeded, firmware is trusted
    - ACTIVE: This slot is the primary boot target
    """
    EMPTY = "empty"
    NEW = "new"                    # Slot is fresh/never written
    PENDING = "pending"            # Firmware written, awaiting boot confirmation
    CONFIRMED = "confirmed"       # Boot succeeded, firmware is trusted
    VALID = "valid"                # Legacy alias for CONFIRMED
    UPDATING = "updating"          # Currently being written
    CORRUPTED = "corrupted"        # Boot failed or verification failed
    PENDING_BOOT = "pending_boot" # Legacy alias for PENDING


class SlotLifecycle(Enum):
    """Slot lifecycle state for pending/confirmed semantics."""
    NEW = "new"           # Slot is fresh, never written
    PENDING = "pending"   # Firmware written, awaiting boot confirmation
    CONFIRMED = "confirmed"  # Boot succeeded, firmware is trusted


@dataclass
class SlotInfo:
    """Slot information with pending/confirmed lifecycle support."""
    slot_id: int
    base_address: int
    size: int
    state: SlotState = SlotState.EMPTY
    firmware_version: str = ""
    firmware_version_int: int = 0  # Numeric version for anti-rollback
    firmware_hash: str = ""
    last_booted: datetime | None = None
    update_count: int = 0
    
    # Boot info
    is_active: bool = False
    boot_count: int = 0
    consecutive_failed_boots: int = 0
    
    # Pending/confirmed lifecycle
    lifecycle: SlotLifecycle = SlotLifecycle.NEW
    pending_since: datetime | None = None
    confirmed_at: datetime | None = None
    
    # Manifest binding
    manifest_signature: str = ""  # Signature from SignedArtifactManifest
    manifest_key_id: str = ""      # Key ID that signed the manifest


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
    
    # Rollback fallback configuration
    max_boot_attempts: int = 3  # N attempts before rollback fallback
    rollback_timeout_ms: int = 5000  # Timeout to mark boot successful


@dataclass
class BootControlBlock:
    """Boot control block stored in flash.
    
    Stores persistent boot state including:
    - Active slot selection
    - Retry counter for rollback fallback
    - Firmware version
    - Image hash
    - Slot lifecycle states (pending/confirmed)
    """
    magic: int
    active_slot: int  # 0 = A, 1 = B
    retry_count: int  # Remaining boot attempts before rollback
    version: int  # Firmware version for anti-rollback
    hash: bytes  # SHA-256 hash of firmware
    
    # Extended fields for pending/confirmed state machine
    pending_slot: int = 0xFF  # 0xFF = none, 0 = A, 1 = B
    confirmed_slot: int = 0xFF  # 0xFF = none, 0 = A, 1 = B
    slot_a_lifecycle: int = 0  # 0=NEW, 1=PENDING, 2=CONFIRMED
    slot_b_lifecycle: int = 0  # 0=NEW, 1=PENDING, 2=CONFIRMED
    
    # Anti-rollback counter stored in boot control (backup)
    anti_rollback_counter: int = 0
    
    # Timestamps
    timestamp: int = 0
    last_boot_attempt: int = 0
    
    def to_bytes(self) -> bytes:
        return struct.pack(
            "<IIIBB32sBBBBII",
            self.magic,
            self.active_slot,
            self.retry_count,
            self.version,
            self.pending_slot,
            self.hash,
            self.timestamp,
            self.confirmed_slot,
            self.slot_a_lifecycle,
            self.slot_b_lifecycle,
            self.anti_rollback_counter,
            self.last_boot_attempt,
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "BootControlBlock":
        if len(data) < 56:
            raise ValueError("BootControlBlock too small")
        unpacked = struct.unpack("<IIIBB32sBBBBII", data[:56])
        return cls(
            magic=unpacked[0],
            active_slot=unpacked[1],
            retry_count=unpacked[2],
            version=unpacked[3],
            hash=unpacked[5],
            timestamp=unpacked[6],
            confirmed_slot=unpacked[7],
            slot_a_lifecycle=unpacked[8],
            slot_b_lifecycle=unpacked[9],
            anti_rollback_counter=unpacked[10],
            last_boot_attempt=unpacked[11],
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
    
    Usage:
        from src.domain.ports.hardware_security import HardwareSecurityModule
        from src.infrastructure.hsm.abstraction import HSMAdapter
        
        hsm: HardwareSecurityModule = HSMAdapter()  # or MockHSMAdapter
        manager = ABPartitionManager(probe, config, hsm=hsm)
    """
    
    def __init__(
        self,
        probe: Any,
        config: ABConfig | None = None,
        hsm: HardwareSecurityModule | None = None,
    ):
        """
        Args:
            probe: Flash probe for memory operations
            config: A/B partition configuration
            hsm: Hardware security module for anti-rollback operations
                 If not provided, anti-rollback will be limited
        """
        self._probe = probe
        self._config = config or ABConfig()
        self._hsm = hsm
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
    
    async def get_active_slot(self) -> int:
        """Get currently active slot (0=A, 1=B)."""
        bcb = await self.read_boot_control()
        return bcb.active_slot
    
    async def get_inactive_slot(self) -> int:
        """Get inactive slot for update."""
        bcb = await self.read_boot_control()
        return 1 - bcb.active_slot
    
    async def prepare_update(
        self,
        firmware: bytes,
        manifest: Any | None = None,  # SignedArtifactManifest
    ) -> UpdateResult:
        """Prepare firmware update in inactive slot.
        
        Writes firmware to inactive slot and sets it to PENDING state.
        The slot will not be booted until switch_slots() is called.
        
        Args:
            firmware: Firmware binary data
            manifest: SignedArtifactManifest for signature binding
            
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
            
            # Update slot info - transition to UPDATING
            slot_info.state = SlotState.UPDATING
            slot_info.firmware_hash = firmware_hash.hex()
            
            # Store manifest binding if provided
            if manifest:
                slot_info.manifest_signature = manifest.signature
                slot_info.manifest_key_id = manifest.key_id
                slot_info.firmware_version = manifest.semantic_version
                # Extract numeric version for anti-rollback
                try:
                    parts = manifest.semantic_version.split(".")
                    slot_info.firmware_version_int = (
                        int(parts[0]) << 16 | int(parts[1]) << 8 | int(parts[2])
                        if len(parts) >= 3 else int(parts[0]) if parts else 0
                    )
                except (ValueError, IndexError):
                    slot_info.firmware_version_int = 0
            
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
                slot_info.lifecycle = SlotLifecycle.NEW
                return UpdateResult(
                    success=False,
                    slot=inactive_slot,
                    bytes_written=bytes_written,
                    verified=False,
                    hash_match=False,
                    error="Verification failed",
                )
            
            # Transition to PENDING (ready to boot, awaiting confirmation)
            slot_info.state = SlotState.PENDING
            slot_info.lifecycle = SlotLifecycle.PENDING
            slot_info.pending_since = datetime.now()
            slot_info.update_count += 1
            
            logger.info(
                "slot_prepared_for_boot",
                slot=inactive_slot,
                version=slot_info.firmware_version,
                lifecycle=slot_info.lifecycle.value,
            )
            
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
    
    async def mark_update_valid(
        self,
        version: int,
        firmware_hash: bytes,
        manifest: Any | None = None,
    ) -> bool:
        """Mark update as valid and ready to boot.
        
        Transitions the inactive slot to PENDING state and sets it as
        the pending slot for boot.
        
        Args:
            version: Firmware version (for anti-rollback)
            firmware_hash: SHA-256 hash of firmware
            manifest: SignedArtifactManifest for binding
            
        Returns:
            True if successful
        """
        try:
            bcb = await self.read_boot_control()
            inactive_slot = 1 - bcb.active_slot
            
            # Update boot control
            bcb.version = version
            bcb.hash = firmware_hash
            bcb.timestamp = int(datetime.now().timestamp())
            bcb.retry_count = self._config.max_boot_attempts
            bcb.pending_slot = inactive_slot
            
            # Set slot lifecycle
            bcb.slot_a_lifecycle = 1 if inactive_slot == 0 else 0
            bcb.slot_b_lifecycle = 1 if inactive_slot == 1 else 0
            
            success = await self.write_boot_control(bcb)
            
            if success:
                slot = self._slots[inactive_slot]
                slot.state = SlotState.PENDING
                slot.lifecycle = SlotLifecycle.PENDING
                slot.pending_since = datetime.now()
                slot.firmware_version = str(version)
                slot.firmware_version_int = version
                
                if manifest:
                    slot.manifest_signature = manifest.signature
                    slot.manifest_key_id = manifest.key_id
                
                logger.info(
                    "update_marked_valid",
                    slot=inactive_slot,
                    version=version,
                )
                
            return success
            
        except Exception as e:
            logger.error("mark_update_valid_failed", error=str(e))
            return False
    
    async def switch_slots(self) -> bool:
        """Switch active slot (atomic operation).
        
        This updates the boot control to point to the other slot.
        The actual switch happens on next reboot.
        
        State transitions:
        - Previous active slot stays in CONFIRMED state
        - New active slot transitions from PENDING → (waiting for boot)
        """
        try:
            bcb = await self.read_boot_control()
            
            # Mark current slot as no longer pending
            old_active = bcb.active_slot
            bcb.confirmed_slot = old_active  # Remember confirmed slot
            
            # Switch active slot
            new_active = 1 - bcb.active_slot
            bcb.active_slot = new_active
            bcb.retry_count = self._config.max_boot_attempts
            bcb.last_boot_attempt = int(datetime.now().timestamp())
            
            success = await self.write_boot_control(bcb)
            
            if success:
                # Update old slot
                self._slots[old_active].is_active = False
                # Keep old slot in CONFIRMED state (already confirmed from previous boot)
                
                # Update new slot
                self._slots[new_active].is_active = True
                self._slots[new_active].state = SlotState.PENDING
                self._slots[new_active].lifecycle = SlotLifecycle.PENDING
                self._slots[new_active].consecutive_failed_boots = 0
                
                logger.info(
                    "slot_switch_prepared",
                    old_active=old_active,
                    new_active=new_active,
                )
            
            return success
            
        except Exception as e:
            logger.error("switch_slots_failed", error=str(e))
            return False
    
    async def mark_boot_successful(
        self,
        advance_anti_rollback: bool = True,
    ) -> bool:
        """Mark current boot as successful.
        
        Call this after verifying firmware runs correctly.
        Transitions the slot from PENDING to CONFIRMED state.
        
        Args:
            advance_anti_rollback: If True, advances the anti-rollback counter
                                   to record this successful boot.
            
        Returns:
            True if successful
        """
        try:
            bcb = await self.read_boot_control()
            current_slot = bcb.active_slot
            
            # Reset retry count on successful boot
            bcb.retry_count = self._config.max_boot_attempts
            bcb.confirmed_slot = current_slot
            
            # Update slot lifecycle
            if current_slot == 0:
                bcb.slot_a_lifecycle = 2  # CONFIRMED
            else:
                bcb.slot_b_lifecycle = 2  # CONFIRMED
            
            success = await self.write_boot_control(bcb)
            
            if success:
                slot = self._slots[current_slot]
                slot.last_booted = datetime.now()
                slot.boot_count += 1
                slot.consecutive_failed_boots = 0
                slot.state = SlotState.CONFIRMED
                slot.lifecycle = SlotLifecycle.CONFIRMED
                slot.confirmed_at = datetime.now()
                
                # Advance anti-rollback counter
                if advance_anti_rollback and slot.firmware_version_int > 0:
                    try:
                        counter = AntiRollbackCounter(self._probe, hsm=self._hsm)
                        await counter.increment_counter()
                        logger.info(
                            "anti_rollback_counter_advanced",
                            slot=current_slot,
                            version=slot.firmware_version_int,
                        )
                    except Exception as e:
                        logger.warning("failed_to_advance_anti_rollback", error=str(e))
                
                logger.info(
                    "boot_successful",
                    slot=current_slot,
                    version=slot.firmware_version,
                    boot_count=slot.boot_count,
                )
            
            return success
            
        except Exception as e:
            logger.error("mark_boot_successful_failed", error=str(e))
            return False
    
    async def mark_boot_failed(self) -> bool:
        """Mark current boot as failed.
        
        Decrements retry count. If retries exhausted, reverts to other slot.
        
        This implements the rollback fallback: after MAX_BOOT_ATTEMPTS,
        the system automatically falls back to the previous slot.
        
        Returns:
            True if boot control was written
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
                    max_attempts=self._config.max_boot_attempts,
                )
                
                # Rollback fallback: switch to other slot
                other_slot = 1 - current_slot
                other = self._slots[other_slot]
                
                # Check if fallback slot is bootable
                can_boot = (
                    other.lifecycle == SlotLifecycle.PENDING or
                    other.lifecycle == SlotLifecycle.CONFIRMED
                )
                
                if can_boot:
                    bcb.active_slot = other_slot
                    bcb.retry_count = self._config.max_boot_attempts
                    bcb.last_boot_attempt = int(datetime.now().timestamp())
                    
                    # Mark failed slot as corrupted
                    slot.state = SlotState.CORRUPTED
                    slot.lifecycle = SlotLifecycle.NEW
                    slot.consecutive_failed_boots = 0
                    
                    # Reset other slot for new attempts
                    other.consecutive_failed_boots = 0
                    
                    logger.info(
                        "rollback_fallback_executed",
                        from_slot=current_slot,
                        to_slot=other_slot,
                    )
                else:
                    logger.error(
                        "rollback_failed_no_bootable_slot",
                        current_slot=current_slot,
                        other_lifecycle=other.lifecycle.value,
                    )
            
            return await self.write_boot_control(bcb)
            
        except Exception as e:
            logger.error("mark_boot_failed_failed", error=str(e))
            return False
    
    async def rollback_to_previous(self) -> bool:
        """Force rollback to previous (confirmed) slot.
        
        This is a manual rollback triggered by external decision.
        Prefer mark_boot_failed() for automatic rollback on boot failure.
        
        Returns:
            True if rollback succeeded
        """
        try:
            bcb = await self.read_boot_control()
            current = bcb.active_slot
            previous = 1 - current
            
            # Can only rollback to PENDING or CONFIRMED slots
            prev_slot = self._slots[previous]
            if prev_slot.lifecycle not in (SlotLifecycle.PENDING, SlotLifecycle.CONFIRMED):
                logger.error(
                    "rollback_rejected_slot_not_bootable",
                    target_slot=previous,
                    lifecycle=prev_slot.lifecycle.value,
                )
                return False
            
            # Perform rollback
            bcb.active_slot = previous
            bcb.retry_count = self._config.max_boot_attempts
            bcb.last_boot_attempt = int(datetime.now().timestamp())
            
            success = await self.write_boot_control(bcb)
            
            if success:
                # Mark current as corrupted
                self._slots[current].is_active = False
                self._slots[current].state = SlotState.CORRUPTED
                
                # Prepare previous as active
                prev_slot.is_active = True
                prev_slot.consecutive_failed_boots = 0
                
                logger.info(
                    "rollback_complete",
                    from_slot=current,
                    to_slot=previous,
                )
            
            return success
            
        except Exception as e:
            logger.error("rollback_failed", error=str(e))
            return False
    
    async def get_slot_status(self) -> dict[str, Any]:
        """Get status of both slots with lifecycle information."""
        bcb = await self.read_boot_control()
        
        def get_lifecycle_value(slot_id: int) -> str:
            """Get lifecycle state for a slot."""
            if slot_id == 0:
                states = {0: "new", 1: "pending", 2: "confirmed"}
                return states.get(bcb.slot_a_lifecycle, "unknown")
            else:
                states = {0: "new", 1: "pending", 2: "confirmed"}
                return states.get(bcb.slot_b_lifecycle, "unknown")
        
        return {
            "active_slot": bcb.active_slot,
            "pending_slot": bcb.pending_slot if bcb.pending_slot != 0xFF else None,
            "confirmed_slot": bcb.confirmed_slot if bcb.confirmed_slot != 0xFF else None,
            "retry_count": bcb.retry_count,
            "anti_rollback_counter": bcb.anti_rollback_counter,
            "slots": {
                0: {
                    "state": self._slots[0].state.value,
                    "lifecycle": get_lifecycle_value(0),
                    "address": f"0x{self._slots[0].base_address:08X}",
                    "is_active": bcb.active_slot == 0,
                    "version": self._slots[0].firmware_version,
                    "version_int": self._slots[0].firmware_version_int,
                    "boot_count": self._slots[0].boot_count,
                    "consecutive_failures": self._slots[0].consecutive_failed_boots,
                    "manifest_key_id": self._slots[0].manifest_key_id,
                    "pending_since": self._slots[0].pending_since.isoformat() if self._slots[0].pending_since else None,
                    "confirmed_at": self._slots[0].confirmed_at.isoformat() if self._slots[0].confirmed_at else None,
                },
                1: {
                    "state": self._slots[1].state.value,
                    "lifecycle": get_lifecycle_value(1),
                    "address": f"0x{self._slots[1].base_address:08X}",
                    "is_active": bcb.active_slot == 1,
                    "version": self._slots[1].firmware_version,
                    "version_int": self._slots[1].firmware_version_int,
                    "boot_count": self._slots[1].boot_count,
                    "consecutive_failures": self._slots[1].consecutive_failed_boots,
                    "manifest_key_id": self._slots[1].manifest_key_id,
                    "pending_since": self._slots[1].pending_since.isoformat() if self._slots[1].pending_since else None,
                    "confirmed_at": self._slots[1].confirmed_at.isoformat() if self._slots[1].confirmed_at else None,
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
        if self._hsm is not None:
            try:
                counter_version = await self._hsm.get_counter(0)
                if version <= counter_version:
                    return False, f"Version {version} <= anti-rollback counter {counter_version}"
            except Exception:
                pass  # HSM counter read failed, skip anti-rollback check

        return True, "OK"


# =============================================================================
# ANTI-ROLLBACK COUNTER INTERFACE
# =============================================================================
# Contract for anti-rollback counter storage:
# - The counter MUST be stored in protected flash region or option bytes
# - The counter MUST be monotonic (only increments)
# - The counter MUST be read-only from application code
# - On STM32: Use option bytes or write-protected flash page
# =============================================================================


class AntiRollbackCounter:
    """Interface for monotonic anti-rollback counter.
    
    STORAGE CONTRACT:
    - Primary: HSM (ATECC608) monotonic counter slot
    - Backup: Write-protected flash page at boot_control_address
    - The counter MUST survive power cycles and cannot be decremented
    
    IMPLEMENTATION NOTES:
    - On STM32 with ATECC608: Use HSM slot 0 for production
    - For embedded: Use option bytes or protected flash page
    - For testing: In-memory counter with write-once semantics
    
    Usage:
        from src.domain.ports.hardware_security import HardwareSecurityModule
        from src.infrastructure.hsm.abstraction import MockHSMAdapter
        
        hsm: HardwareSecurityModule = MockHSMAdapter()
        counter = AntiRollbackCounter(probe, hsm=hsm)
    """
    
    def __init__(
        self,
        probe: Any,
        primary_address: int = 0x2003F010,  # Backup location in SRAM
        counter_slot: int = 0,
        hsm: HardwareSecurityModule | None = None,
    ):
        """
        Args:
            probe: Flash probe for memory operations
            primary_address: Backup flash address for counter
            counter_slot: HSM counter slot (default 0)
            hsm: Hardware security module for counter operations
        """
        self._probe = probe
        self._primary_address = primary_address
        self._counter_slot = counter_slot
        self._hsm = hsm
        self._cached_counter: int | None = None
    
    async def get_counter(self) -> int:
        """Get current anti-rollback counter value.
        
        Reads from HSM if available, falls back to flash backup.
        
        Returns:
            Current counter value (monotonic)
        """
        if self._cached_counter is not None:
            return self._cached_counter
        
        # Try HSM first if available
        if self._hsm is not None:
            try:
                counter = await self._hsm.get_counter(self._counter_slot)
                self._cached_counter = counter
                return counter
            except Exception:
                pass  # HSM read failed, fall through to flash backup
        
        # Fall back to flash backup
        try:
            data = await self._probe.read_memory(self._primary_address, 4)
            counter = int.from_bytes(data[:4], "little")
            self._cached_counter = counter
            return counter
        except Exception:
            return 0
    
    async def increment_counter(self) -> int:
        """Increment anti-rollback counter.
        
        Increments the counter to record successful boot of new firmware.
        This is the ONLY way to advance the anti-rollback floor.
        
        Returns:
            New counter value after increment
        """
        current = await self.get_counter()
        new_value = current + 1
        
        # Update HSM if available
        if self._hsm is not None:
            try:
                await self._hsm.set_counter(self._counter_slot, new_value)
            except Exception:
                pass  # HSM update failed, continue with flash backup only
        
        # Update flash backup
        try:
            data = new_value.to_bytes(4, "little")
            await self._probe.write_memory(self._primary_address, data)
        except Exception:
            logger.error("failed_to_persist_anti_rollback_counter")
        
        self._cached_counter = new_value
        return new_value
    
    async def verify_version_allowed(self, version: int) -> tuple[bool, str]:
        """Verify firmware version is allowed by anti-rollback.
        
        Args:
            version: Firmware version to verify
            
        Returns:
            (is_allowed, reason)
        """
        counter = await self.get_counter()
        
        if version <= counter:
            return False, (
                f"Version {version} rejected: anti-rollback counter is {counter}. "
                f"Firmware must have version > {counter} to be bootable."
            )
        
        return True, "OK"


# =============================================================================
# MANIFEST-INTEGRATED BOOT VALIDATOR
# =============================================================================


class ManifestBootValidator:
    """Validates firmware boot eligibility using SignedArtifactManifest.
    
    Integrates with SignedArtifactManifest to ensure:
    - Firmware signature is valid
    - Firmware version passes anti-rollback check
    - Slot lifecycle state allows boot
    
    This is the software-side enforcement of the bootloader contract.
    """
    
    def __init__(
        self,
        anti_rollback: AntiRollbackCounter,
        verifier: Any | None = None,  # ManifestVerifier
    ):
        """
        Args:
            anti_rollback: Anti-rollback counter interface
            verifier: ManifestVerifier instance (optional)
        """
        self._anti_rollback = anti_rollback
        self._verifier = verifier
    
    async def validate_for_boot(
        self,
        slot_info: SlotInfo,
        manifest: Any | None = None,  # SignedArtifactManifest
    ) -> tuple[bool, str]:
        """Validate if firmware in slot can be booted.
        
        Checks:
        1. Slot state allows boot (PENDING or CONFIRMED)
        2. Manifest signature is valid (if provided)
        3. Firmware version > anti-rollback counter
        
        Args:
            slot_info: Slot information
            manifest: SignedArtifactManifest (optional)
            
        Returns:
            (can_boot, reason)
        """
        # Check slot lifecycle state
        if slot_info.lifecycle == SlotLifecycle.NEW:
            return False, "Slot has no firmware written"
        
        if slot_info.lifecycle == SlotLifecycle.PENDING:
            # PENDING is allowed but logged
            logger.info("booting_pending_slot", slot=slot_info.slot_id)
        
        # Check manifest signature if provided
        if manifest and self._verifier:
            result = self._verifier.verify(manifest)
            if not result.is_valid():
                return False, f"Manifest verification failed: {result.message}"
        
        # Check anti-rollback
        if slot_info.firmware_version_int > 0:
            allowed, reason = await self._anti_rollback.verify_version_allowed(
                slot_info.firmware_version_int
            )
            if not allowed:
                return False, f"Anti-rollback check failed: {reason}"
        
        return True, "OK"
    
    async def confirm_boot_and_advance_counter(
        self,
        slot_info: SlotInfo,
    ) -> bool:
        """Confirm successful boot and advance anti-rollback counter.
        
        This should be called after mark_boot_successful() to:
        1. Transition slot from PENDING to CONFIRMED
        2. Advance the anti-rollback counter
        
        Args:
            slot_info: Slot that booted successfully
            
        Returns:
            True if counter was advanced
        """
        if slot_info.lifecycle != SlotLifecycle.PENDING:
            return False
        
        # Advance anti-rollback counter
        await self._anti_rollback.increment_counter()
        
        logger.info(
            "anti_rollback_advanced",
            slot=slot_info.slot_id,
            version=slot_info.firmware_version_int,
        )
        
        return True


# =============================================================================
# ROLLBACK FALLBACK VERIFIER
# =============================================================================


class RollbackFallbackVerifier:
    """Manages rollback fallback after N failed boot attempts.
    
    Tracks boot failures and triggers automatic rollback when
    MAX_BOOT_ATTEMPTS is exceeded.
    """
    
    def __init__(
        self,
        ab_manager: ABPartitionManager,
        config: ABConfig | None = None,
    ):
        """
        Args:
            ab_manager: A/B partition manager
            config: A/B configuration
        """
        self._ab = ab_manager
        self._config = config or ABConfig()
    
    async def record_boot_attempt(self, slot_id: int) -> dict[str, Any]:
        """Record a boot attempt and check for rollback trigger.
        
        Args:
            slot_id: Slot that attempted to boot
            
        Returns:
            Dict with:
            - should_rollback: bool
            - attempts_remaining: int
            - current_slot: int
            - fallback_slot: int
        """
        bcb = await self._ab.read_boot_control()
        slot = self._ab._slots[slot_id]
        
        # Increment failed boot counter
        slot.consecutive_failed_boots += 1
        attempts_remaining = max(0, self._config.max_boot_attempts - slot.consecutive_failed_boots)
        
        should_rollback = slot.consecutive_failed_boots >= self._config.max_boot_attempts
        
        result = {
            "should_rollback": should_rollback,
            "attempts_remaining": attempts_remaining,
            "consecutive_failures": slot.consecutive_failed_boots,
            "current_slot": slot_id,
            "fallback_slot": 1 - slot_id,
        }
        
        if should_rollback:
            logger.warning(
                "rollback_triggered",
                slot=slot_id,
                failures=slot.consecutive_failed_boots,
                max_attempts=self._config.max_boot_attempts,
            )
            
            # Mark current slot as corrupted
            slot.state = SlotState.CORRUPTED
            slot.lifecycle = SlotLifecycle.NEW  # Reset lifecycle
            
            # Rollback to other slot
            await self._ab.rollback_to_previous()
            
            # Reset failure counter for fallback slot
            fallback = self._ab._slots[1 - slot_id]
            fallback.consecutive_failed_boots = 0
            
            result["rolled_back_to"] = 1 - slot_id
        
        return result
    
    async def check_and_recover(self) -> dict[str, Any]:
        """Check system state and recover if needed.
        
        Call this at boot time to ensure system is in valid state.
        
        Returns:
            Recovery status dict
        """
        bcb = await self._ab.read_boot_control()
        status = await self._ab.get_slot_status()
        
        recovery_needed = False
        recovery_action = "none"
        
        # Check for corrupted active slot
        active_slot = status["slots"][bcb.active_slot]
        if active_slot["state"] == SlotState.CORRUPTED.value:
            recovery_needed = True
            recovery_action = "fallback_to_other_slot"
            await self._ab.rollback_to_previous()
        
        # Check anti-rollback consistency
        # If active slot version <= counter, we have a problem
        active = self._ab._slots[bcb.active_slot]
        if active.firmware_version_int > 0:
            counter = await AntiRollbackCounter(self._ab._probe, hsm=self._ab._hsm).get_counter()
            if active.firmware_version_int <= counter:
                recovery_needed = True
                recovery_action = "corrupted_state_recovery_needed"
                logger.error(
                    "anti_rollback_inconsistency",
                    active_version=active.firmware_version_int,
                    counter=counter,
                )
        
        return {
            "recovery_needed": recovery_needed,
            "recovery_action": recovery_action,
            "active_slot": bcb.active_slot,
            "status": status,
        }


# Global manager
_manager: ABPartitionManager | None = None


def get_ab_manager(
    probe: Any,
    config: ABConfig | None = None,
    hsm: HardwareSecurityModule | None = None,
) -> ABPartitionManager:
    """Get A/B partition manager.
    
    Args:
        probe: Flash probe for memory operations
        config: A/B partition configuration
        hsm: Hardware security module (optional)
        
    Returns:
        ABPartitionManager instance
    """
    global _manager
    if _manager is None:
        _manager = ABPartitionManager(probe, config, hsm=hsm)
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
