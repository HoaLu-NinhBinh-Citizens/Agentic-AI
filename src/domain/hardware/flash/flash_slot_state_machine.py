"""Flash Slot State Machine - MCUboot-like A/B slot management with power-loss safety.

Phase 2 (P0-B): End-to-End Flash State Machine
Implements MCUboot-like slot table model with:
- Pending/Confirmed/Boot states
- Rollback activation confirmation
- Anti-rollback monotonic counter binding
- Power-loss recovery

This module provides the authoritative state machine for firmware OTA operations,
ensuring atomic transitions and safe rollback on failure.

MCUboot Slot States:
    INVALID      -> Empty slot, not bootable
    TESTING      -> New image written, pending boot validation
    VALID        -> Image validated, bootable
    PERMANENT    -> Image marked as permanent (no rollback)
    RESERVED     -> Slot temporarily locked

State Transitions:
    INVALID -> TESTING: After successful flash + verify
    TESTING -> VALID:   After successful boot + health check
    TESTING -> INVALID:  After failed boot or health check
    VALID -> PERMANENT:  After explicit confirmation
    VALID -> INVALID:    After explicit revert
    PERMANENT -> INVALID: After explicit downgrade
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .flash_transaction import FlashTransaction, FlashTransactionManager
    from .flash_journal import FlashJournal
    from .flash_lock import FlashFenceToken, TargetFlashLock

logger = logging.getLogger(__name__)


# =============================================================================
# SLOT STATE DEFINITIONS
# =============================================================================


class SlotState(Enum):
    """MCUboot-style slot states for firmware images.
    
    These states represent the complete lifecycle of a firmware slot:
    - INVALID: Empty or corrupted slot
    - TESTING: New image written, pending boot validation (P0-B key state)
    - VALID: Image validated, ready to boot
    - PERMANENT: Image marked permanent, no rollback
    - RESERVED: Slot temporarily locked
    """
    
    INVALID = "invalid"           # Empty, erased, or corrupted slot
    TESTING = "testing"           # New image pending validation (P0-B: Pending equivalent)
    VALID = "valid"               # Image validated, bootable
    PERMANENT = "permanent"       # Image confirmed, no rollback allowed
    RESERVED = "reserved"         # Slot locked during operation


class SlotIdentity(Enum):
    """Identifies which slot (A or B)."""
    SLOT_A = "A"
    SLOT_B = "B"


class ImageStatus(Enum):
    """Status of an image within a slot."""
    EMPTY = "empty"
    PARTIAL = "partial"       # Partially written (power loss during flash)
    WRITE_COMPLETE = "write_complete"  # Fully written, not yet verified
    VERIFY_IN_PROGRESS = "verify_in_progress"
    VERIFY_FAILED = "verify_failed"
    VERIFY_PASSED = "verify_passed"
    BOOT_ATTEMPTED = "boot_attempted"
    BOOT_SUCCESS = "boot_success"
    BOOT_FAILED = "boot_failed"


class BootAttemptResult(Enum):
    """Result of boot attempt."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CORRUPTED = "corrupted"
    HEALTH_CHECK_FAILED = "health_check_failed"


# =============================================================================
# SLOT ENTRY (MCUboot-style slot table)
# =============================================================================


