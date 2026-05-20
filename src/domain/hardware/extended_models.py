"""Extended domain models for embedded target hardware.

Phase 6.1: Extended Chip, Core, Board, MemoryRegion with provenance,
revision, temperature range, multi-core support.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .provenance import Provenance


# ============================================================================
# Core Models
# ============================================================================


class CoreArchitecture(Enum):
    """Core architecture types."""

    CORTEX_M0 = "Cortex-M0"
    CORTEX_M0PLUS = "Cortex-M0+"
    CORTEX_M3 = "Cortex-M3"
    CORTEX_M4 = "Cortex-M4"
    CORTEX_M7 = "Cortex-M7"
    CORTEX_M33 = "Cortex-M33"
    CORTEX_M35P = "Cortex-M35P"
    CORTEX_M55 = "Cortex-M55"
    CORTEX_M85 = "Cortex-M85"
    CORTEX_A = "Cortex-A"
    CORTEX_R = "Cortex-R"
    RISC_V = "RISC-V"
    XTENSA = "Xtensa"
    ARC = "ARC"
    MSP430 = "MSP430"
    UNKNOWN = "Unknown"


class ChipVendor(Enum):
    """Chip vendor identification."""

    ST = "STMicroelectronics"
    ESPRESSIF = "Espressif"
    NXP = "NXP"
    TI = "Texas Instruments"
    INFINEON = "Infineon"
    RENESAS = "Renesas"
    NORDIC = "Nordic Semiconductor"
    SIFIVE = "SiFive"
    MICROCHIP = "Microchip"
    ANALOG_DEVICES = "Analog Devices"
    ON_SEMI = "ON Semiconductor"
    UNKNOWN = "Unknown"


class SteppingLevel(Enum):
    """Chip stepping/revision levels."""

    EARLY = "Early Silicon"
    REVA = "Rev A"
    REVB = "Rev B"
    REVC = "Rev C"
    REVD = "Rev D"
    PRODUCTION = "Production"
    QUALIFICATION = "Qualification"
    ENGINEERING = "Engineering"
    UNKNOWN = "Unknown"


@dataclass
class TemperatureRange:
    """Operating temperature range."""

    min_celsius: float = -40.0
    max_celsius: float = 85.0

    @property
    def min_kelvin(self) -> float:
        """Get minimum in Kelvin."""
        return self.min_celsius + 273.15

    @property
    def max_kelvin(self) -> float:
        """Get maximum in Kelvin."""
        return self.max_celsius + 273.15

    def contains(self, celsius: float) -> bool:
        """Check if temperature is within range."""
        return self.min_celsius <= celsius <= self.max_celsius

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "min_celsius": self.min_celsius,
            "max_celsius": self.max_celsius,
        }


@dataclass
class Core:
    """Represents a CPU core in a multi-core chip.

    In multi-core MCUs (e.g., STM32H7 dual-core), each core is
    represented as a separate Core instance with its own properties.
    """

    name: str
    core_type: CoreArchitecture
    core_id: int  # 0 for primary, 1+ for secondary cores
    frequency_hz: int = 0
    has_fpu: bool = False
    has_dsp: bool = False
    has_mpu: bool = False
    has_cache: bool = False
    cache_size_kb: int = 0
    instruction_set: str = "Thumb"  # Thumb, Thumb-2, RV32IMC, etc.
    supported_endianness: str = "little"  # little, big, bi
    is_primary: bool = True
    has_hardware_divide: bool = False
    has_bitband: bool = False
    hardware_divide_cycles: int = 12  # Typical cycles for 32-bit divide

    # Multi-core synchronization
    supports_smp: bool = False
    has_tcm: bool = False  # Tightly Coupled Memory
    tcm_size_kb: int = 0

    # State
    current_frequency_hz: int | None = None
    is_halted: bool = False
    registers: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate core configuration."""
        if self.core_id < 0:
            raise ValueError(f"core_id must be non-negative, got {self.core_id}")
        if self.frequency_hz < 0:
            raise ValueError(f"frequency_hz must be non-negative, got {self.frequency_hz}")

    @property
    def clock_period_ns(self) -> float:
        """Get clock period in nanoseconds."""
        if self.current_frequency_hz:
            return 1_000_000_000 / self.current_frequency_hz
        if self.frequency_hz:
            return 1_000_000_000 / self.frequency_hz
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "core_type": self.core_type.value,
            "core_id": self.core_id,
            "frequency_hz": self.frequency_hz,
            "has_fpu": self.has_fpu,
            "has_dsp": self.has_dsp,
            "has_mpu": self.has_mpu,
            "has_cache": self.has_cache,
            "cache_size_kb": self.cache_size_kb,
            "instruction_set": self.instruction_set,
            "is_primary": self.is_primary,
            "supports_smp": self.supports_smp,
            "has_tcm": self.has_tcm,
            "tcm_size_kb": self.tcm_size_kb,
        }


