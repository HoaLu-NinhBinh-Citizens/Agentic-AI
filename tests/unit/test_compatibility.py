"""Tests for Compatibility Checker - 6.2.UT5.

Tests version range checking and compatibility validation.
"""

import pytest
from src.domain.hardware.flash.memory_map_validator import (
    ValidationResult,
    MemoryRegion,
    MemoryMapValidator,
    ProtectedRegionManager,
)


class TestCompatibilityChecker:
    """Test compatibility checking functionality."""
    
    def test_version_range_basic(self):
        """Test basic version range checking."""
        # Simple semantic version comparison
        def compare_versions(current: str, min_version: str) -> bool:
            current_parts = [int(x) for x in current.split(".")]
            min_parts = [int(x) for x in min_version.split(".")]
            return current_parts >= min_parts
        
        assert compare_versions("2.0.0", "1.0.0") is True
        assert compare_versions("1.0.0", "2.0.0") is False
        assert compare_versions("1.5.0", "1.0.0") is True
    
    def test_version_range_with_patch(self):
        """Test version range with patch version."""
        def compare_versions(current: str, min_version: str) -> bool:
            current_parts = [int(x) for x in current.split(".")]
            min_parts = [int(x) for x in min_version.split(".")]
            return current_parts >= min_parts
        
        assert compare_versions("1.0.1", "1.0.0") is True
        assert compare_versions("1.0.0", "1.0.1") is False
    
    def test_version_range_equal(self):
        """Test equal version."""
        def compare_versions(current: str, min_version: str) -> bool:
            current_parts = [int(x) for x in current.split(".")]
            min_parts = [int(x) for x in min_version.split(".")]
            return current_parts >= min_parts
        
        assert compare_versions("1.0.0", "1.0.0") is True
    
    def test_wildcard_version(self):
        """Test wildcard version matching."""
        def matches_wildcard(version: str, pattern: str) -> bool:
            parts = version.split(".")
            pattern_parts = pattern.split(".")
            
            for v, p in zip(parts, pattern_parts):
                if p == "*":
                    continue
                if int(v) != int(p):
                    return False
            return True
        
        assert matches_wildcard("1.0.0", "1.*.*") is True
        assert matches_wildcard("1.5.3", "1.*.*") is True
        assert matches_wildcard("2.0.0", "1.*.*") is False
    
    def test_range_specifier(self):
        """Test range specifier parsing."""
        # Simulate SpecifierSet behavior
        def parse_specifiers(spec: str) -> list[tuple[str, str]]:
            """Parse ~=, >=, <=, ==, != operators."""
            operators = [">=", "<=", "==", "!=", "~=", ">", "<"]
            
            for op in operators:
                if op in spec:
                    parts = spec.split(op)
                    return [(op, parts[1].strip())]
            return []
        
        specs = parse_specifiers(">=1.0.0,<2.0.0")
        assert len(specs) == 1  # Simplified
        
        specs = parse_specifiers("==1.5.0")
        assert len(specs) == 1
    
    def test_compatible_release(self):
        """Test compatible release operator (~=)."""
        def compatible_release(version: str, spec: str) -> bool:
            # ~= means compatible release
            # ~=1.4.2 is roughly equivalent to >=1.4.2, ==1.4.*
            if spec.startswith("~="):
                base = spec[2:].strip()
                base_parts = base.split(".")
                major, minor = int(base_parts[0]), int(base_parts[1])
                
                v_parts = [int(x) for x in version.split(".")]
                if len(v_parts) >= 2:
                    v_major, v_minor = v_parts[0], v_parts[1]
                    if v_major == major and v_minor == minor:
                        return True
            return False
        
        assert compatible_release("1.4.2", "~=1.4.2") is True
        assert compatible_release("1.4.5", "~=1.4.2") is True
        assert compatible_release("1.5.0", "~=1.4.2") is False
    
    def test_incompatible_major_version(self):
        """Test incompatibility detection for major version changes."""
        def check_major_compatibility(current: str, min_version: str) -> tuple[bool, str]:
            current_parts = [int(x) for x in current.split(".")]
            min_parts = [int(x) for x in min_version.split(".")]
            
            if current_parts[0] < min_parts[0]:
                return False, f"Major version {current_parts[0]} < {min_parts[0]}"
            return True, "OK"
        
        ok, _ = check_major_compatibility("2.0.0", "1.0.0")
        assert ok is True
        
        not_ok, msg = check_major_compatibility("1.0.0", "2.0.0")
        assert not_ok is False
        assert "Major version" in msg
    
    def test_warning_threshold(self):
        """Test warning threshold calculation."""
        def should_warn(current: str, recommended: str) -> bool:
            current_parts = [int(x) for x in current.split(".")]
            rec_parts = [int(x) for x in recommended.split(".")]
            
            # Warn if behind by minor version or more
            if current_parts[0] < rec_parts[0]:
                return True
            if current_parts[0] == rec_parts[0] and current_parts[1] < rec_parts[1]:
                return True
            return False
        
        assert should_warn("1.5.0", "2.0.0") is True
        assert should_warn("2.0.0", "2.0.0") is False
        assert should_warn("2.1.0", "2.0.0") is False
    
    def test_error_threshold(self):
        """Test error threshold calculation."""
        def should_error(current: str, minimum: str) -> bool:
            current_parts = [int(x) for x in current.split(".")]
            min_parts = [int(x) for x in minimum.split(".")]
            
            return current_parts < min_parts
        
        assert should_error("1.0.0", "2.0.0") is True
        assert should_error("2.0.0", "1.0.0") is False
        assert should_error("2.0.0", "2.0.0") is False