@dataclass
class SlotEntry:
    """Single slot entry in the slot table.
    
    Mirrors MCUboot's image trailer concept:
    - Slot address and size
    - Image version and hash
    - Copy/boot status
    - Trailer magic validation
    """
    
    # Slot identification
    slot_id: str = ""  # "A" or "B"
    slot_address: int = 0  # Flash address of slot start
    slot_size: int = 0  # Total slot size in bytes
    
    # MCUboot trailer state
    state: SlotState = SlotState.INVALID
    image_status: ImageStatus = ImageStatus.EMPTY
    
    # Image metadata
    image_version: tuple[int, int, int, int] = (0, 0, 0, 0)  # major.minor.revision.build
    image_hash: str = ""  # SHA256 of image
    image_size: int = 0  # Actual size of image (excluding trailer)
    
    # MCUboot-style flags
    copy_done: bool = False  # Image copied to this slot
    swap_status: int = 0  # Swap operation status
    image_ok: bool = False  # Image confirmed as good (set after successful boot)
    
    # Anti-rollback binding
    version_binding: int = 0  # Version number for anti-rollback
    monotonic_counter: int = 0  # Counter value at time of flash
    
    # Timestamps
    flashed_at: datetime | None = None
    booted_at: datetime | None = None
    confirmed_at: datetime | None = None
    
    # Trailer magic
    has_trailer: bool = False
    trailer_magic: int = 0
    
    # Boot attempts
    boot_attempts: int = 0
    max_boot_attempts: int = 3
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "slot_id": self.slot_id,
            "slot_address": hex(self.slot_address),
            "slot_size": self.slot_size,
            "state": self.state.value,
            "image_status": self.image_status.value,
            "image_version": ".".join(str(v) for v in self.image_version),
            "image_hash": self.image_hash,
            "image_size": self.image_size,
            "copy_done": self.copy_done,
            "swap_status": self.swap_status,
            "image_ok": self.image_ok,
            "version_binding": self.version_binding,
            "monotonic_counter": self.monotonic_counter,
            "flashed_at": self.flashed_at.isoformat() if self.flashed_at else None,
            "booted_at": self.booted_at.isoformat() if self.booted_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "boot_attempts": self.boot_attempts,
            "max_boot_attempts": self.max_boot_attempts,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlotEntry:
        """Create from dictionary."""
        version_str = data.get("image_version", "0.0.0.0")
        version_parts = tuple(int(x) for x in version_str.split("."))
        
        flashed_at = data.get("flashed_at")
        booted_at = data.get("booted_at")
        confirmed_at = data.get("confirmed_at")
        
        return cls(
            slot_id=data.get("slot_id", ""),
            slot_address=int(data.get("slot_address", "0x0"), 16) if isinstance(data.get("slot_address"), str) else data.get("slot_address", 0),
            slot_size=data.get("slot_size", 0),
            state=SlotState(data.get("state", "invalid")),
            image_status=ImageStatus(data.get("image_status", "empty")),
            image_version=version_parts,
            image_hash=data.get("image_hash", ""),
            image_size=data.get("image_size", 0),
            copy_done=data.get("copy_done", False),
            swap_status=data.get("swap_status", 0),
            image_ok=data.get("image_ok", False),
            version_binding=data.get("version_binding", 0),
            monotonic_counter=data.get("monotonic_counter", 0),
            flashed_at=datetime.fromisoformat(flashed_at) if flashed_at else None,
            booted_at=datetime.fromisoformat(booted_at) if booted_at else None,
            confirmed_at=datetime.fromisoformat(confirmed_at) if confirmed_at else None,
            boot_attempts=data.get("boot_attempts", 0),
            max_boot_attempts=data.get("max_boot_attempts", 3),
        )
    
    def can_boot(self) -> bool:
        """Check if slot can be booted."""
        return (
            self.state in (SlotState.VALID, SlotState.TESTING)
            and self.image_status in (ImageStatus.VERIFY_PASSED, ImageStatus.BOOT_SUCCESS)
            and self.boot_attempts < self.max_boot_attempts
        )
    
    def is_active(self) -> bool:
        """Check if slot is currently active (booted and running)."""
        return self.state == SlotState.VALID and self.image_ok


@dataclass
class SlotTable:
    """MCUboot-style slot table.
    
    Contains entries for all slots and tracks which is active.
    Persisted to flash for power-loss recovery.
    """
    
    # Slot entries
    slot_a: SlotEntry = field(default_factory=lambda: SlotEntry(slot_id="A"))
    slot_b: SlotEntry = field(default_factory=lambda: SlotEntry(slot_id="B"))
    
    # Active slot tracking
    active_slot: str = "A"  # Currently booted slot
    pending_slot: str | None = None  # Slot pending boot
    
    # Global state
    boot_count: int = 0  # Total boot count
    last_boot_time: datetime | None = None
    last_update_time: datetime | None = None
    
    # Scratch area (for swap operations)
    scratch_address: int = 0
    scratch_size: int = 0
    
    # Slot table magic
    SLOT_TABLE_MAGIC: int = 0x8693DAA  # "SLTAB"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slot_a": self.slot_a.to_dict(),
            "slot_b": self.slot_b.to_dict(),
            "active_slot": self.active_slot,
            "pending_slot": self.pending_slot,
            "boot_count": self.boot_count,
            "last_boot_time": self.last_boot_time.isoformat() if self.last_boot_time else None,
            "last_update_time": self.last_update_time.isoformat() if self.last_update_time else None,
            "scratch_address": hex(self.scratch_address),
            "scratch_size": self.scratch_size,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlotTable:
        """Create from dictionary."""
        last_boot = data.get("last_boot_time")
        last_update = data.get("last_update_time")
        
        table = cls(
            slot_a=SlotEntry.from_dict(data.get("slot_a", {})),
            slot_b=SlotEntry.from_dict(data.get("slot_b", {})),
            active_slot=data.get("active_slot", "A"),
            pending_slot=data.get("pending_slot"),
            boot_count=data.get("boot_count", 0),
            last_boot_time=datetime.fromisoformat(last_boot) if last_boot else None,
            last_update_time=datetime.fromisoformat(last_update) if last_update else None,
            scratch_address=int(data.get("scratch_address", "0x0"), 16) if isinstance(data.get("scratch_address"), str) else data.get("scratch_address", 0),
            scratch_size=data.get("scratch_size", 0),
        )
        table.slot_a.slot_id = "A"
        table.slot_b.slot_id = "B"
        return table
    
    def get_slot(self, slot_id: str) -> SlotEntry:
        """Get slot by ID."""
        if slot_id == "A":
            return self.slot_a
        return self.slot_b
    
    def get_inactive_slot(self) -> SlotEntry:
        """Get the inactive slot (for flashing new firmware)."""
        return self.slot_b if self.active_slot == "A" else self.slot_a
    
    def get_active_slot(self) -> SlotEntry:
        """Get the currently active slot."""
        return self.slot_a if self.active_slot == "A" else self.slot_b


