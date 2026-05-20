"""Unit tests for Phase 6 - Embedded Target models."""

import pytest
from datetime import datetime

from src.domain.hardware.embedded_target import (
    EmbeddedTarget,
    TargetState,
    ChipFamily,
    CoreType,
    DebugProbeType,
    DebugInterface,
    ResetMode,
    Toolchain,
    BreakpointType,
    FaultType,
    FirmwareVersion,
    IDCODE,
    MemoryRegion,
    ChipDescription,
    DebugProbeConfig,
    SerialConfig,
    ToolchainConfig,
    FirmwareInfo,
    TargetConfig,
    GDBFrame,
    GDBBreakpoint,
    StackFrame,
    CrashInfo,
    CompatibilityResult,
)


class TestIDCODE:
    """Tests for IDCODE parsing."""
    
    def test_idcode_from_int_stm32(self):
        """Test IDCODE parsing for STM32."""
        # STM32F4 IDCODE: 0x2BA01477
        value = 0x2BA01477
        idcode = IDCODE.from_int(value)
        
        # manufacturer_id = (value >> 1) & 0x7FF
        expected_manufacturer = (value >> 1) & 0x7FF
        assert idcode.manufacturer_id == expected_manufacturer
        assert idcode.device_id == value
        # full_code returns canonical format: (manufacturer_id << 1) | 1
        assert idcode.full_code == (expected_manufacturer << 1) | 1
    
    def test_idcode_from_int_generic(self):
        """Test generic IDCODE parsing."""
        value = 0x06410041
        idcode = IDCODE.from_int(value)
        
        # manufacturer_id = (value >> 1) & 0x7FF
        expected_manufacturer = (value >> 1) & 0x7FF
        assert idcode.manufacturer_id == expected_manufacturer
        assert idcode.revision == (value >> 28) & 0xF


class TestTargetStateMachine:
    """Tests for EmbeddedTarget state machine."""
    
    def test_initial_state(self):
        """Test initial target state."""
        target = EmbeddedTarget(
            id="test-1",
            name="Test Target",
            chip_family=ChipFamily.STM32F4,
        )
        
        assert target.state == TargetState.UNKNOWN
        assert not target.is_connected()
    
    def test_valid_transition(self):
        """Test valid state transition."""
        target = EmbeddedTarget(
            id="test-1",
            name="Test Target",
            chip_family=ChipFamily.STM32F4,
        )
        
        assert target.transition(TargetState.CONNECTED)
        assert target.state == TargetState.CONNECTED
    
    def test_invalid_transition(self):
        """Test invalid state transition."""
        target = EmbeddedTarget(
            id="test-1",
            name="Test Target",
            chip_family=ChipFamily.STM32F4,
        )
        
        # Cannot go directly from UNKNOWN to HALTED
        assert not target.transition(TargetState.HALTED)
        assert target.state == TargetState.UNKNOWN
    
    def test_halted_to_running(self):
        """Test HALTED to RUNNING transition."""
        target = EmbeddedTarget(
            id="test-1",
            name="Test Target",
            chip_family=ChipFamily.STM32F4,
            state=TargetState.HALTED,
        )
        
        assert target.transition(TargetState.RUNNING)
        assert target.state == TargetState.RUNNING
    
    def test_can_debug_states(self):
        """Test can_debug() method."""
        target = EmbeddedTarget(
            id="test-1",
            name="Test Target",
            chip_family=ChipFamily.STM32F4,
        )
        
        # Cannot debug when not connected
        assert not target.can_debug()
        
        target.transition(TargetState.CONNECTED)
        assert target.can_debug()
        
        target.transition(TargetState.HALTED)
        assert target.can_debug()
        
        target.transition(TargetState.RUNNING)
        assert not target.can_debug()


class TestFirmwareVersion:
    """Tests for FirmwareVersion."""
    
    def test_version_hash(self):
        """Test version hash generation."""
        version = FirmwareVersion(
            version="1.2.3",
            git_hash="abc1234",
        )
        
        # Same inputs should produce same hash
        version2 = FirmwareVersion(
            version="1.2.3",
            git_hash="abc1234",
        )
        assert version.version_hash == version2.version_hash
        
        # Different inputs should produce different hash
        version3 = FirmwareVersion(
            version="1.2.4",
            git_hash="abc1234",
        )
        assert version.version_hash != version3.version_hash
    
    def test_semver_tuple(self):
        """Test semantic version parsing."""
        version = FirmwareVersion(
            version="v1.2.3",
            git_hash="abc",
        )
        
        assert version.semver_tuple == (1, 2, 3, 0, 0)
    
    def test_semver_tuple_short(self):
        """Test semantic version with missing parts."""
        version = FirmwareVersion(
            version="1",
            git_hash="abc",
        )
        
        # Version "1" becomes (1, 0, 0) - only 3 elements
        assert version.semver_tuple == (1, 0, 0)


