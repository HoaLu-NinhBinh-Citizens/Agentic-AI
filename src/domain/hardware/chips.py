"""Hardware domain module - Enhanced chip models with full hardware semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ChipFamily(Enum):
    """Supported MCU families."""
    STM32F0 = "STM32F0"
    STM32F1 = "STM32F1"
    STM32F2 = "STM32F2"
    STM32F3 = "STM32F3"
    STM32F4 = "STM32F4"
    STM32F7 = "STM32F7"
    STM32H7 = "STM32H7"
    STM32L0 = "STM32L0"
    STM32L1 = "STM32L1"
    STM32L4 = "STM32L4"
    STM32L5 = "STM32L5"
    STM32U5 = "STM32U5"
    STM32WB = "STM32WB"
    STM32G0 = "STM32G0"
    STM32G4 = "STM32G4"
    ESP32 = "ESP32"
    ESP32S2 = "ESP32-S2"
    ESP32S3 = "ESP32-S3"
    ESP32C3 = "ESP32-C3"
    ESP32C6 = "ESP32-C6"
    NRF52 = "nRF52"
    NRF91 = "nRF91"
    RP2040 = "RP2040"
    LPC55 = "LPC55"
    IMXRT = "i.MX RT"
    UNKNOWN = "Unknown"


class CoreType(Enum):
    """CPU core types."""
    CORTEX_M0 = "ARM Cortex-M0"
    CORTEX_M0PLUS = "ARM Cortex-M0+"
    CORTEX_M3 = "ARM Cortex-M3"
    CORTEX_M4 = "ARM Cortex-M4"
    CORTEX_M7 = "ARM Cortex-M7"
    CORTEX_M33 = "ARM Cortex-M33"
    CORTEX_M35P = "ARM Cortex-M35P"
    CORTEX_M55 = "ARM Cortex-M55"
    CORTEX_M85 = "ARM Cortex-M85"
    RISCV = "RISC-V"
    XTENSA = "Xtensa"
    UNKNOWN = "Unknown"


class Vendor(Enum):
    """MCU vendors."""
    ST = "STMicroelectronics"
    ESPRESSIF = "Espressif"
    NORDIC = "Nordic Semiconductor"
    NXP = "NXP"
    MICROCHIP = "Microchip"
    INFINEON = "Infineon"
    RENESAS = "Renesas"
    UNKNOWN = "Unknown"


class DebugProbeType(Enum):
    """Debug probe types."""
    JLINK = "SEGGER J-Link"
    STLINK = "ST-Link"
    CMSIS_DAP = "CMSIS-DAP"
    OPENOCD = "OpenOCD"
    PICkit = "PICkit"
    UNKNOWN = "Unknown"


@dataclass
class Core:
    """Represents a CPU core within a chip."""
    name: str
    type: CoreType
    frequency_hz: Optional[int] = None
    has_fpu: bool = False
    has_dsp: bool = False
    has_mpu: bool = False
    has_cache: bool = False
    cache_size_kb: Optional[int] = None
    has_tcm: bool = False
    itcm_size_kb: Optional[int] = None
    dtcm_size_kb: Optional[int] = None
    interrupt_lines: int = 32
    priority_bits: int = 4


@dataclass
class MemoryRegion:
    """Represents a memory region."""
    name: str
    start: int
    size: int
    access: str = "RW"  # R, W, RW, RO, WO
    type: str = "RAM"  # RAM, FLASH, EEPROM, QSPI, SRAM, CCM
    executable: bool = False
    cached: bool = True
    mpu_attributes: Optional[str] = None

    @property
    def end(self) -> int:
        return self.start + self.size

    @property
    def size_kb(self) -> float:
        return self.size / 1024

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    def contains(self, address: int) -> bool:
        """Check if address is within this region."""
        return self.start <= address < self.end

    def __str__(self) -> str:
        return f"{self.name}: 0x{self.start:08X}-0x{self.end:08X} ({self.size_kb:.1f} KB)"


@dataclass
class Interrupt:
    """Represents a hardware interrupt."""
    name: str
    number: int
    priority_default: int = 0
    priority_min: int = 0
    priority_max: int = 15
    description: str = ""
    peripheral: Optional[str] = None
    type: str = "regular"  # regular, nmi, fault, software

    @property
    def priority_range(self) -> str:
        return f"{self.priority_min}-{self.priority_max}"

    def validate_priority(self, priority: int) -> bool:
        return self.priority_min <= priority <= self.priority_max


@dataclass
class DMADMAChannel:
    """Represents a DMA channel/request."""
    name: str
    channel: int
    request_line: Optional[int] = None
    peripheral: Optional[str] = None
    direction: str = "both"  # read, write, both
    max_burst: int = 4
    fifo_threshold: Optional[int] = None


@dataclass
class ClockConfig:
    """Clock configuration for a peripheral."""
    clock_name: str  # e.g., "APB1", "APB2", "AHB1"
    prescaler: Optional[int] = None
    frequency_hz: Optional[int] = None


@dataclass
class Pin:
    """Represents a physical pin."""
    name: str  # e.g., "PA5", "PB10"
    port: str  # e.g., "A", "B"
    number: int
    alternative_functions: list[str] = field(default_factory=list)
    analog_channels: list[str] = field(default_factory=list)
    power_supply: Optional[str] = None
    package_pin: Optional[str] = None


@dataclass
class HardwareChip:
    """Represents a hardware chip with full hardware semantics."""

    name: str
    part_number: str
    family: ChipFamily
    vendor: Vendor
    core: Core

    # Memory
    flash: Optional[MemoryRegion] = None
    ram: Optional[MemoryRegion] = None
    sram1: Optional[MemoryRegion] = None
    sram2: Optional[MemoryRegion] = None
    ccm: Optional[MemoryRegion] = None
    backup_sram: Optional[MemoryRegion] = None
    memory_map: list[MemoryRegion] = field(default_factory=list)

    # Cores (for multi-core)
    cores: list[Core] = field(default_factory=list)

    # Interrupts
    interrupts: list[Interrupt] = field(default_factory=list)

    # DMA
    dma_channels: list[DMADMAChannel] = field(default_factory=list)
    dma_requests: dict[int, str] = field(default_factory=dict)

    # Pins
    pins: list[Pin] = field(default_factory=list)
    pin_count: int = 0

    # Package
    package: str = ""
    temperature_range: str = ""  # e.g., "-40 to 85°C"

    # Debug
    debug_probe: DebugProbeType = DebugProbeType.STLINK
    has_swd: bool = True
    has_jtag: bool = False
    has_trace: bool = False

    # Power
    vdd_min: float = 3.3
    vdd_max: float = 3.6
    current_ma: Optional[float] = None

    # Additional metadata
    svd_file: Optional[str] = None
    datasheet_url: Optional[str] = None
    reference_manual_url: Optional[str] = None
    revision: str = "1.0"
    production_status: str = "Active"

    def __post_init__(self):
        """Initialize default cores list."""
        if not self.cores and self.core:
            self.cores = [self.core]

    @property
    def total_ram_kb(self) -> float:
        """Calculate total RAM size."""
        total = 0
        for region in self.memory_map:
            if "RAM" in region.type or region.type == "SRAM":
                total += region.size_kb
        return total

    @property
    def total_flash_kb(self) -> float:
        """Calculate total flash size."""
        for region in self.memory_map:
            if region.type == "FLASH":
                return region.size_kb
        return 0

    def get_interrupt(self, name_or_number: str | int) -> Optional[Interrupt]:
        """Get interrupt by name or number."""
        if isinstance(name_or_number, int):
            for irq in self.interrupts:
                if irq.number == name_or_number:
                    return irq
        else:
            for irq in self.interrupts:
                if irq.name == name_or_number:
                    return irq
        return None

    def get_peripheral_interrupts(self, peripheral: str) -> list[Interrupt]:
        """Get all interrupts for a peripheral."""
        return [irq for irq in self.interrupts if irq.peripheral == peripheral]

    def get_dma_channel(self, channel: int) -> Optional[DMADMAChannel]:
        """Get DMA channel by number."""
        for ch in self.dma_channels:
            if ch.channel == channel:
                return ch
        return None

    def get_pin(self, pin_name: str) -> Optional[Pin]:
        """Get pin by name (e.g., 'PA5')."""
        for pin in self.pins:
            if pin.name == pin_name:
                return pin
        return None

    def get_memory_region(self, address: int) -> Optional[MemoryRegion]:
        """Get memory region containing address."""
        for region in self.memory_map:
            if region.contains(address):
                return region
        return None

    def validate_clock_config(self, peripheral: str, config: ClockConfig) -> tuple[bool, list[str]]:
        """Validate clock configuration for a peripheral."""
        issues = []

        # Check if clock domain exists
        valid_clocks = ["APB1", "APB2", "AHB1", "AHB2", "AHB3", "APB", "AHB"]
        clock_base = re.sub(r'\d+', '', config.clock_name)

        if clock_base not in valid_clocks:
            issues.append(f"Unknown clock domain: {config.clock_name}")

        # Check frequency limits
        if config.frequency_hz:
            if "APB1" in config.clock_name and config.frequency_hz > 42_000_000:
                issues.append(f"APB1 frequency {config.frequency_hz} exceeds 42 MHz limit")
            if "APB2" in config.clock_name and config.frequency_hz > 84_000_000:
                issues.append(f"APB2 frequency {config.frequency_hz} exceeds 84 MHz limit")

        return len(issues) == 0, issues

    def get_dependency_chain(self, peripheral: str) -> list[str]:
        """Get peripheral dependency chain (what it depends on)."""
        # Clock domain dependencies
        clock_deps = {
            "GPIOA": ["AHB1"],
            "GPIOB": ["AHB1"],
            "USART1": ["APB2"],
            "USART2": ["APB1"],
            "SPI1": ["APB2"],
            "SPI2": ["APB1"],
            "I2C1": ["APB1"],
            "ADC1": ["APB2"],
            "CAN1": ["APB1"],
            "TIM1": ["APB2"],
            "TIM2": ["APB1"],
        }
        return clock_deps.get(peripheral, ["APB1"])

    def __str__(self) -> str:
        return f"{self.name} ({self.part_number}) - {self.core.type.value}"


# Common chip definitions
CHIP_DEFINITIONS: dict[str, HardwareChip] = {
    "STM32F407VG": HardwareChip(
        name="STM32F407VG",
        part_number="STM32F407VGT6",
        family=ChipFamily.STM32F4,
        vendor=Vendor.ST,
        core=Core(
            name="ARM Cortex-M4",
            type=CoreType.CORTEX_M4,
            frequency_hz=168_000_000,
            has_fpu=True,
            has_dsp=True,
            has_mpu=True,
            has_cache=True,
            cache_size_kb=16,
        ),
        flash=MemoryRegion(name="FLASH", start=0x08000000, size=1024*1024, access="RWX", type="FLASH", executable=True),
        sram1=MemoryRegion(name="SRAM1", start=0x20000000, size=128*1024, type="SRAM"),
        sram2=MemoryRegion(name="SRAM2", start=0x20020000, size=64*1024, type="SRAM"),
        ccm=MemoryRegion(name="CCM", start=0x10000000, size=64*1024, type="CCM"),
        pin_count=100,
        package="LQFP100",
        temperature_range="-40 to 85°C",
        debug_probe=DebugProbeType.JLINK,
        has_jtag=True,
        has_trace=True,
    ),

    "STM32F103C8": HardwareChip(
        name="STM32F103C8",
        part_number="STM32F103C8T6",
        family=ChipFamily.STM32F1,
        vendor=Vendor.ST,
        core=Core(
            name="ARM Cortex-M3",
            type=CoreType.CORTEX_M3,
            frequency_hz=72_000_000,
            has_fpu=False,
            has_mpu=False,
        ),
        flash=MemoryRegion(name="FLASH", start=0x08000000, size=64*1024, access="RWX", type="FLASH", executable=True),
        ram=MemoryRegion(name="SRAM", start=0x20000000, size=20*1024, type="SRAM"),
        pin_count=48,
        package="LQFP48",
        temperature_range="-40 to 85°C",
    ),

    "ESP32": HardwareChip(
        name="ESP32",
        part_number="ESP32-WROOM-32",
        family=ChipFamily.ESP32,
        vendor=Vendor.ESPRESSIF,
        core=Core(
            name="Xtensa LX6",
            type=CoreType.XTENSA,
            frequency_hz=240_000_000,
            has_dsp=True,
        ),
        sram1=MemoryRegion(name="SRAM0", start=0x3FF00000, size=128*1024, type="SRAM"),
        sram2=MemoryRegion(name="SRAM1", start=0x3FFE0000, size=200*1024, type="SRAM"),
        pin_count=38,
        package="Module",
    ),

    "nRF52840": HardwareChip(
        name="nRF52840",
        part_number="nRF52840-QIAA",
        family=ChipFamily.NRF52,
        vendor=Vendor.NORDIC,
        core=Core(
            name="ARM Cortex-M4",
            type=CoreType.CORTEX_M4,
            frequency_hz=64_000_000,
            has_fpu=True,
            has_dsp=True,
        ),
        flash=MemoryRegion(name="FLASH", start=0x00000000, size=1024*1024, access="RWX", type="FLASH", executable=True),
        ram=MemoryRegion(name="RAM", start=0x20000000, size=256*1024, type="SRAM"),
        pin_count=48,
        package="aQFN73",
    ),

    "RP2040": HardwareChip(
        name="RP2040",
        part_number="RP2040",
        family=ChipFamily.RP2040,
        vendor=Vendor.UNKNOWN,  # Raspberry Pi
        core=Core(
            name="ARM Cortex-M0+",
            type=CoreType.CORTEX_M0PLUS,
            frequency_hz=133_000_000,
            has_fpu=False,
        ),
        sram1=MemoryRegion(name="SRAM0", start=0x20000000, size=128*1024, type="SRAM"),
        sram2=MemoryRegion(name="SRAM1", start=0x20010000, size=128*1024, type="SRAM"),
        sram3=MemoryRegion(name="SRAM2", start=0x20020000, size=128*1024, type="SRAM"),
        sram4=MemoryRegion(name="SRAM3", start=0x20030000, size=128*1024, type="SRAM"),
        pin_count=40,
        package="QFN56",
    ),
}


def get_chip(name: str) -> Optional[HardwareChip]:
    """Get chip definition by name."""
    return CHIP_DEFINITIONS.get(name)