# =============================================================================
# ANTI-ROLLBACK MANAGER (P0-B)
# =============================================================================


@dataclass
class AntiRollbackManager:
    """Anti-rollback protection using monotonic counter.
    
    P0-B: Binds firmware version to monotonic counter to prevent
    downgrade attacks. Counter stored in secure flash region.
    
    Key Features:
    - Hardware monotonic counter (eFuse, OTP, or battery-backed RAM)
    - Version binding (minimum version stored)
    - Atomic counter update after successful flash
    - Power-loss safe (counter persists across reboots)
    """
    
    # Counter storage
    counter_address: int = 0  # Flash/OTP address for counter
    version_binding_address: int = 0  # Address for min version
    
    # Current state
    current_counter: int = 0
    minimum_version: tuple[int, int, int, int] = (0, 0, 0, 0)
    
    # Probe for hardware access
    probe: Any = field(default=None)
    
    # Lock for atomic operations
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def version_to_int(self, version: tuple[int, int, int, int]) -> int:
        """Convert version tuple to integer for comparison."""
        major, minor, revision, build = version
        return (major << 24) | (minor << 16) | (revision << 8) | build
    
    def int_to_version(self, value: int) -> tuple[int, int, int, int]:
        """Convert integer to version tuple."""
        major = (value >> 24) & 0xFF
        minor = (value >> 16) & 0xFF
        revision = (value >> 8) & 0xFF
        build = value & 0xFF
        return (major, minor, revision, build)
    
    async def read_counter(self) -> int:
        """Read current monotonic counter from storage."""
        if not self.probe or self.counter_address == 0:
            return self.current_counter
        
        try:
            data = await self.probe.read_memory(self.counter_address, 4)
            if len(data) >= 4:
                self.current_counter = struct.unpack("<I", data)[0]
        except Exception as e:
            logger.warning("anti_rollback_read_counter_failed: %s", str(e))
        
        return self.current_counter
    
    async def write_counter(self, value: int) -> bool:
        """Write monotonic counter to storage."""
        if not self.probe or self.counter_address == 0:
            self.current_counter = value
            return True
        
        try:
            data = struct.pack("<I", value)
            await self.probe.write_memory(self.counter_address, data)
            
            # Verify
            verify = await self.probe.read_memory(self.counter_address, 4)
            if len(verify) >= 4 and struct.unpack("<I", verify)[0] == value:
                self.current_counter = value
                return True
        except Exception as e:
            logger.error("anti_rollback_write_counter_failed: %s", str(e))
        
        return False
    
    async def read_minimum_version(self) -> tuple[int, int, int, int]:
        """Read minimum allowed version from storage."""
        if not self.probe or self.version_binding_address == 0:
            return self.minimum_version
        
        try:
            data = await self.probe.read_memory(self.version_binding_address, 4)
            if len(data) >= 4:
                value = struct.unpack("<I", data)[0]
                self.minimum_version = self.int_to_version(value)
        except Exception as e:
            logger.warning("anti_rollback_read_version_failed: %s", str(e))
        
        return self.minimum_version
    
    async def write_minimum_version(self, version: tuple[int, int, int, int]) -> bool:
        """Write minimum version to storage."""
        if not self.probe or self.version_binding_address == 0:
            self.minimum_version = version
            return True
        
        try:
            value = self.version_to_int(version)
            data = struct.pack("<I", value)
            await self.probe.write_memory(self.version_binding_address, data)
            
            # Verify
            verify = await self.probe.read_memory(self.version_binding_address, 4)
            if len(verify) >= 4 and struct.unpack("<I", verify)[0] == value:
                self.minimum_version = version
                return True
        except Exception as e:
            logger.error("anti_rollback_write_version_failed: %s", str(e))
        
        return False
    
    async def validate_version(self, version: tuple[int, int, int, int]) -> tuple[bool, str]:
        """Validate firmware version against anti-rollback policy.
        
        Args:
            version: New firmware version to validate
            
        Returns:
            (is_valid, error_message)
        """
        async with self._lock:
            min_version = await self.read_minimum_version()
            new_version_int = self.version_to_int(version)
            min_version_int = self.version_to_int(min_version)
            
            if new_version_int < min_version_int:
                return False, (
                    f"Anti-rollback: version {version} < minimum {min_version}. "
                    f"Downgrade blocked to prevent known vulnerability exploitation."
                )
            
            return True, "Version acceptable"
    
    async def increment_counter(self, new_version: tuple[int, int, int, int]) -> tuple[bool, str]:
        """Increment monotonic counter after successful flash.
        
        CRITICAL: This must be called AFTER successful boot validation
        to ensure the firmware is actually running before committing.
        
        Args:
            new_version: The new firmware version
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            current = await self.read_counter()
            current_min_version = await self.read_minimum_version()
            
            # Increment counter
            new_counter = current + 1
            
            # Update minimum version if this is higher
            new_version_int = self.version_to_int(new_version)
            min_version_int = self.version_to_int(current_min_version)
            
            if new_version_int > min_version_int:
                write_version = True
            else:
                write_version = False
            
            # Atomic update: counter must be written
            if not await self.write_counter(new_counter):
                return False, "Failed to update monotonic counter"
            
            # Update version binding if needed
            if write_version:
                if not await self.write_minimum_version(new_version):
                    logger.warning("anti_rollback_version_update_failed: version=%s", new_version)
                    # Non-fatal: counter was updated, version binding can be retried
            
            logger.info("anti_rollback_counter_incremented: counter=%s version=%s", new_counter, new_version)
            
            return True, "Counter updated"


# =============================================================================
# SLOT STATE MACHINE (P0-B CORE)
# =============================================================================


@dataclass
class FlashSlotStateMachine:
    """End-to-End Flash State Machine with MCUboot-like slot management.
    
    P0-B: Complete state machine that integrates:
    - Slot table model
    - Transaction state
    - Journal operations
    - Anti-rollback binding
    - Power-loss recovery
    
    State Machine Flow:
    
    [Power On/Recovery] 
           |
           v
    +-------------+
    | READ_SLOTS  | -- Read slot table from flash
    +-------------+
           |
           v
    +-------------------+
    | CHECK_PENDING     | -- Check for interrupted operation
    +-------------------+
           |
     +-----+-----+
     |           |
     v           v
  [Pending]  [None]
     |           |
     v           v
    +--------+   +---------+
    | RECOVER|   | DETERMINE|
    | STATE  |   | ACTIVE  |
    +--------+   +---------+
           |           |
           +-----+-----+
                 |
                 v
           +-----------+
           | READY     | -- Normal operation
           +-----------+
           
    Flash Flow (Normal):
    1. Acquire lock + fence token
    2. Journal: erase started
    3. Journal: erase completed
    4. Journal: write started
    5. Write firmware to inactive slot
    6. Journal: write completed
    7. Verify image hash
    8. Journal: verify passed
    9. Update slot table: INVALID -> TESTING
    10. Commit journal
    11. Mark pending boot (PENDING_BOOT)
    12. Release lock
    
    Boot Flow:
    1. Read pending marker
    2. Boot into target slot
    3. Run health checks
    4. On success: TESTING -> VALID, commit active
    5. On failure: TESTING -> INVALID, rollback
    
    P0-B: Added TESTING state as critical pending validation state.
    """
    
    # Configuration
    slot_table_address: int = 0x0803F000  # Default: last page of 2MB flash
    slot_a_address: int = 0x08040000
    slot_a_size: int = 0x80000  # 512KB
    slot_b_address: int = 0x080C0000
    slot_b_size: int = 0x80000  # 512KB
    
    # Sub-components
    slot_table: SlotTable = field(default_factory=SlotTable)
    anti_rollback: AntiRollbackManager | None = None
    
    # Hardware interface
    probe: Any = field(default=None)
    
    # Lock manager
    lock_manager: Any = field(default=None)
    
    # Transaction tracking
    _active_transaction_id: str | None = None
    _pending_boot: bool = False
    
    # Recovery state
    _recovery_needed: bool = False
    _recovery_info: dict[str, Any] = field(default_factory=dict)
    
    # Lock for state transitions
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def __post_init__(self) -> None:
        """Initialize slot table with addresses."""
        self.slot_table.slot_a.slot_address = self.slot_a_address
        self.slot_table.slot_a.slot_size = self.slot_a_size
        self.slot_table.slot_b.slot_address = self.slot_b_address
        self.slot_table.slot_b.slot_size = self.slot_b_size
        
        # Default active slot
        self.slot_table.active_slot = "A"
    
    # =========================================================================
    # STATE TRANSITIONS (P0-B CORE)
    # =========================================================================
    
    async def initialize(self) -> tuple[bool, str]:
        """Initialize state machine from flash.
        
        Returns:
            (success, error_message)
        """
        async with self._lock:
            if not self.probe:
                return False, "No probe configured"
            
            try:
                # Read slot table
                data = await self.probe.read_memory(self.slot_table_address, 256)
                
                if len(data) >= 4:
                    magic = struct.unpack("<I", data[:4])[0]
                    
                    if magic == SlotTable.SLOT_TABLE_MAGIC:
                        # Valid slot table exists
                        table_data = json.loads(data[4:].decode("utf-8").rstrip("\x00"))
                        self.slot_table = SlotTable.from_dict(table_data)
                        logger.info("slot_table_loaded: active=%s", self.slot_table.active_slot)
                    else:
                        # No valid table, initialize fresh
                        logger.info("slot_table_not_found_initializing")
                        await self._save_slot_table()
                
                # Check for pending boot (recovery scenario)
                await self._check_pending_boot()
                
                return True, "Initialized"
                
            except Exception as e:
                logger.error("slot_state_machine_init_failed: %s", str(e))
                return False, str(e)
    
    async def _save_slot_table(self) -> bool:
        """Save slot table to flash."""
        if not self.probe:
            return False
        
        try:
            table_json = json.dumps(self.slot_table.to_dict())
            table_bytes = table_json.encode("utf-8")
            
            # Pack with magic
            magic = struct.pack("<I", SlotTable.SLOT_TABLE_MAGIC)
            padded = magic + table_bytes + b"\x00" * (256 - 4 - len(table_bytes))
            
            await self.probe.write_memory(self.slot_table_address, padded[:256])
            self.slot_table.last_update_time = datetime.now()
            
            return True
        except Exception as e:
            logger.error("slot_table_save_failed: %s", str(e))
            return False
    
    async def _check_pending_boot(self) -> None:
        """Check for pending boot scenario (recovery)."""
        # Read last 32 bytes of flash for pending marker
        pending_addr = self.slot_table_address - 32
        try:
            data = await self.probe.read_memory(pending_addr, 32)
            
            # Check for PEND magic (0x50454E44)
            if len(data) >= 4:
                magic = struct.unpack("<I", data[:4])[0]
                if magic == 0x50454E44:
                    self._pending_boot = True
                    self._recovery_needed = True
                    self._recovery_info = {
                        "type": "pending_boot",
                        "pending_addr": hex(pending_addr),
                    }
                    logger.warning("pending_boot_recovery_needed")
        except Exception:
            pass
    
    async def begin_flash(
        self,
        firmware_data: bytes,
        version: tuple[int, int, int, int],
        fence_token: Any = None,
    ) -> tuple[bool, str]:
        """Begin flash operation to inactive slot.
        
        Args:
            firmware_data: Firmware binary to flash
            version: Firmware version tuple
            fence_token: Flash fence token for validation
            
        Returns:
            (success, error_message or slot_id)
        """
        async with self._lock:
            # Validate fence token if provided
            if self.lock_manager and fence_token:
                valid, reason = await self.lock_manager.validate_fence_token(
                    target_name="flash",
                    token=fence_token,
                    operation_name="begin_flash",
                )
                if not valid:
                    return False, f"Fence token invalid: {reason}"
            
            # Get inactive slot
            target_slot = self.slot_table.get_inactive_slot()
            slot_id = target_slot.slot_id
            
            # Check slot is in valid state for flashing
            if target_slot.state not in (SlotState.INVALID, SlotState.TESTING):
                if target_slot.state == SlotState.PERMANENT:
                    return False, "Cannot flash permanent slot without explicit revert"
                return False, f"Slot {slot_id} in invalid state: {target_slot.state.value}"
            
            # Anti-rollback check
            if self.anti_rollback:
                valid, reason = await self.anti_rollback.validate_version(version)
                if not valid:
                    return False, reason
            
            # Calculate image hash
            image_hash = hashlib.sha256(firmware_data).hexdigest()
            
            # Update slot entry (preliminary - actual write happens async)
            target_slot.image_version = version
            target_slot.image_hash = image_hash
            target_slot.image_size = len(firmware_data)
            target_slot.image_status = ImageStatus.PARTIAL
            target_slot.state = SlotState.TESTING
            target_slot.flashed_at = datetime.now()
            target_slot.boot_attempts = 0
            
            logger.info(
                "flash_begin",
                slot=slot_id,
                version=version,
                size=len(firmware_data),
                hash=image_hash[:16],
            )
            
            return True, slot_id
    
    async def write_slot(
        self,
        slot_id: str,
        firmware_data: bytes,
        fence_token: Any = None,
    ) -> tuple[bool, str]:
        """Write firmware to slot.
        
        Args:
            slot_id: Slot to write ("A" or "B")
            firmware_data: Firmware binary
            fence_token: Flash fence token
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            if self.lock_manager and fence_token:
                valid, reason = await self.lock_manager.validate_fence_token(
                    target_name="flash",
                    token=fence_token,
                    operation_name="write",
                )
                if not valid:
                    return False, f"Fence token invalid: {reason}"
            
            slot = self.slot_table.get_slot(slot_id)
            
            # Write firmware
            if not self.probe:
                return False, "No probe configured"
            
            try:
                # Write in chunks (typical flash page size)
                chunk_size = 2048
                offset = 0
                
                while offset < len(firmware_data):
                    chunk = firmware_data[offset : offset + chunk_size]
                    addr = slot.slot_address + offset
                    
                    await self.probe.write_memory(addr, chunk)
                    offset += len(chunk)
                
                # Update status
                slot.image_status = ImageStatus.WRITE_COMPLETE
                
                logger.info("slot_write_complete: slot=%s bytes=%s", slot_id, offset)
                
                return True, "Write complete"
                
            except Exception as e:
                slot.image_status = ImageStatus.PARTIAL
                logger.error("slot_write_failed: slot=%s error=%s", slot_id, str(e))
                return False, str(e)
    
    async def verify_slot(
        self,
        slot_id: str,
        expected_hash: str | None = None,
        fence_token: Any = None,
    ) -> tuple[bool, str]:
        """Verify firmware in slot."""
        async with self._lock:
            if self.lock_manager and fence_token:
                valid, reason = await self.lock_manager.validate_fence_token(
                    target_name="flash",
                    token=fence_token,
                    operation_name="verify",
                )
                if not valid:
                    return False, f"Fence token invalid: {reason}"

            slot = self.slot_table.get_slot(slot_id)
            
            if not self.probe:
                return False, "No probe configured"
            
            try:
                # Update status
                slot.image_status = ImageStatus.VERIFY_IN_PROGRESS
                
                # Read back firmware
                firmware_data = await self.probe.read_memory(
                    slot.slot_address,
                    slot.image_size,
                )
                
                # Calculate hash
                actual_hash = hashlib.sha256(firmware_data).hexdigest()
                
                # Compare
                expected = expected_hash or slot.image_hash
                
                if actual_hash != expected:
                    slot.image_status = ImageStatus.VERIFY_FAILED
                    logger.error("slot_verify_hash_mismatch: slot=%s expected=%s actual=%s", slot_id, expected[:16], actual_hash[:16])
                    return False, "Hash mismatch"
                
                # Verify passed
                slot.image_status = ImageStatus.VERIFY_PASSED
                slot.image_hash = actual_hash
                
                logger.info("slot_verify_passed: slot=%s", slot_id)
                
                return True, "Verified"
                
            except Exception as e:
                slot.image_status = ImageStatus.VERIFY_FAILED
                logger.error("slot_verify_failed: slot=%s error=%s", slot_id, str(e))
                return False, str(e)
    
    async def mark_pending_boot(
        self,
        target_slot_id: str,
        fallback_slot_id: str,
    ) -> tuple[bool, str]:
        """Mark slot as pending boot (P0-B critical step).
        
        This is the "point of no return" - after this, the next boot
        will attempt to boot into the target slot.
        
        Args:
            target_slot_id: Slot to boot into
            fallback_slot_id: Slot to rollback to on failure
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            target_slot = self.slot_table.get_slot(target_slot_id)
            fallback_slot = self.slot_table.get_slot(fallback_slot_id)
            
            # Validate slot states
            if target_slot.image_status != ImageStatus.VERIFY_PASSED:
                return False, f"Target slot not verified: {target_slot.image_status.value}"
            
            if target_slot.state not in (SlotState.INVALID, SlotState.TESTING):
                return False, f"Target slot in invalid state: {target_slot.state.value}"
            
            # Update slot states
            target_slot.state = SlotState.TESTING
            self.slot_table.pending_slot = target_slot_id
            
            # Write pending marker to flash (atomic with slot table)
            if self.probe:
                marker_addr = self.slot_table_address - 32
                timestamp = int(datetime.now().timestamp())
                
                # Simple pending marker: slot_id + fallback + timestamp
                marker = struct.pack(
                    "<IIII",
                    0x50454E44,  # PEND magic
                    ord(target_slot_id[0]) if target_slot_id else 0,
                    ord(fallback_slot_id[0]) if fallback_slot_id else 0,
                    timestamp,
                )
                
                await self.probe.write_memory(marker_addr, marker)
                self._pending_boot = True
            
            # Save slot table
            await self._save_slot_table()
            
            logger.info("pending_boot_marked: target=%s fallback=%s", target_slot_id, fallback_slot_id)
            
            return True, "Pending boot marked"
    
    async def confirm_boot(
        self,
        slot_id: str,
        result: BootAttemptResult,
    ) -> tuple[bool, str]:
        """Confirm boot result and update slot state.
        
        P0-B: This is the critical state transition:
        - SUCCESS: TESTING -> VALID (image_ok = True)
        - FAILURE: TESTING -> INVALID (rollback)
        
        Args:
            slot_id: Slot that was booted
            result: Boot attempt result
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            slot = self.slot_table.get_slot(slot_id)
            
            if result == BootAttemptResult.SUCCESS:
                # Boot succeeded - commit to VALID state
                slot.state = SlotState.VALID
                slot.image_status = ImageStatus.BOOT_SUCCESS
                slot.image_ok = True
                slot.booted_at = datetime.now()
                slot.boot_attempts += 1
                
                # Update active slot
                self.slot_table.active_slot = slot_id
                self.slot_table.pending_slot = None
                self.slot_table.boot_count += 1
                self.slot_table.last_boot_time = datetime.now()
                
                # Clear pending marker
                if self.probe:
                    marker_addr = self.slot_table_address - 32
                    # Write ACTIVE magic
                    marker = struct.pack(
                        "<IIII",
                        0x41435456,  # ACTV magic
                        ord(slot_id[0]) if slot_id else 0,
                        0,
                        int(datetime.now().timestamp()),
                    )
                    await self.probe.write_memory(marker_addr, marker)
                
                self._pending_boot = False
                
                # Update anti-rollback counter (P0-B critical)
                if self.anti_rollback:
                    await self.anti_rollback.increment_counter(slot.image_version)
                
                await self._save_slot_table()
                
                logger.info("boot_confirmed_success: slot=%s", slot_id)
                return True, "Boot confirmed"
            
            else:
                # Boot failed - rollback to INVALID
                slot.state = SlotState.INVALID
                slot.image_status = ImageStatus.BOOT_FAILED
                slot.image_ok = False
                slot.boot_attempts += 1
                
                self.slot_table.pending_slot = None
                self._pending_boot = False
                
                # Clear pending marker
                if self.probe:
                    marker_addr = self.slot_table_address - 32
                    marker = struct.pack("<IIII", 0, 0, 0, 0)
                    await self.probe.write_memory(marker_addr, marker)
                
                await self._save_slot_table()
                
                logger.warning("boot_confirmed_failure: slot=%s result=%s attempts=%s", slot_id, result.value, slot.boot_attempts)
                
                return False, f"Boot failed: {result.value}"
    
    async def mark_permanent(self, slot_id: str) -> tuple[bool, str]:
        """Mark slot as permanent (no rollback allowed).
        
        Args:
            slot_id: Slot to mark permanent
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            slot = self.slot_table.get_slot(slot_id)
            
            if slot.state != SlotState.VALID:
                return False, f"Cannot mark non-valid slot permanent: {slot.state.value}"
            
            if not slot.image_ok:
                return False, "Cannot mark unconfirmed image permanent"
            
            slot.state = SlotState.PERMANENT
            slot.confirmed_at = datetime.now()
            
            await self._save_slot_table()
            
            logger.info("slot_marked_permanent: slot=%s", slot_id)
            
            return True, "Marked permanent"
    
    async def revert_slot(self, slot_id: str) -> tuple[bool, str]:
        """Revert slot to INVALID state.
        
        Args:
            slot_id: Slot to revert
            
        Returns:
            (success, error_message)
        """
        async with self._lock:
            slot = self.slot_table.get_slot(slot_id)
            
            if slot.state == SlotState.PERMANENT:
                # Permanent slots require explicit force
                return False, "Cannot revert permanent slot without force"
            
            slot.state = SlotState.INVALID
            slot.image_status = ImageStatus.EMPTY
            slot.image_ok = False
            slot.boot_attempts = 0
            
            await self._save_slot_table()
            
            logger.info("slot_reverted: slot=%s", slot_id)
            
            return True, "Reverted"
    
    # =========================================================================
    # POWER-LOSS RECOVERY (P0-B)
    # =========================================================================
    
    async def recover_from_power_loss(self) -> tuple[bool, str]:
        """Recover state after power loss during flash/boot.
        
        Returns:
            (recovery_success, description)
        """
        async with self._lock:
            self._recovery_needed = False
            
            # Check each slot for partial state
            recovery_actions = []
            
            for slot_id in ["A", "B"]:
                slot = self.slot_table.get_slot(slot_id)
                
                if slot.image_status == ImageStatus.PARTIAL:
                    # Power loss during write - slot needs re-erase
                    recovery_actions.append({
                        "slot": slot_id,
                        "action": "re_erase",
                        "reason": "partial_write",
                    })
                    slot.image_status = ImageStatus.EMPTY
                    slot.state = SlotState.INVALID
                    
                elif slot.image_status == ImageStatus.WRITE_COMPLETE:
                    # Write complete but not verified - verify or re-erase
                    recovery_actions.append({
                        "slot": slot_id,
                        "action": "verify_or_reerase",
                        "reason": "write_complete_no_verify",
                    })
                    
                elif slot.image_status == ImageStatus.VERIFY_IN_PROGRESS:
                    # Verification interrupted - re-verify
                    recovery_actions.append({
                        "slot": slot_id,
                        "action": "re_verify",
                        "reason": "verify_interrupted",
                    })
            
            # Check pending boot
            if self._pending_boot:
                # Boot was interrupted - slot is still in TESTING
                if self.slot_table.pending_slot:
                    pending = self.slot_table.get_slot(self.slot_table.pending_slot)
                    
                    if pending.state == SlotState.TESTING:
                        recovery_actions.append({
                            "slot": self.slot_table.pending_slot,
                            "action": "require_manual_boot",
                            "reason": "pending_boot_interrupted",
                        })
            
            await self._save_slot_table()
            
            self._recovery_info = {
                "recovery_performed": True,
                "actions": recovery_actions,
            }
            
            logger.info("power_loss_recovery_complete: actions=%s", len(recovery_actions))
            
            return True, f"Recovery complete: {len(recovery_actions)} actions"
    
    async def get_state(self) -> dict[str, Any]:
        """Get current state of state machine."""
        return {
            "slot_table": self.slot_table.to_dict(),
            "pending_boot": self._pending_boot,
            "recovery_needed": self._recovery_needed,
            "recovery_info": self._recovery_info,
            "active_slot": self.slot_table.active_slot,
            "inactive_slot": "B" if self.slot_table.active_slot == "A" else "A",
        }
    
    async def can_flash(self) -> tuple[bool, str]:
        """Check if flash operation can proceed."""
        slot = self.slot_table.get_inactive_slot()
        
        if slot.state == SlotState.RESERVED:
            return False, "Slot is reserved"
        
        if slot.state == SlotState.PERMANENT:
            return False, "Slot is permanent (requires revert)"
        
        if slot.boot_attempts >= slot.max_boot_attempts:
            return False, f"Max boot attempts reached ({slot.max_boot_attempts})"
        
        if self._pending_boot:
            return False, "Pending boot in progress"
        
        return True, "Ready to flash"
    
    async def can_boot(self) -> tuple[bool, str]:
        """Check if boot operation can proceed."""
        if self._pending_boot:
            return True, "Pending boot available"
        
        active = self.slot_table.get_active_slot()
        
        if active.state == SlotState.VALID and active.image_ok:
            return True, "Active slot ready"
        
        inactive = self.slot_table.get_inactive_slot()
        
        if inactive.image_status == ImageStatus.VERIFY_PASSED:
            return True, "Inactive slot verified and ready"
        
        return False, "No bootable slot available"