# ============================================================================
# Chip Models
# ============================================================================


class ChipFamily(Enum):
    """Supported chip families by vendor."""

    # STMicroelectronics
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
    STM32WL = "STM32WL"
    STM32G0 = "STM32G0"
    STM32G4 = "STM32G4"
    STM32MP1 = "STM32MP1"

    # Espressif
    ESP32 = "ESP32"
    ESP32S2 = "ESP32-S2"
    ESP32S3 = "ESP32-S3"
    ESP32C3 = "ESP32-C3"
    ESP32C6 = "ESP32-C6"
    ESP32H2 = "ESP32-H2"

    # NXP
    NXP_LPC = "NXP_LPC"
    NXP_KINETIS = "NXP_Kinetis"
    NXP_IMX_RT = "NXP_iMX_RT"
    NXP_S32 = "NXP_S32"

    # Texas Instruments
    TI_TIVA = "TI_Tiva"
    TI_MSP430 = "TI_MSP430"
    TI_MSP432 = "TI_MSP432"
    TI_HERCULES = "TI_Hercules"

    # Nordic Semiconductor
    NRF52 = "nRF52"
    NRF53 = "nRF53"
    NRF91 = "nRF91"

    # SiFive
    HIFIVE_UNMATCHED = "HiFive Unmatched"
    HIFIVE_FREELANCE = "HiFive Freelance"
    SIFIVE_CORE = "SiFive Core"

    # Renesas
    RENESAS_RA = "Renesas RA"
    RENESAS_RL = "Renesas RL"
    RENESAS_RX = "Renesas RX"

    # Infineon
    INFINEON_XMC = "Infineon XMC"
    INFINEON_PSoC = "Infineon PSoC"

    # Generic
    RISCV_GENERIC = "RISC-V"
    ARM_GENERIC = "ARM"

    UNKNOWN = "Unknown"


