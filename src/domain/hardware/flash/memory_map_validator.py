"""Memory Map Validator - Validate firmware against target memory map.

Phase 6.2: Implements validation for:
- Section overlap detection
- Protected region checking
- Bootloader protection
- Memory region validation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of memory map validation."""
    
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "overlaps": [
                {"section": o[0], "region": o[1]}
                for o in self.overlaps
            ],
        }
    
    def add_error(self, message: str) -> None:
        """Add error message."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str) -> None:
        """Add warning message."""
        self.warnings.append(message)


@dataclass
class ELFSection:
    """ELF section information."""
    
    name: str
    address: int
    size: int
    type: str = "LOAD"
    
    def end_address(self) -> int:
        """Get end address."""
        return self.address + self.size


@dataclass
class MemoryRegion:
    """Memory region definition."""
    
    name: str
    base_address: int
    size: int
    region_type: str = "RAM"
    
    readable: bool = True
    writable: bool = True
    executable: bool = True
    
    def end_address(self) -> int:
        """Get end address."""
        return self.base_address + self.size
    
    def contains_address(self, addr: int) -> bool:
        """Check if address is in region."""
        return self.base_address <= addr < self.end_address()


@dataclass
class MemoryMapValidator:
    """Validates firmware against target memory map.
    
    Checks:
    - No overlap with protected regions
    - Sections within valid memory regions
    - No overflow beyond partition boundaries
    """
    
    async def validate(
        self,
        elf_sections: list[ELFSection],
        target_memory_regions: list[MemoryRegion],
        protected_regions: list[Any],  # Partition list
        target_partition_start: int,
        target_partition_size: int,
    ) -> ValidationResult:
        """Validate firmware memory map.
        
        Args:
            elf_sections: Sections from ELF file
            target_memory_regions: Valid memory regions
            protected_regions: Protected regions (bootloader, etc.)
            target_partition_start: Start of target partition
            target_partition_size: Size of target partition
        
        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)
        partition_end = target_partition_start + target_partition_size
        
        for section in elf_sections:
            section_end = section.address + section.size
            
            # Check within partition bounds
            if section.address < target_partition_start:
                result.add_error(
                    f"Section {section.name}: address {hex(section.address)} "
                    f"before partition start {hex(target_partition_start)}"
                )
            
            if section_end > partition_end:
                result.add_error(
                    f"Section {section.name}: end {hex(section_end)} "
                    f"exceeds partition end {hex(partition_end)}"
                )
            
            # Check protected regions
            for protected in protected_regions:
                protected_start = getattr(protected, 'start_address', 0)
                protected_end = protected_start + protected.size
                
                if section.address < protected_end and section_end > protected_start:
                    result.add_error(
                        f"Section {section.name}: overlaps protected region {protected.name} "
                        f"({hex(protected_start)}-{hex(protected_end)})"
                    )
                    result.overlaps.append((section.name, protected.name))
            
            # Check within valid memory (for LOAD sections)
            if section.type == "LOAD":
                in_valid_region = any(
                    r.contains_address(section.address)
                    for r in target_memory_regions
                )
                if not in_valid_region:
                    result.warnings.append(
                        f"Section {section.name}: address {hex(section.address)} "
                        "not in known memory regions"
                    )
        
        return result
    
    async def validate_from_elf(
        self,
        elf_path: str,
        target_memory_regions: list[MemoryRegion],
        protected_regions: list[Any],
        target_partition_start: int,
        target_partition_size: int,
    ) -> ValidationResult:
        """Validate ELF file directly."""
        try:
            from elftools.elf.elffile import ELFFile
        except ImportError:
            logger.error("pyelftools_not_installed")
            return ValidationResult(is_valid=False, errors=["pyelftools not installed"])
        
        sections = []
        
        try:
            with open(elf_path, "rb") as f:
                elf = ELFFile(f)
                
                for section in elf.iter_sections():
                    if section["sh_type"] == "SHT_LOAD":
                        sections.append(ELFSection(
                            name=section.name,
                            address=section["sh_addr"],
                            size=section["sh_size"],
                            type="LOAD",
                        ))
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Failed to parse ELF: {e}"],
            )
        
        return await self.validate(
            sections,
            target_memory_regions,
            protected_regions,
            target_partition_start,
            target_partition_size,
        )