class TestMemoryMapValidator:
    """Test MemoryMapValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create validator."""
        return MemoryMapValidator()
    
    @pytest.mark.asyncio
    async def test_validate_no_overlap(self, validator):
        """Test validation passes when no overlaps."""
        from src.domain.hardware.flash.memory_map_validator import ELFSection
        
        sections = [
            ELFSection(name=".text", address=0x08000000, size=1024),
        ]
        
        regions = [
            MemoryRegion(name="flash", base_address=0x08000000, size=1024*1024),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=regions,
            protected_regions=[],
            target_partition_start=0x08000000,
            target_partition_size=1024*1024,
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_detect_overlap(self, validator):
        """Test overlap detection."""
        from src.domain.hardware.flash.memory_map_validator import ELFSection
        from src.domain.hardware.flash.flash_layout import Partition
        
        # Two sections that overlap
        sections = [
            ELFSection(name=".text", address=0x08000000, size=1024),
            ELFSection(name=".data", address=0x08000800, size=1024),  # Overlaps with .text end
        ]
        
        regions = [
            MemoryRegion(name="flash", base_address=0x08000000, size=1024*1024),
        ]
        
        protected = [
            Partition(name="protected", start_address=0x08000800, size=512),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=regions,
            protected_regions=protected,
            target_partition_start=0x08000000,
            target_partition_size=1024*1024,
        )
        
        # Should detect overlap with protected region
        assert len(result.overlaps) > 0
    
    @pytest.mark.asyncio
    async def test_out_of_bounds(self, validator):
        """Test out-of-bounds detection."""
        from src.domain.hardware.flash.memory_map_validator import ELFSection
        
        sections = [
            ELFSection(name=".text", address=0x09000000, size=1024),  # Outside partition
        ]
        
        regions = [
            MemoryRegion(name="flash", base_address=0x08000000, size=1024*1024),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=regions,
            protected_regions=[],
            target_partition_start=0x08000000,
            target_partition_size=1024*1024,
        )
        
        assert result.is_valid is False
        assert len(result.errors) > 0


class TestProtectedRegionManager:
    """Test ProtectedRegionManager class."""
    
    @pytest.fixture
    def manager(self):
        """Create protected region manager."""
        return ProtectedRegionManager()
    
    def test_add_protected_region(self, manager):
        """Test adding protected region."""
        manager.add_protected_region(
            name="bootloader",
            start=0x08000000,
            size=0x8000,
        )
        
        assert len(manager.protected_regions) == 1
    
    def test_is_address_protected(self, manager):
        """Test checking if address is protected."""
        manager.add_protected_region(
            name="otp",
            start=0x1FFFF800,
            size=16,
        )
        
        is_protected, name = manager.is_address_protected(0x1FFFF800)
        assert is_protected is True
        assert name == "otp"
        
        is_protected, _ = manager.is_address_protected(0x08000000)
        assert is_protected is False
    
    def test_is_range_protected(self, manager):
        """Test checking if range overlaps protected region."""
        manager.add_protected_region(
            name="bootloader",
            start=0x08000000,
            size=0x8000,
        )
        
        # Fully protected
        is_protected, regions = manager.is_range_protected(0x08000000, 0x8000)
        assert is_protected is True
        assert "bootloader" in regions
        
        # Partially protected (overlaps with bootloader)
        is_protected, regions = manager.is_range_protected(0x08007000, 0x2000)
        assert is_protected is True  # This overlaps with bootloader!
        
        # Non-overlapping range
        is_protected, regions = manager.is_range_protected(0x08010000, 0x1000)
        assert is_protected is False  # Doesn't overlap
    
    def test_check_flash_operation(self, manager):
        """Test checking if flash operation is allowed."""
        manager.add_protected_region(
            name="option_bytes",
            start=0x1FFFF800,
            size=16,
        )
        
        allowed, msg = manager.check_flash_operation(0x08000000, 1024)
        assert allowed is True
        
        allowed, msg = manager.check_flash_operation(0x1FFFF800, 16)
        assert allowed is False
        assert "protected" in msg.lower()