@dataclass
class ChipDescription:
    """Extended chip description with full hardware specification.

    Represents the complete hardware description of a microcontroller,
    including cores, memory, peripherals, and operating conditions.
    """

    # Basic identification
    part_number: str
    vendor: ChipVendor = ChipVendor.UNKNOWN
    series: str = ""
    family: ChipFamily = ChipFamily.UNKNOWN

    # Silicon revision
    revision: str = "1.0"
    stepping: SteppingLevel = SteppingLevel.UNKNOWN

    # Core configuration
    cores: list[Core] = field(default_factory=list)
    primary_core: Core | None = None

    # Operating conditions
    temperature_range: TemperatureRange = field(default_factory=TemperatureRange)
    max_frequency_hz: int = 0
    min_voltage_mv: int = 3300  # Millivolts
    max_voltage_mv: int = 3300

    # Memory
    flash_base: int = 0x08000000
    flash_size: int = 0  # bytes
    ram_base: int = 0x20000000
    ram_size: int = 0  # bytes
    has_boot_rom: bool = True
    boot_rom_size: int = 0

    # Features
    has_fpu: bool = False
    has_dsp: bool = False
    has_mpu: bool = False
    has_cache: bool = False
    has_dwt: bool = False  # Data Watchpoint and Trace
    has_itm: bool = False  # Instrumentation Trace Macrocell
    has_etm: bool = False  # Embedded Trace Macrocell
    has_swo: bool = False  # Serial Wire Output
    has_htm: bool = False  # Historical Trace Macrocell

    # Peripheral support
    has_usb: bool = False
    has_ethernet: bool = False
    has_can: bool = False
    has_lin: bool = False
    has_spi: int = 0  # Number of SPI instances
    has_i2c: int = 0  # Number of I2C instances
    has_uart: int = 0  # Number of UART instances
    has_adc: int = 0  # Number of ADC channels
    has_dac: int = 0  # Number of DAC channels
    has_pwm: int = 0  # Number of PWM channels
    has_timer: int = 0  # Number of timer instances

    # DMA
    dma_channels: int = 0
    has_dma_m2m: bool = False

    # Package
    package: str = ""
    pin_count: int = 0

    # SVD
    svd_file: str | None = None
    svd_path: str | None = None

    # Description
    description: str = ""
    datasheet_url: str | None = None

    # Debug
    debug_interface: str = "SWD"  # SWD, JTAG, cJTAG
    max_breakpoints: int = 8
    max_watchpoints: int = 4

    # Chip ID registers (for auto-detection)
    chip_id_address: int = 0xE0042000
    chip_id_fields: dict[str, int] = field(default_factory=dict)  # name -> address

    # JEP106 manufacturer ID (for auto-detection)
    jep106_manufacturer_id: int = 0  # JEDEC JEP106 assignment
    jep106Continuation: int = 0

    # Part ID (part of IDCODE)
    part_id_mask: int = 0x0000FFFF

    # Creation metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Initialize derived fields."""
        if not self.cores and not self.primary_core:
            # Create default core from flags
            default_core = Core(
                name="Main",
                core_type=CoreArchitecture.CORTEX_M4 if self.has_fpu else CoreArchitecture.CORTEX_M3,
                core_id=0,
                frequency_hz=self.max_frequency_hz,
                has_fpu=self.has_fpu,
                has_dsp=self.has_dsp,
                has_mpu=self.has_mpu,
            )
            self.cores = [default_core]
            self.primary_core = default_core
        elif not self.primary_core and self.cores:
            self.primary_core = self.cores[0]

    @property
    def core_count(self) -> int:
        """Get number of cores."""
        return len(self.cores)

    @property
    def is_multi_core(self) -> bool:
        """Check if chip has multiple cores."""
        return len(self.cores) > 1

    @property
    def total_ram_size(self) -> int:
        """Get total RAM size in bytes."""
        return self.ram_size

    @property
    def total_flash_size(self) -> int:
        """Get total flash size in bytes."""
        return self.flash_size

    def get_core(self, core_id: int) -> Core | None:
        """Get core by ID."""
        for core in self.cores:
            if core.core_id == core_id:
                return core
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "part_number": self.part_number,
            "vendor": self.vendor.value,
            "series": self.series,
            "family": self.family.value,
            "revision": self.revision,
            "stepping": self.stepping.value,
            "cores": [c.to_dict() for c in self.cores],
            "temperature_range": self.temperature_range.to_dict(),
            "max_frequency_hz": self.max_frequency_hz,
            "flash_base": hex(self.flash_base),
            "flash_size": self.flash_size,
            "ram_base": hex(self.ram_base),
            "ram_size": self.ram_size,
            "has_fpu": self.has_fpu,
            "has_dsp": self.has_dsp,
            "has_mpu": self.has_mpu,
            "has_etm": self.has_etm,
            "has_swo": self.has_swo,
            "debug_interface": self.debug_interface,
            "package": self.package,
            "pin_count": self.pin_count,
            "svd_file": self.svd_file,
            "description": self.description,
        }

    def to_chip_id_code(self) -> str:
        """Generate unique chip ID code for caching/comparison."""
        content = f"{self.vendor.value}:{self.part_number}:{self.revision}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class MemoryRegion:
    """Memory region definition with detailed attributes.

    Represents a memory region (Flash, RAM, ROM, TCM, etc.)
    with access permissions and caching information.
    """

    name: str
    base_address: int
    size: int

    # Type classification
    region_type: str = "RAM"  # RAM, ROM, FLASH, SRAM, CCM, DTCM, ITCM, QSPI, OSPI

    # Access permissions
    readable: bool = True
    writable: bool = True
    executable: bool = True

    # Caching
    cached: bool = False
    write_through: bool = False
    write_back: bool = False
    prefetch_buffer: bool = False

    # Memory attributes (MPU)
    shareable: bool = False
    strongly_ordered: bool = False
    device: bool = False

    # Organization
    is_internal: bool = True
    bank_count: int = 1

    # Security (TrustZone for M33/M55)
    secure: bool = True

    # State tracking
    current_usage: int = 0  # bytes currently used

    def __post_init__(self) -> None:
        """Validate memory region."""
        if self.size <= 0:
            raise ValueError(f"Memory region size must be positive, got {self.size}")
        if self.base_address < 0:
            raise ValueError(f"Base address must be non-negative, got {self.base_address}")

    @property
    def end_address(self) -> int:
        """Get end address (exclusive)."""
        return self.base_address + self.size

    @property
    def is_flash(self) -> bool:
        """Check if region is flash memory."""
        return "FLASH" in self.name.upper() or self.region_type.upper() == "FLASH"

    @property
    def is_ram(self) -> bool:
        """Check if region is RAM."""
        return "RAM" in self.name.upper() or self.region_type.upper() in ("RAM", "SRAM")

    @property
    def is_tcm(self) -> bool:
        """Check if region is Tightly Coupled Memory."""
        return "TCM" in self.name.upper() or "DTCM" in self.name.upper() or "ITCM" in self.name.upper()

    @property
    def usage_percent(self) -> float:
        """Get memory usage percentage."""
        if self.size == 0:
            return 0.0
        return (self.current_usage / self.size) * 100

    def contains_address(self, address: int) -> bool:
        """Check if address is within this region."""
        return self.base_address <= address < self.end_address

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "base_address": hex(self.base_address),
            "end_address": hex(self.end_address),
            "size": self.size,
            "size_kb": self.size // 1024,
            "region_type": self.region_type,
            "readable": self.readable,
            "writable": self.writable,
            "executable": self.executable,
            "cached": self.cached,
            "is_internal": self.is_internal,
            "usage_percent": round(self.usage_percent, 2),
        }