class TestChipDescription:
    """Tests for ChipDescription."""
    
    def test_flash_region(self):
        """Test getting flash region."""
        chip = ChipDescription(
            family=ChipFamily.STM32F4,
            part_number="STM32F407VGT6",
            core=CoreType.CORTEX_M4,
            memory_regions=[
                MemoryRegion(name="FLASH", base_address=0x08000000, size=0x100000),
                MemoryRegion(name="SRAM1", base_address=0x20000000, size=0x20000),
            ],
        )
        
        flash = chip.flash_region
        assert flash is not None
        assert flash.base_address == 0x08000000
        assert flash.size == 0x100000
    
    def test_sram_regions(self):
        """Test getting SRAM regions."""
        chip = ChipDescription(
            family=ChipFamily.STM32F4,
            part_number="STM32F407VGT6",
            core=CoreType.CORTEX_M4,
            memory_regions=[
                MemoryRegion(name="FLASH", base_address=0x08000000, size=0x100000, region_type="FLASH"),
                MemoryRegion(name="SRAM1", base_address=0x20000000, size=0x20000, region_type="RAM"),
                MemoryRegion(name="SRAM2", base_address=0x20020000, size=0x10000, region_type="SRAM"),
            ],
        )
        
        sram_regions = chip.sram_regions
        assert len(sram_regions) == 2
        assert chip.total_sram_size == 0x30000  # 0x20000 + 0x10000


class TestCrashInfo:
    """Tests for CrashInfo."""
    
    def test_is_hard_fault(self):
        """Test hard fault detection."""
        crash = CrashInfo(
            fault_type=FaultType.HARD_FAULT,
            fault_address=0x08001000,
            pc=0x08000500,
            sp=0x20010000,
            lr=0x08000504,
            xPSR=0x61000000,
            registers={},
            stack_trace=[],
        )
        
        assert crash.is_hard_fault
        assert not crash.is_stack_overflow
    
    def test_is_stack_overflow(self):
        """Test stack overflow detection."""
        crash = CrashInfo(
            fault_type=FaultType.STACK_OVERFLOW,
            fault_address=0x2001FFF8,
            pc=0x08000500,
            sp=0x2001FF00,
            lr=0x08000504,
            xPSR=0x61000000,
            registers={},
            stack_trace=[],
        )
        
        assert crash.is_stack_overflow


class TestChipFamilies:
    """Tests for ChipFamily enum."""
    
    def test_stm32_families(self):
        """Test STM32 families."""
        assert ChipFamily.STM32F4.value == "STM32F4"
        assert ChipFamily.STM32H7.value == "STM32H7"
    
    def test_riscv_families(self):
        """Test RISC-V families."""
        assert ChipFamily.ESPRESSIF_ESP32.value == "ESP32"
        assert ChipFamily.RISCV_GENERIC.value == "RISCV"
    
    def test_unknown_family(self):
        """Test unknown family."""
        assert ChipFamily.UNKNOWN.value == "UNKNOWN"


class TestDebugProbeConfig:
    """Tests for DebugProbeConfig."""
    
    def test_default_probe_config(self):
        """Test default probe config."""
        config = DebugProbeConfig(
            probe_type=DebugProbeType.STLINK,
        )
        
        assert config.interface == DebugInterface.SWD
        assert config.speed_khz == 4000
        assert config.serial is None
    
    def test_jlink_config(self):
        """Test JLink probe config."""
        config = DebugProbeConfig(
            probe_type=DebugProbeType.JLINK,
            interface=DebugInterface.JTAG,
            speed_khz=8000,
            serial="12345678",
        )
        
        assert config.probe_type == DebugProbeType.JLINK
        assert config.interface == DebugInterface.JTAG
        assert config.speed_khz == 8000


class TestTargetConfig:
    """Tests for TargetConfig."""
    
    def test_target_config_to_dict(self):
        """Test TargetConfig serialization."""
        chip = ChipDescription(
            family=ChipFamily.STM32F4,
            part_number="STM32F407VGT6",
            core=CoreType.CORTEX_M4,
        )
        
        config = TargetConfig(
            id="test-target",
            name="Test Target",
            chip=chip,
            debug_probe=DebugProbeConfig(probe_type=DebugProbeType.JLINK),
            toolchain=ToolchainConfig(name=Toolchain.GCC_ARM),
        )
        
        result = config.to_dict()
        
        assert result["id"] == "test-target"
        assert result["name"] == "Test Target"
        assert result["chip"]["family"] == "STM32F4"
        assert result["debug_probe"]["type"] == "JLINK"


class TestCompatibilityResult:
    """Tests for CompatibilityResult."""
    
    def test_compatible_result(self):
        """Test compatible result."""
        result = CompatibilityResult(
            compatible=True,
            warnings=["Minor version difference"],
        )
        
        assert result.compatible
        assert len(result.warnings) == 1
    
    def test_incompatible_result(self):
        """Test incompatible result."""
        result = CompatibilityResult(
            compatible=False,
            errors=["Incompatible chip family"],
        )
        
        assert not result.compatible
        assert len(result.errors) == 1
