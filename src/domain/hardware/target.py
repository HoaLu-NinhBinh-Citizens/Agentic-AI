"""Extended target models for Phase 6.1.

This module defines comprehensive target models including:
- Chip with revision, stepping, temperature range, multi-core support
- Core definition with frequency and core_id
- Board abstraction
- Memory regions with detailed attributes
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from .embedded_target import ChipFamily, CoreType, IDCODE, MemoryRegion


class TemperatureRange(Enum):
    """Operating temperature ranges for chips."""

    COMMERCIAL = auto()  # 0°C to 70°C
    INDUSTRIAL = auto()  # -40°C to 85°C
    AUTOMOTIVE = auto()  # -40°C to 125°C
    EXTENDED = auto()  # -55°C to 125°C
    MILITARY = auto()  # -55°C to 125°C ( stricter tolerances)
    HIGH_TEMP = auto()  # -40°C to 105°C


class PackageType(Enum):
    """Chip package types."""

    LQFP = auto()
    QFN = auto()
    BGA = auto()
    WLCSP = auto()
    TSSOP = auto()
    LGA = auto()
    QFP = auto()
    PLCC = auto()


@dataclass
class Core:
    """Individual core definition in a multi-core chip.

    Attributes:
        name: Core identifier (e.g., "CPU0", "CPU1", "DSP")
        core_type: Type of core (ARM core type)
        frequency_hz: Operating frequency in Hz
        core_id: Unique identifier for this core (for multi-core awareness)
        has_fpu: Whether this core has FPU
        has_dsp: Whether this core has DSP extension
        enabled: Whether this core is enabled (some cores can be disabled)
        affinity_mask: Bitmask for RTOS affinity configuration
    """

    name: str
    core_type: CoreType
    frequency_hz: int = 0
    core_id: int = 0
    has_fpu: bool = False
    has_dsp: bool = False
    enabled: bool = True
    affinity_mask: int = 0

    @property
    def frequency_mhz(self) -> float:
        """Get frequency in MHz."""
        return self.frequency_hz / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "core_type": self.core_type.value,
            "frequency_hz": self.frequency_hz,
            "frequency_mhz": self.frequency_mhz,
            "core_id": self.core_id,
            "has_fpu": self.has_fpu,
            "has_dsp": self.has_dsp,
            "enabled": self.enabled,
            "affinity_mask": self.affinity_mask,
        }


@dataclass
class ChipRevision:
    """Chip revision information.

    Attributes:
        revision_id: Silicon revision identifier (A, B, 1.0, etc.)
        stepping: Mask ROM stepping (for chips with mask ROM)
        description: Human-readable description
        known_issues: List of known issues for this revision
        compatible: Whether this revision is compatible with the plugin
    """

    revision_id: str
    stepping: str | None = None
    description: str = ""
    known_issues: list[str] = field(default_factory=list)
    compatible: bool = True

    def __hash__(self) -> int:
        """Make hashable for comparison."""
        return hash((self.revision_id, self.stepping or ""))


@dataclass
class ChipSpec:
    """Extended chip specification.

    This is the Phase 6.1 replacement for ChipDescription with additional
    fields for revision, temperature range, multi-core support, etc.

    Attributes:
        part_number: Full part number (e.g., STM32F407VGT6)
        family: Chip family
        revision: Chip revision info
        cores: List of cores in this chip
        temperature_range: Operating temperature range
        max_frequency_hz: Maximum specified frequency
        vendor: Chip vendor/manufacturer
        series: Product series within vendor
        package: Package type
        flash_size_kb: Flash memory size in KB
        sram_size_kb: SRAM size in KB
        core_voltage_v: Core voltage in Volts
        io_voltage_v: I/O voltage in Volts
        has_mpu: Whether MPU is present
        has_fpu: Whether FPU is present
        has_dsp: Whether DSP is present
        has_trustzone: Whether ARM TrustZone is supported
        svd_file: Path to SVD file for register definitions
        memory_regions: Memory region definitions
        ids: Device identification (IDCODE, CHIP_ID, etc.)
    """

    part_number: str
    family: ChipFamily
    revision: ChipRevision | None = None
    cores: list[Core] = field(default_factory=list)
    temperature_range: TemperatureRange = TemperatureRange.INDUSTRIAL

    # Frequency and power
    max_frequency_hz: int = 0
    core_voltage_v: float = 0.0
    io_voltage_v: float = 0.0

    # Vendor and series
    vendor: str = "Unknown"
    series: str = ""

    # Package
    package: PackageType | None = None

    # Memory sizes (in KB)
    flash_size_kb: int = 0
    sram_size_kb: int = 0

    # Features
    has_mpu: bool = False
    has_fpu: bool = False
    has_dsp: bool = False
    has_trustzone: bool = False
    has_mpu_plus: bool = False

    # SVD
    svd_file: str | None = None

    # Memory regions
    memory_regions: list[MemoryRegion] = field(default_factory=list)

    # Device identification
    ids: dict[str, int | str] = field(default_factory=dict)

    # Metadata
    description: str = ""
    datasheet_url: str | None = None

    @property
    def primary_core(self) -> Core | None:
        """Get the primary (first) core."""
        if self.cores:
            return self.cores[0]
        return None

    @property
    def core_count(self) -> int:
        """Get number of enabled cores."""
        return len([c for c in self.cores if c.enabled])

    @property
    def max_frequency_mhz(self) -> float:
        """Get max frequency in MHz."""
        return self.max_frequency_hz / 1_000_000

    @property
    def total_flash_bytes(self) -> int:
        """Get total flash size in bytes."""
        return self.flash_size_kb * 1024

    @property
    def total_sram_bytes(self) -> int:
        """Get total SRAM size in bytes."""
        return self.sram_size_kb * 1024

    def get_core_by_name(self, name: str) -> Core | None:
        """Get core by name."""
        for core in self.cores:
            if core.name == name:
                return core
        return None

    def get_core_by_id(self, core_id: int) -> Core | None:
        """Get core by ID."""
        for core in self.cores:
            if core.core_id == core_id:
                return core
        return None

    @property
    def flash_region(self) -> MemoryRegion | None:
        """Get flash memory region."""
        for r in self.memory_regions:
            if "FLASH" in r.name.upper():
                return r
        return None

    @property
    def sram_regions(self) -> list[MemoryRegion]:
        """Get SRAM regions."""
        return [r for r in self.memory_regions if "SRAM" in r.name.upper() or r.region_type == "RAM"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "part_number": self.part_number,
            "family": self.family.value,
            "revision": self.revision.revision_id if self.revision else None,
            "cores": [c.to_dict() for c in self.cores],
            "core_count": self.core_count,
            "temperature_range": self.temperature_range.name,
            "max_frequency_mhz": self.max_frequency_mhz,
            "vendor": self.vendor,
            "series": self.series,
            "package": self.package.name if self.package else None,
            "flash_size_kb": self.flash_size_kb,
            "sram_size_kb": self.sram_size_kb,
            "has_mpu": self.has_mpu,
            "has_fpu": self.has_fpu,
            "has_dsp": self.has_dsp,
            "has_trustzone": self.has_trustzone,
            "svd_file": self.svd_file,
            "ids": self.ids,
            "description": self.description,
        }

    @classmethod
    def from_chip_description(
        cls,
        chip: Any,
        revision: ChipRevision | None = None,
    ) -> "ChipSpec":
        """Create ChipSpec from existing ChipDescription for compatibility."""
        cores = []
        if hasattr(chip, "core"):
            primary = Core(
                name="CPU0",
                core_type=chip.core,
                has_fpu=chip.has_fpu,
                has_dsp=chip.has_dsp,
            )
            cores.append(primary)

        return cls(
            part_number=chip.part_number,
            family=chip.family,
            revision=revision,
            cores=cores,
            has_fpu=chip.has_fpu,
            has_dsp=chip.has_dsp,
            has_mpu=chip.has_mpu,
            svd_file=chip.svd_file,
            memory_regions=chip.memory_regions,
            description=chip.description,
        )


@dataclass
class Board:
    """Board/development kit definition.

    A board represents a physical development kit or custom board
    that hosts one or more chips.

    Attributes:
        name: Board name (e.g., "STM32F4 Discovery")
        model: Board model identifier
        vendor: Board manufacturer
        chips: List of chips on this board
        connectors: Physical connector definitions
        jumpers: Jumper/switch configuration
        leds: LED definitions
        buttons: Button definitions
        external_crystal_hz: External crystal frequency (if present)
        default_probes: Compatible debug probes
        documentation_url: Link to board documentation
    """

    name: str
    model: str = ""
    vendor: str = "Unknown"
    chips: list[ChipSpec] = field(default_factory=list)

    # Physical attributes
    connectors: dict[str, str] = field(default_factory=dict)  # name -> description
    jumpers: dict[str, str] = field(default_factory=dict)  # name -> position
    leds: dict[str, int] = field(default_factory=dict)  # name -> GPIO pin
    buttons: dict[str, int] = field(default_factory=dict)  # name -> GPIO pin

    # Clock
    external_crystal_hz: int | None = None

    # Debug
    default_probes: list[str] = field(default_factory=list)
    on_board_debug: bool = False  # Has embedded debug probe (e.g., ST-Link)

    # Documentation
    documentation_url: str | None = None
    schematic_url: str | None = None

    @property
    def primary_chip(self) -> ChipSpec | None:
        """Get the primary (first) chip."""
        if self.chips:
            return self.chips[0]
        return None

    @property
    def chip_count(self) -> int:
        """Get number of chips."""
        return len(self.chips)

    def get_chip_by_family(self, family: ChipFamily) -> list[ChipSpec]:
        """Get all chips of a specific family."""
        return [c for c in self.chips if c.family == family]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "model": self.model,
            "vendor": self.vendor,
            "chips": [c.to_dict() for c in self.chips],
            "chip_count": self.chip_count,
            "leds": self.leds,
            "buttons": self.buttons,
            "external_crystal_hz": self.external_crystal_hz,
            "on_board_debug": self.on_board_debug,
            "default_probes": self.default_probes,
        }


@dataclass
class Target:
    """Extended target representation.

    This unifies chip and board into a single target concept
    for Phase 6.1, replacing the earlier EmbeddedTarget.

    Attributes:
        id: Unique target identifier
        name: Human-readable name
        chip: Chip specification
        board: Optional board (for development kits)
        serial_number: Device serial number
        hardware_version: Hardware revision
        firmware_version: Current firmware version
        connected_at: Timestamp of last connection
        last_seen: Timestamp of last activity
    """

    id: str
    name: str
    chip: ChipSpec
    board: Board | None = None

    # Identification
    serial_number: str | None = None
    hardware_version: str | None = None
    lot_number: str | None = None

    # Firmware
    firmware_version: str | None = None
    firmware_hash: str | None = None

    # Timestamps
    manufactured_at: datetime | None = None
    connected_at: datetime | None = None
    last_seen: datetime | None = None

    # Custom metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Get full descriptive name."""
        if self.board:
            return f"{self.board.vendor} {self.board.name} ({self.chip.part_number})"
        return f"{self.chip.vendor} {self.chip.part_number}"

    @property
    def is_connected(self) -> bool:
        """Check if target is currently connected."""
        return self.connected_at is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "chip": self.chip.to_dict(),
            "board": self.board.to_dict() if self.board else None,
            "serial_number": self.serial_number,
            "hardware_version": self.hardware_version,
            "firmware_version": self.firmware_version,
            "firmware_hash": self.firmware_hash,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "metadata": self.metadata,
        }