@dataclass
class ProtectedRegionManager:
    """Manages protected flash regions.
    
    Prevents accidental writes to:
    - Bootloader
    - OTP/eFuse
    - Option bytes
    - Secure boot signatures
    """
    
    protected_regions: list[Any] = field(default_factory=list)  # Partition list
    
    def add_protected_region(
        self,
        name: str,
        start: int,
        size: int,
        reason: str = "",
    ) -> None:
        """Add a protected region."""
        from .flash_layout import Partition
        
        self.protected_regions.append(Partition(
            name=name,
            start_address=start,
            size=size,
            is_protected=True,
        ))
        
        logger.info("protected_region_added", name=name, start=hex(start), size=hex(size))
    
    def is_address_protected(self, address: int) -> tuple[bool, str]:
        """Check if address is in protected region.
        
        Returns:
            (is_protected, region_name)
        """
        for region in self.protected_regions:
            if region.contains_address(address):
                return True, region.name
        return False, ""
    
    def is_range_protected(self, start: int, size: int) -> tuple[bool, list[str]]:
        """Check if address range is protected.
        
        Returns:
            (is_protected, list of protected region names)
        """
        protected = []
        end = start + size
        
        for region in self.protected_regions:
            region_end = region.start_address + region.size
            if start < region_end and end > region.start_address:
                protected.append(region.name)
        
        return len(protected) > 0, protected
    
    def check_flash_operation(
        self,
        address: int,
        size: int,
    ) -> tuple[bool, str]:
        """Check if flash operation is allowed.
        
        Returns:
            (allowed, error_message)
        """
        is_protected, region_name = self.is_range_protected(address, size)
        
        if is_protected:
            return False, f"Flash operation blocked: overlaps protected region '{region_name}'"
        
        return True, ""
    
    def check_erase_sectors(
        self,
        sector_starts: list[int],
        sector_size: int,
    ) -> tuple[bool, list[str], list[str]]:
        """Check if sector erase is allowed.
        
        Returns:
            (all_allowed, blocked_sectors, warnings)
        """
        blocked = []
        warnings = []
        
        for sector_start in sector_starts:
            is_protected, region_name = self.is_range_protected(sector_start, sector_size)
            
            if is_protected:
                blocked.append(f"sector at {hex(sector_start)} (protected by {region_name})")
            else:
                # Check if sector overlaps protected region
                for region in self.protected_regions:
                    region_end = region.start_address + region.size
                    sector_end = sector_start + sector_size
                    
                    if sector_start < region_end and sector_end > region.start_address:
                        overlap_start = max(sector_start, region.start_address)
                        overlap_end = min(sector_end, region_end)
                        warnings.append(
                            f"sector at {hex(sector_start)} partially overlaps {region.name} "
                            f"({hex(overlap_start)}-{hex(overlap_end)})"
                        )
        
        return len(blocked) == 0, blocked, warnings
    
    @classmethod
    def from_target_config(
        cls,
        config: dict[str, Any],
        chip_family: str,
    ) -> ProtectedRegionManager:
        """Create from target configuration."""
        manager = cls()
        
        # Add bootloader
        if "bootloader" in config:
            manager.add_protected_region(
                name="bootloader",
                start=config["bootloader"]["start"],
                size=config["bootloader"]["size"],
                reason="Bootloader must not be overwritten",
            )
        
        # Add OTP/eFuse if present
        if "otp" in config:
            manager.add_protected_region(
                name="otp",
                start=config["otp"]["start"],
                size=config["otp"]["size"],
                reason="One-time programmable memory",
            )
        
        # Chip-specific defaults
        if chip_family.startswith("STM32"):
            manager.add_protected_region(
                name="option_bytes",
                start=0x1FFFF800,
                size=16,
                reason="STM32 option bytes",
            )
        
        return manager
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "regions": [
                {
                    "name": r.name,
                    "start": hex(r.start_address),
                    "size": hex(r.size),
                }
                for r in self.protected_regions
            ],
        }