@dataclass
class Board:
    """Development board or custom hardware board.

    Represents a complete board with chip, debug probe connection,
    and peripheral mappings.
    """

    id: str
    name: str
    description: str = ""

    # Chip on the board
    chip: ChipDescription | None = None

    # Memory layout (may differ from chip defaults)
    memory_regions: list[MemoryRegion] = field(default_factory=list)

    # Debug probe
    default_probe_type: str = "STLINK"
    default_interface: str = "SWD"
    default_speed_khz: int = 4000
    probe_connector: str = ""  # CN1, J1, etc.

    # Pin mappings
    pin_header: str = ""  # Arduino headers, etc.
    gpio_count: int = 0

    # On-board peripherals
    has_debug_led: bool = False
    has_boot_button: bool = False
    has_reset_button: bool = False
    has_usb_device: bool = False
    has_usb_host: bool = False

    # External oscillators
    hse_frequency_hz: int = 0  # High Speed External
    lse_frequency_hz: int = 32768  # Low Speed External

    # Configuration
    config_file: str | None = None
    svd_file: str | None = None

    # Boot configuration
    boot_from_flash: bool = True
    boot_pins: dict[str, str] = field(default_factory=dict)

    # Manufacturer info
    manufacturer: str = ""
    url: str | None = None

    # Version tracking
    version: str = "1.0"
    hw_version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Initialize board from chip if not specified."""
        if not self.memory_regions and self.chip:
            # Use chip memory configuration
            if self.chip.flash_size > 0:
                self.memory_regions.append(
                    MemoryRegion(
                        name="Flash",
                        base_address=self.chip.flash_base,
                        size=self.chip.flash_size,
                        region_type="FLASH",
                        writable=True,
                        executable=True,
                    )
                )
            if self.chip.ram_size > 0:
                self.memory_regions.append(
                    MemoryRegion(
                        name="SRAM",
                        base_address=self.chip.ram_base,
                        size=self.chip.ram_size,
                        region_type="RAM",
                        writable=True,
                        readable=True,
                        executable=False,
                    )
                )

    @property
    def flash_region(self) -> MemoryRegion | None:
        """Get flash memory region."""
        for region in self.memory_regions:
            if region.is_flash:
                return region
        return None

    @property
    def ram_region(self) -> MemoryRegion | None:
        """Get primary RAM region."""
        for region in self.memory_regions:
            if region.is_ram:
                return region
        return None

    def get_memory_region_by_address(self, address: int) -> MemoryRegion | None:
        """Find memory region containing address."""
        for region in self.memory_regions:
            if region.contains_address(address):
                return region
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "chip": self.chip.part_number if self.chip else None,
            "memory_regions": [r.to_dict() for r in self.memory_regions],
            "default_probe_type": self.default_probe_type,
            "manufacturer": self.manufacturer,
            "version": self.version,
        }


# ============================================================================
# Target Models
# ============================================================================


class TargetState(Enum):
    """Target connection states with lifecycle."""

    UNKNOWN = auto()
    DISCOVERED = auto()  # Target seen but not connected
    CONNECTING = auto()
    CONNECTED = auto()
    HALTED = auto()
    RUNNING = auto()
    FAULT = auto()
    RESET = auto()
    FLASHING = auto()
    SLEEPING = auto()
    POWERED_OFF = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()

    @classmethod
    def is_active(cls, state: TargetState) -> bool:
        """Check if state is active (debuggable)."""
        return state in (
            cls.CONNECTED,
            cls.HALTED,
            cls.RUNNING,
        )

    @classmethod
    def is_error(cls, state: TargetState) -> bool:
        """Check if state indicates error."""
        return state == cls.FAULT


class DebugProbeType(Enum):
    """Debug probe types."""

    JLINK = "JLINK"
    STLINK = "STLink"
    CMSIS_DAP = "CMSIS-DAP"
    OPENOCD = "OpenOCD"
    PICOKIT = "PICOKIT"
    QEMU = "QEMU"
    RENODE = "Renode"
    PYOCD = "pyOCD"
    ESP_PROG = "ESP-Prog"
    J_LINK = "J-Link"  # Alternative naming
    RTT = "RTT"  # SEGGER RTT terminal


class DebugInterface(Enum):
    """Debug interface types."""

    SWD = "SWD"
    JTAG = "JTAG"
    CJTAG = "cJTAG"
    SPD = "SPD"  # Single Pin Debug


class ResetMode(Enum):
    """Target reset modes."""

    HALT_AFTER_RESET = "halt_after_reset"
    RUN_AFTER_RESET = "run_after_reset"
    SOFT_RESET = "soft_reset"
    SYSTEM_RESET = "system_reset"
    CORE_RESET = "core_reset"
    AIR_RESET = "air_reset"  # Assert, Inspect, Release


class Toolchain(Enum):
    """Toolchain types."""

    GCC_ARM = "GCC_ARM"
    ARM_CLANG = "ARM_CLANG"
    IAR = "IAR"
    KEIL = "KEIL"
    LLVM_ARM = "LLVM_ARM"
    LLVM_RISCV = "LLVM_RISCV"
    ESP_IDF = "ESP_IDF"
    RISCV_GCC = "RISCV_GCC"
    RISCV_IDE = "RISCV_IDE"
    ZEPHYR = "ZEPHYR"


class BreakpointType(Enum):
    """Breakpoint types."""

    SOFTWARE = "software"
    HARDWARE = "hardware"
    FLASH = "flash"
    HYBRID = "hybrid"


class FaultType(Enum):
    """ARM fault types."""

    HARD_FAULT = "HARD_FAULT"
    MEM_MANAGE_FAULT = "MEM_MANAGE_FAULT"
    BUS_FAULT = "BUS_FAULT"
    USAGE_FAULT = "USAGE_FAULT"
    NMI = "NMI"
    STACK_OVERFLOW = "STACK_OVERFLOW"
    STACK_UNDERFLOW = "STACK_UNDERFLOW"
    WATCHDOG = "WATCHDOG"
    UNKNOWN = "UNKNOWN"


@dataclass
class IDCODE:
    """JTAG/SWD IDCODE register value.

    IDCODE format (32 bits):
    - Bit 0: Always 1 (indicates JTAG presence)
    - Bits 1-11: Manufacturer ID (JEDEC JEP-106)
    - Bits 12-27: Part Number
    - Bits 28-31: Revision
    """

    manufacturer_id: int
    part_id: int
    device_id: int
    revision: int
    jep106_continuation: int = 0

    @property
    def full_code(self) -> int:
        """Get full 32-bit IDCODE."""
        return self.device_id

    @classmethod
    def from_int(cls, value: int) -> IDCODE:
        """Parse from 32-bit integer."""
        if value == 0:
            return cls(manufacturer_id=0, part_id=0, device_id=0, revision=0)

        manufacturer = (value >> 1) & 0x7FF
        part = (value >> 12) & 0xFFFF
        revision = (value >> 28) & 0xF
        return cls(
            manufacturer_id=manufacturer,
            part_id=part,
            device_id=value,
            revision=revision,
        )

    def to_manufacturer_code(self) -> tuple[int, int]:
        """Get JEP106 manufacturer code (bank, index)."""
        bank = self.jep106_continuation
        index = self.manufacturer_id - (self.jep106_continuation * 7)
        return (bank, index)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "manufacturer_id": f"0x{self.manufacturer_id:03X}",
            "part_id": f"0x{self.part_id:04X}",
            "device_id": f"0x{self.device_id:08X}",
            "revision": self.revision,
        }


@dataclass
class DebugProbeConfig:
    """Debug probe configuration."""

    probe_type: DebugProbeType
    interface: DebugInterface = DebugInterface.SWD
    speed_khz: int = 4000
    serial: str | None = None
    jtag_chain_position: int = 0
    vid: int | None = None  # USB Vendor ID
    pid: int | None = None  # USB Product ID


@dataclass
class SerialConfig:
    """Serial/UART configuration."""

    enabled: bool = False
    port: str | None = None
    baudrate: int = 115200
    parity: str = "none"
    stopbits: int = 1
    bytesize: int = 8
    timeout: float = 1.0


@dataclass
class ToolchainConfig:
    """Toolchain configuration."""

    name: Toolchain
    prefix: str = "arm-none-eabi-"
    objcopy: str = "arm-none-eabi-objcopy"
    gdb: str = "arm-none-eabi-gdb"
    openocd_config: str | None = None


@dataclass
class TargetConfig:
    """Complete target configuration."""

    id: str
    name: str
    chip: ChipDescription
    debug_probe: DebugProbeConfig
    toolchain: ToolchainConfig
    serial: SerialConfig = field(default_factory=SerialConfig)
    board: Board | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "chip": self.chip.part_number if self.chip else None,
            "debug_probe": self.debug_probe.probe_type.value,
            "toolchain": self.toolchain.name.value,
        }


@dataclass
class EmbeddedTarget:
    """Embedded debug target with full state tracking.

    Represents a connected debug target with its current state,
    runtime information, and associated resources.
    """

    id: str
    name: str
    chip_family: ChipFamily
    config: TargetConfig | None = None
    state: TargetState = TargetState.UNKNOWN
    debug_probe: DebugProbeType | None = None
    toolchain: Toolchain | None = None

    # Timestamps
    discovered_at: datetime | None = None
    connected_at: datetime | None = None
    last_activity: datetime | None = None
    disconnected_at: datetime | None = None

    # Runtime state (when connected)
    pc: int | None = None
    sp: int | None = None
    lr: int | None = None
    fault_reason: FaultType | None = None

    # Chip details (populated on connection)
    chip_description: ChipDescription | None = None
    cores: list[Core] = field(default_factory=list)
    memory_regions: list[MemoryRegion] = field(default_factory=list)

    # Probe info
    probe_serial: str | None = None
    probe_firmware_version: str | None = None

    # Current execution state
    is_halted: bool = False
    current_instruction: str | None = None
    registers: dict[str, int] = field(default_factory=dict)

    # Reset state
    reset_count: int = 0
    last_reset_reason: str | None = None

    # Session tracking
    session_id: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.last_activity is None:
            self.last_activity = datetime.now()

    def is_connected(self) -> bool:
        """Check if target is connected."""
        return TargetState.is_active(self.state)

    def can_debug(self) -> bool:
        """Check if target can be debugged."""
        return self.state in (TargetState.HALTED, TargetState.CONNECTED)

    def is_faulted(self) -> bool:
        """Check if target is in fault state."""
        return TargetState.is_error(self.state)

    def transition(self, new_state: TargetState) -> bool:
        """Transition to new state if valid."""
        valid_transitions: dict[TargetState, set[TargetState]] = {
            TargetState.UNKNOWN: {TargetState.DISCOVERED, TargetState.CONNECTING},
            TargetState.DISCOVERED: {TargetState.CONNECTING, TargetState.DISCONNECTED},
            TargetState.CONNECTING: {TargetState.CONNECTED, TargetState.FAULT, TargetState.DISCONNECTED},
            TargetState.CONNECTED: {TargetState.HALTED, TargetState.RUNNING, TargetState.FAULT, TargetState.RESET, TargetState.FLASHING, TargetState.DISCONNECTING},
            TargetState.HALTED: {TargetState.RUNNING, TargetState.FAULT, TargetState.RESET, TargetState.FLASHING, TargetState.DISCONNECTING},
            TargetState.RUNNING: {TargetState.HALTED, TargetState.FAULT, TargetState.DISCONNECTING},
            TargetState.FAULT: {TargetState.HALTED, TargetState.RESET, TargetState.DISCONNECTING},
            TargetState.RESET: {TargetState.CONNECTED, TargetState.HALTED, TargetState.RUNNING},
            TargetState.FLASHING: {TargetState.HALTED, TargetState.FAULT, TargetState.CONNECTED},
            TargetState.SLEEPING: {TargetState.CONNECTED, TargetState.HALTED, TargetState.FAULT},
            TargetState.DISCONNECTING: {TargetState.DISCONNECTED},
            TargetState.DISCONNECTED: {TargetState.UNKNOWN},
        }

        if new_state not in valid_transitions.get(self.state, set()):
            return False

        self.state = new_state
        self.last_activity = datetime.now()

        if new_state == TargetState.CONNECTED:
            self.connected_at = datetime.now()
        elif new_state == TargetState.DISCONNECTED:
            self.disconnected_at = datetime.now()

        return True

    def get_core_state(self, core_id: int) -> Core | None:
        """Get state for specific core."""
        for core in self.cores:
            if core.core_id == core_id:
                return core
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.name,
            "chip_family": self.chip_family.value,
            "pc": hex(self.pc) if self.pc else None,
            "sp": hex(self.sp) if self.sp else None,
            "fault_reason": self.fault_reason.value if self.fault_reason else None,
            "cores": len(self.cores),
            "memory_regions": [r.name for r in self.memory_regions],
        }
