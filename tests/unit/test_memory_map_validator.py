"""Unit tests for Memory Map Validator."""

import pytest
from src.domain.hardware.flash.memory_map_validator import (
    ValidationResult,
    ELFSection,
    MemoryRegion,
    MemoryMapValidator,
    ProtectedRegionManager,
)


class TestValidationResult:
    """Tests for ValidationResult."""
    
    def test_valid_result(self):
        """Test valid result."""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
    
    def test_add_error(self):
        """Test adding errors."""
        result = ValidationResult(is_valid=True)
        result.add_error("Test error")
        
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "Test error" in result.errors[0]
    
    def test_add_warning(self):
        """Test adding warnings."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Test warning")
        
        assert result.is_valid  # Warnings don't invalidate
        assert len(result.warnings) == 1
    
    def test_to_dict(self):
        """Test serialization."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1"],
            warnings=["Warning 1"],
            overlaps=[("section1", "protected1")],
        )
        
        data = result.to_dict()
        
        assert data["is_valid"] is False
        assert "Error 1" in data["errors"]
        assert "Warning 1" in data["warnings"]


class TestELFSection:
    """Tests for ELFSection."""
    
    def test_creation(self):
        """Test section creation."""
        section = ELFSection(
            name=".text",
            address=0x08010000,
            size=0x5000,
            type="LOAD",
        )
        
        assert section.name == ".text"
        assert section.address == 0x08010000
        assert section.size == 0x5000
        assert section.end_address() == 0x08015000


class TestMemoryRegion:
    """Tests for MemoryRegion."""
    
    def test_creation(self):
        """Test region creation."""
        region = MemoryRegion(
            name="SRAM",
            base_address=0x20000000,
            size=0x20000,
            region_type="RAM",
        )
        
        assert region.base_address == 0x20000000
        assert region.size == 0x20000
        assert region.end_address() == 0x20020000
    
    def test_contains_address(self):
        """Test address containment."""
        region = MemoryRegion(
            name="Flash",
            base_address=0x08000000,
            size=0x100000,
        )
        
        assert region.contains_address(0x08000000)
        assert region.contains_address(0x0807FFFF)
        assert not region.contains_address(0x080FFFFF)
        assert not region.contains_address(0x07FFFFFF)


class TestMemoryMapValidator:
    """Tests for MemoryMapValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create validator."""
        return MemoryMapValidator()
    
    @pytest.mark.asyncio
    async def test_valid_firmware(self, validator):
        """Test validation of valid firmware."""
        sections = [
            ELFSection(name=".text", address=0x08010000, size=0x5000),
            ELFSection(name=".data", address=0x20000000, size=0x1000),
        ]
        
        memory_regions = [
            MemoryRegion(name="Flash", base_address=0x08000000, size=0x100000),
            MemoryRegion(name="SRAM", base_address=0x20000000, size=0x20000),
        ]
        
        protected = [
            create_partition("bootloader", 0x08000000, 0x10000, True),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=memory_regions,
            protected_regions=protected,
            target_partition_start=0x08000000,
            target_partition_size=0x100000,
        )
        
        # .text overlaps bootloader - should error
        assert not result.is_valid
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_no_overlap_protected(self, validator):
        """Test detection of protected region overlap."""
        sections = [
            ELFSection(name=".text", address=0x08010000, size=0x5000),
        ]
        
        memory_regions = [
            MemoryRegion(name="Flash", base_address=0x08000000, size=0x100000),
        ]
        
        protected = [
            create_partition("bootloader", 0x08000000, 0x10000, True),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=memory_regions,
            protected_regions=protected,
            target_partition_start=0x08000000,
            target_partition_size=0x100000,
        )
        
        # Should detect overlap
        assert not result.is_valid
        overlap_found = any("bootloader" in e for e in result.errors)
        assert overlap_found
    
    @pytest.mark.asyncio
    async def test_partition_overflow(self, validator):
        """Test detection of partition overflow."""
        sections = [
            ELFSection(name=".text", address=0x08010000, size=0xF0000),  # 0x08010000 + 0xF0000 = 0x09000000 > 0x08100000
        ]
        
        memory_regions = [
            MemoryRegion(name="Flash", base_address=0x08000000, size=0x100000),
        ]
        
        protected = []
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=memory_regions,
            protected_regions=protected,
            target_partition_start=0x08000000,
            target_partition_size=0x100000,  # Ends at 0x08100000
        )
        
        assert not result.is_valid
        overflow_found = any("exceeds partition" in e for e in result.errors)
        assert overflow_found


class TestProtectedRegionManager:
    """Tests for ProtectedRegionManager."""
    
    def test_add_protected_region(self):
        """Test adding protected region."""
        manager = ProtectedRegionManager()
        manager.add_protected_region(
            name="bootloader",
            start=0x08000000,
            size=0x10000,
        )
        
        assert len(manager.protected_regions) == 1
        assert manager.protected_regions[0].name == "bootloader"
    
    def test_is_address_protected(self):
        """Test protected address check."""
        manager = ProtectedRegionManager()
        manager.add_protected_region(
            name="boot",
            start=0x08000000,
            size=0x10000,
        )
        
        protected, name = manager.is_address_protected(0x08005000)
        assert protected
        assert name == "boot"
        
        protected, name = manager.is_address_protected(0x08010000)
        assert not protected
    
    def test_is_range_protected(self):
        """Test protected range check."""
        manager = ProtectedRegionManager()
        manager.add_protected_region(
            name="boot",
            start=0x08000000,
            size=0x10000,
        )
        
        # Range fully in protected
        is_prot, regions = manager.is_range_protected(0x08002000, 0x5000)
        assert is_prot
        assert "boot" in regions
        
        # Range partially overlaps
        is_prot, regions = manager.is_range_protected(0x08008000, 0x5000)
        assert not is_prot
    
    def test_check_flash_operation(self):
        """Test flash operation check."""
        manager = ProtectedRegionManager()
        manager.add_protected_region(
            name="option_bytes",
            start=0x1FFFF800,
            size=16,
        )
        
        allowed, msg = manager.check_flash_operation(0x1FFFF800, 16)
        assert not allowed
        assert "option_bytes" in msg
        
        allowed, msg = manager.check_flash_operation(0x08010000, 0x10000)
        assert allowed
    
    def test_from_config(self):
        """Test creating from config."""
        config = {
            "bootloader": {
                "start": 0x08000000,
                "size": 0x10000,
            },
            "otp": {
                "start": 0x1FFF7800,
                "size": 0x400,
            },
        }
        
        manager = ProtectedRegionManager.from_target_config(config, "STM32F4")
        
        assert len(manager.protected_regions) >= 2


def create_partition(name, start, size, is_protected):
    """Helper to create partition-like object."""
    from dataclasses import dataclass
    
    @dataclass
    class PartitionLike:
        name: str
        start_address: int
        size: int
        is_protected: bool
        
        @property
        def end_address(self):
            return self.start_address + self.size
        
        def contains_address(self, addr):
            return self.start_address <= addr < self.end_address
    
    return PartitionLike(
        name=name,
        start_address=start,
        size=size,
        is_protected=is_protected,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
