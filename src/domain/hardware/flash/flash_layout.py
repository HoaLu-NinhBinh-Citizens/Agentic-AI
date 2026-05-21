"""Flash Layout - A/B Firmware Layout awareness for OTA updates.

Phase 6.2: Implements A/B layout detection and slot selection for:
- Dual-bank flash (STM32)
- Partition table (ESP32)
- MCUboot
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LayoutType(Enum):
    """Flash layout types."""
    
    SINGLE = "single"           # Single bank, no redundancy
    DUAL_BANK = "dual_bank"     # Two equal banks (A/B)
    PARTITION_TABLE = "partition_table"  # ESP32-style partitions


@dataclass
class Partition:
    """Represents a flash partition/slot."""
    
    name: str
    start_address: int
    size: int
    
    # Flags
    is_bootable: bool = False
    is_protected: bool = False
    is_read_only: bool = False
    
    # For A/B slots
    slot_id: str | None = None  # "A" or "B" for dual-bank
    
    # Metadata
    filesystem_type: str | None = None  # "app", "ota", "spiffs", etc.
    version: str | None = None
    
    @property
    def end_address(self) -> int:
        """Get end address (exclusive)."""
        return self.start_address + self.size
    
    def contains_address(self, addr: int) -> bool:
        """Check if address is within partition."""
        return self.start_address <= addr < self.end_address
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "start_address": hex(self.start_address),
            "size": hex(self.size),
            "end_address": hex(self.end_address),
            "is_bootable": self.is_bootable,
            "is_protected": self.is_protected,
            "slot_id": self.slot_id,
        }


@dataclass
class FlashLayout:
    """Complete flash layout for a target.
    
    Describes partitions, slots, and metadata for firmware placement.
    """
    
    layout_id: str = ""
    layout_type: LayoutType = LayoutType.SINGLE
    target_id: str = ""
    
    # Partitions
    partitions: list[Partition] = field(default_factory=list)
    
    # A/B specific
    active_slot: str | None = None  # "A" or "B"
    inactive_slot: str | None = None
    slot_selector_address: int | None = None
    
    # Bootloader area
    bootloader_start: int | None = None
    bootloader_size: int = 0
    
    # Config storage
    config_start: int | None = None
    config_size: int = 0
    
    # Metadata
    flash_size: int = 0
    sector_size: int = 2048  # Default for STM32
    page_size: int = 2048
    
    def get_partition(self, name: str) -> Partition | None:
        """Get partition by name."""
        for p in self.partitions:
            if p.name == name:
                return p
        return None
    
    def get_active_partition(self) -> Partition | None:
        """Get currently active application partition."""
        if self.active_slot:
            for p in self.partitions:
                if p.slot_id == self.active_slot:
                    return p
        return None
    
    def get_inactive_partition(self) -> Partition | None:
        """Get inactive partition suitable for flashing."""
        if self.inactive_slot:
            for p in self.partitions:
                if p.slot_id == self.inactive_slot:
                    return p
        return None
    
    def get_boot_partition(self) -> Partition | None:
        """Get bootable partition (active or fallback)."""
        for p in self.partitions:
            if p.is_bootable:
                return p
        return self.get_active_partition()
    
    def validate_address(self, addr: int, size: int) -> tuple[bool, str]:
        """Validate if address range is valid.
        
        Returns:
            (is_valid, error_message)
        """
        end_addr = addr + size
        
        # Check within flash bounds
        if addr < 0 or end_addr > self.flash_size:
            return False, f"Address range outside flash bounds"
        
        # Check overlap with protected regions
        for p in self.partitions:
            if p.is_protected:
                if addr < p.end_address and end_addr > p.start_address:
                    return False, f"Overlaps protected partition: {p.name}"
        
        return True, ""
    
    def get_slot_for_address(self, addr: int) -> str | None:
        """Get slot ID for an address."""
        for p in self.partitions:
            if p.contains_address(addr) and p.slot_id:
                return p.slot_id
        return None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> FlashLayout:
        """Create layout from configuration dict."""
        layout = cls()
        
        layout.layout_id = config.get("id", "")
        layout.flash_size = config.get("flash_size", 0x100000)
        layout.sector_size = config.get("sector_size", 2048)
        
        layout_type = config.get("type", "single")
        if layout_type == "dual_bank":
            layout.layout_type = LayoutType.DUAL_BANK
        elif layout_type == "partition_table":
            layout.layout_type = LayoutType.PARTITION_TABLE
        
        # Parse partitions
        for part_config in config.get("partitions", []):
            partition = Partition(
                name=part_config["name"],
                start_address=part_config["start"],
                size=part_config["size"],
                is_bootable=part_config.get("bootable", False),
                is_protected=part_config.get("protected", False),
                slot_id=part_config.get("slot"),
            )
            layout.partitions.append(partition)
        
        # A/B specific
        if "active_slot" in config:
            layout.active_slot = config["active_slot"]
            layout.slot_selector_address = config.get("slot_selector_address")
        
        # Bootloader
        if "bootloader" in config:
            layout.bootloader_start = config["bootloader"]["start"]
            layout.bootloader_size = config["bootloader"]["size"]
        
        return layout
    
    @classmethod
    def create_stm32_dual_bank(cls, flash_size: int = 0x100000) -> FlashLayout:
        """Create STM32 dual-bank layout."""
        layout = cls()
        layout.layout_type = LayoutType.DUAL_BANK
        layout.flash_size = flash_size
        layout.sector_size = 2048
        
        half = flash_size // 2
        
        # Bank A
        layout.partitions.append(Partition(
            name="bank_a",
            start_address=0x08000000,
            size=half,
            is_bootable=True,
            slot_id="A",
        ))
        
        # Bank B
        layout.partitions.append(Partition(
            name="bank_b",
            start_address=0x08000000 + half,
            size=half,
            is_bootable=True,
            slot_id="B",
        ))
        
        # Slot selector at end of flash
        layout.slot_selector_address = 0x08000000 + flash_size - 4
        layout.active_slot = "A"
        layout.inactive_slot = "B"
        
        return layout
    
    @classmethod
    def create_esp32_partition_table(cls) -> FlashLayout:
        """Create ESP32 partition table layout."""
        layout = cls()
        layout.layout_type = LayoutType.PARTITION_TABLE
        layout.flash_size = 0x400000  # 4MB
        layout.sector_size = 4096
        
        # Bootloader
        layout.partitions.append(Partition(
            name="bootloader",
            start_address=0x1000,
            size=0x6000,
            is_protected=True,
        ))
        
        # Partition table
        layout.partitions.append(Partition(
            name="partition_table",
            start_address=0x8000,
            size=0x1000,
            is_protected=True,
        ))
        
        # App A (ota_0)
        layout.partitions.append(Partition(
            name="app_a",
            start_address=0x10000,
            size=0x180000,
            is_bootable=True,
            slot_id="A",
            filesystem_type="ota",
        ))
        
        # App B (ota_1)
        layout.partitions.append(Partition(
            name="app_b",
            start_address=0x190000,
            size=0x180000,
            is_bootable=True,
            slot_id="B",
            filesystem_type="ota",
        ))
        
        # SPIFFS
        layout.partitions.append(Partition(
            name="spiffs",
            start_address=0x310000,
            size=0xEF000,
            filesystem_type="spiffs",
        ))
        
        # Otadata
        layout.partitions.append(Partition(
            name="otadata",
            start_address=0x1FB000,
            size=0x2000,
            is_protected=True,
        ))
        
        # NVS
        layout.partitions.append(Partition(
            name="nvs",
            start_address=0x1FD000,
            size=0x3000,
        ))
        
        return layout
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "layout_id": self.layout_id,
            "layout_type": self.layout_type.value,
            "target_id": self.target_id,
            "partitions": [p.to_dict() for p in self.partitions],
            "active_slot": self.active_slot,
            "inactive_slot": self.inactive_slot,
            "slot_selector_address": hex(self.slot_selector_address) if self.slot_selector_address else None,
            "flash_size": hex(self.flash_size),
            "sector_size": self.sector_size,
        }


class ActiveSlotDetector:
    """Detects active slot in A/B firmware layout.
    
    Supports multiple mechanisms:
    - ESP32 otadata
    - STM32 dual-bank
    - MCUboot
    - Custom slot selector
    """
    
    async def detect(
        self,
        probe: Any,  # ProbeInterface
        layout: FlashLayout,
    ) -> str | None:
        """Detect active slot.
        
        Returns:
            Slot ID ("A" or "B") or None for single layout
        """
        if layout.layout_type == LayoutType.SINGLE:
            return None
        
        if layout.layout_type == LayoutType.DUAL_BANK:
            return await self._detect_dual_bank(probe, layout)
        
        if layout.layout_type == LayoutType.PARTITION_TABLE:
            return await self._detect_partition_table(probe, layout)
        
        return None
    
    async def _detect_dual_bank(
        self,
        probe: Any,
        layout: FlashLayout,
    ) -> str | None:
        """Detect active slot in dual-bank layout using slot selector."""
        if layout.slot_selector_address:
            try:
                data = await probe.read_memory(
                    layout.slot_selector_address,
                    4,
                )
                if len(data) == 4:
                    selector = struct.unpack("<I", data)[0]
                    slot = "B" if selector != 0xFFFFFFFF else "A"
                    return slot
            except Exception:
                pass
        
        return await self._detect_by_bootprobe(probe, layout)
    
    async def _detect_partition_table(
        self,
        probe: Any,
        layout: FlashLayout,
    ) -> str | None:
        """Detect active slot in ESP32 partition table."""
        # ESP32 uses otadata at 0x1FB000
        otadata_addr = 0x1FB000
        
        try:
            data = await probe.read_memory(otadata_addr, 32)
            if len(data) >= 16:
                seq_a = struct.unpack("<I", data[8:12])[0]
                seq_b = struct.unpack("<I", data[24:28])[0]
                
                if seq_a == 0xFFFFFFFF and seq_b == 0xFFFFFFFF:
                    return "A"  # Default
                
                return "A" if seq_a > seq_b else "B"
        except Exception:
            pass
        
        return "A"
    
    async def _detect_by_bootprobe(
        self,
        probe: Any,
        layout: FlashLayout,
    ) -> str | None:
        """Detect active slot by probing boot markers."""
        slot_a = layout.get_partition("app_a") or layout.get_partition("bank_a")
        slot_b = layout.get_partition("app_b") or layout.get_partition("bank_b")
        
        if not slot_a or not slot_b:
            return None
        
        for slot, partition in [("A", slot_a), ("B", slot_b)]:
            try:
                data = await probe.read_memory(partition.start_address, 8)
                if len(data) == 8:
                    initial_sp = struct.unpack("<I", data[0:4])[0]
                    initial_pc = struct.unpack("<I", data[4:8])[0]
                    
                    if 0x20000000 <= initial_sp < 0x20040000:
                        if partition.start_address <= initial_pc < partition.end_address:
                            return slot
            except Exception:
                continue
        
        return "A"


class SlotSelector:
    """Selects appropriate slot for firmware flash.
    
    Implements policies:
    - For A/B: Always flash to inactive slot
    - For single: Flash with backup
    - For rollback: Return to previous slot
    """
    
    def __init__(self, layout: FlashLayout) -> None:
        self.layout = layout
    
    def get_flash_target_slot(self) -> Partition | None:
        """Get target partition for flashing.
        
        For A/B: Returns inactive slot.
        For single: Returns main partition.
        """
        if self.layout.layout_type == LayoutType.SINGLE:
            return self.layout.get_boot_partition()
        
        return self.layout.get_inactive_partition()
    
    def get_rollback_slot(self) -> Partition | None:
        """Get partition to restore on rollback."""
        if self.layout.layout_type == LayoutType.SINGLE:
            return None
        
        return self.layout.get_active_partition()
    
    async def switch_active_slot(
        self,
        probe: Any,
        new_slot: str,
    ) -> bool:
        """Switch active slot in bootloader/ota data.
        
        Args:
            probe: Probe interface
            new_slot: Slot ID ("A" or "B")
        
        Returns:
            True if successful
        """
        if self.layout.layout_type == LayoutType.SINGLE:
            return True
        
        if self.layout.slot_selector_address:
            value = 0 if new_slot == "A" else 1
            data = struct.pack("<I", value)
            await probe.write_memory(self.layout.slot_selector_address, data)
            
            self.layout.active_slot = new_slot
            self.layout.inactive_slot = "A" if new_slot == "B" else "B"
            return True
        
        if self.layout.layout_type == LayoutType.PARTITION_TABLE:
            return await self._write_otadata(probe, new_slot)
        
        return False
    
    async def _write_otadata(self, probe: Any, new_slot: str) -> bool:
        """Write otadata for ESP32 slot switch."""
        # Write to both slots, higher sequence wins
        slot_a_addr = 0x1FB000
        slot_b_addr = 0x1FB010
        
        try:
            # Read current sequences
            data_a = await probe.read_memory(slot_a_addr, 4)
            data_b = await probe.read_memory(slot_b_addr, 4)
            
            seq_a = struct.unpack("<I", data_a)[0]
            seq_b = struct.unpack("<I", data_b)[0]
            
            max_seq = max(seq_a, seq_b)
            new_seq = max_seq + 1
            
            if new_slot == "A":
                await probe.write_memory(slot_a_addr, struct.pack("<I", new_seq))
            else:
                await probe.write_memory(slot_b_addr, struct.pack("<I", new_seq))
            
            self.layout.active_slot = new_slot
            self.layout.inactive_slot = "A" if new_slot == "B" else "B"
            return True
            
        except Exception:
            return False
    
    def estimate_flash_time(
        self,
        firmware_size: int,
        target_partition: Partition,
    ) -> dict[str, float]:
        """Estimate flash time in seconds.
        
        Returns:
            Dict with erase_time, write_time, verify_time
        """
        erase_speed_kb_per_sec = 50
        write_speed_kb_per_sec = 100
        verify_speed_kb_per_sec = 200
        
        size_kb = firmware_size / 1024
        
        return {
            "erase_time": size_kb / erase_speed_kb_per_sec,
            "write_time": size_kb / write_speed_kb_per_sec,
            "verify_time": size_kb / verify_speed_kb_per_sec,
        }