def create_stm32f4_discovery() -> Target:
    """Create a STM32F4 Discovery board target for testing."""
    chip = ChipSpec(
        part_number="STM32F407VGT6",
        family=ChipFamily.STM32F4,
        revision=ChipRevision(revision_id="A"),
        cores=[
            Core(
                name="CPU0",
                core_type=CoreType.CORTEX_M4,
                frequency_hz=168_000_000,
                core_id=0,
                has_fpu=True,
                has_dsp=True,
            )
        ],
        temperature_range=TemperatureRange.INDUSTRIAL,
        max_frequency_hz=168_000_000,
        vendor="STMicroelectronics",
        series="STM32F4",
        package=PackageType.LQFP,
        flash_size_kb=1024,
        sram_size_kb=192,
        has_mpu=True,
        has_fpu=True,
        has_dsp=True,
        svd_file="STM32F407.svd",
        memory_regions=[
            MemoryRegion(name="FLASH", base_address=0x08000000, size=0x100000, region_type="FLASH"),
            MemoryRegion(name="SRAM1", base_address=0x20000000, size=0x20000, region_type="SRAM"),
            MemoryRegion(name="SRAM2", base_address=0x20020000, size=0x10000, region_type="SRAM"),
            MemoryRegion(name="CCM", base_address=0x10000000, size=0x10000, region_type="CCM"),
        ],
        ids={"idcode": 0x2BA01477},
    )

    board = Board(
        name="STM32F4 Discovery",
        model="STM32F407G-DISC1",
        vendor="STMicroelectronics",
        chips=[chip],
        leds={"LD1": 12, "LD2": 13, "LD3": 14, "LD4": 15},
        buttons={"USER": 0, "RESET": -1},
        external_crystal_hz=8_000_000,
        on_board_debug=True,
        default_probes=["STLink", "JLink"],
    )

    return Target(
        id="stm32f4-discovery",
        name="STM32F4 Discovery Kit",
        chip=chip,
        board=board,
    )
