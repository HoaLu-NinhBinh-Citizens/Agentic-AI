"""Embedded target models for hardware debugging."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class TargetState(Enum):
    """Target connection states."""
    
    UNKNOWN = auto()
    CONNECTED = auto()
    HALTED = auto()
    RUNNING = auto()
    FAULT = auto()
    RESET = auto()
    FLASHING = auto()
    DISCONNECTED = auto()


class ChipFamily(Enum):
    """Supported chip families."""
    
    # ARM Cortex-M
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
    STM32G0 = "STM32G0"
    STM32G4 = "STM32G4"
    STM32WB = "STM32WB"
    STM32WL = "STM32WL"
    
    # Other ARM
    NXP_LPC = "NXP_LPC"
    NXP_KINETIS = "NXP_KINETIS"
    NXP_IMX_RT = "NXP_IMX_RT"
    TI_TIVA = "TI_TIVA"
    TI_MSP430 = "TI_MSP430"
    
    # RISC-V
    RISCV_GENERIC = "RISCV"
    ESPRESSIF_ESP32 = "ESP32"
    ESPRESSIF_ESP32S2 = "ESP32S2"
    ESPRESSIF_ESP32S3 = "ESP32S3"
    ESPRESSIF_ESP32C3 = "ESP32C3"
    ESPRESSIF_ESP32C6 = "ESP32C6"
    HIFIVE_UNmatched = "HIFIVE_UNmatched"
    
    # Other
    Nordic_nRF52 = "nRF52"
    Nordic_nRF53 = "nRF53"
    
    UNKNOWN = "UNKNOWN"


class CoreType(Enum):
    """ARM Core types."""
    
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
    RISC_V = "RISC-V"
    ESP32 = "Xtensa"


class DebugProbeType(Enum):
    """Debug probe types."""
    
    JLINK = "JLINK"
    STLINK = "STLink"
    CMSIS_DAP = "CMSIS-DAP"
    OPENOCD = "OpenOCD"
    PICOKIT = "PICOKIT"
    QEMU = "QEMU"
    RENODE = "Renode"
    pyOCD = "pyOCD"


class DebugInterface(Enum):
    """Debug interface types."""
    
    SWD = "SWD"
    JTAG = "JTAG"


class ResetMode(Enum):
    """Target reset modes."""
    
    HALT_AFTER_RESET = "halt_after_reset"
    RUN_AFTER_RESET = "run_after_reset"
    SOFT_RESET = "soft_reset"
    SYSTEM_RESET = "system_reset"
    CORE_RESET = "core_reset"


class Toolchain(Enum):
    """Toolchain types."""
    
    GCC_ARM = "GCC_ARM"
    ARM_CLANG = "ARM_CLANG"
    IAR = "IAR"
    KEIL = "KEIL"
    LLVM_RISCV = "LLVM_RISCV"
    ESP_IDF = "ESP_IDF"
    RISCV_GCC = "RISCV_GCC"


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
    """JTAG/SWD IDCODE."""
    
    manufacturer_id: int
    part_id: int
    device_id: int
    revision: int
    
    @property
    def full_code(self) -> int:
        """Get full 32-bit IDCODE."""
        return (self.manufacturer_id << 1) | 1
    
    @classmethod
    def from_int(cls, value: int) -> IDCODE:
        """Parse from integer."""
        manufacturer = (value >> 1) & 0x7FF
        part = (value >> 12) & 0xFFFF
        revision = (value >> 28) & 0xF
        return cls(
            manufacturer_id=manufacturer,
            part_id=part,
            device_id=value,
            revision=revision,
        )


@dataclass
class MemoryRegion:
    """Memory region definition."""
    
    name: str
    base_address: int
    size: int
    region_type: str = "RAM"  # RAM, ROM, FLASH, SRAM, CCM
    readable: bool = True
    writable: bool = True
    executable: bool = True
    cached: bool = False


@dataclass
class ChipDescription:
    """Chip description from SVD or config."""
    
    family: ChipFamily
    part_number: str
    core: CoreType
    svd_file: str | None = None
    has_fpu: bool = False
    has_dsp: bool = False
    has_mpu: bool = False
    has_fpu_plus: bool = False
    memory_regions: list[MemoryRegion] = field(default_factory=list)
    manufacturer: str = "Unknown"
    description: str = ""
    
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
    
    @property
    def total_sram_size(self) -> int:
        """Get total SRAM size."""
        return sum(r.size for r in self.sram_regions)


@dataclass
class DebugProbeConfig:
    """Debug probe configuration."""
    
    probe_type: DebugProbeType
    interface: DebugInterface = DebugInterface.SWD
    speed_khz: int = 4000
    serial: str | None = None
    jtag_chain_position: int = 0


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
class FirmwareVersion:
    """Firmware version information."""
    
    version: str
    git_hash: str
    build_timestamp: datetime = field(default_factory=datetime.now)
    build_id: str | None = None
    target_chip: ChipFamily = ChipFamily.UNKNOWN
    min_toolchain_version: str | None = None
    elf_file: str | None = None
    binary_file: str | None = None
    
    @property
    def version_hash(self) -> str:
        """Get short hash of version."""
        content = f"{self.version}:{self.git_hash}"
        return hashlib.sha1(content.encode()).hexdigest()[:8]
    
    @property
    def semver_tuple(self) -> tuple[int, int, int]:
        """Parse as semantic version tuple."""
        parts = self.version.lstrip("v").split(".")
        return tuple(int(p) for p in parts[:3]) + (0, 0)  # type: ignore


@dataclass
class FirmwareInfo:
    """Complete firmware information."""
    
    version: FirmwareVersion
    elf_path: str | None = None
    binary_path: str | None = None
    flash_address: int = 0x08000000
    flash_size: int | None = None
    entry_point: int | None = None
    linker_script: str | None = None


@dataclass
class TargetConfig:
    """Complete target configuration."""
    
    id: str
    name: str
    chip: ChipDescription
    debug_probe: DebugProbeConfig
    toolchain: ToolchainConfig
    serial: SerialConfig = field(default_factory=SerialConfig)
    firmware: FirmwareInfo | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "chip": {
                "family": self.chip.family.value,
                "part_number": self.chip.part_number,
                "core": self.chip.core.value,
            },
            "debug_probe": {
                "type": self.debug_probe.probe_type.value,
                "interface": self.debug_probe.interface.value,
                "speed_khz": self.debug_probe.speed_khz,
            },
        }


@dataclass
class EmbeddedTarget:
    """Embedded debug target."""
    
    id: str
    name: str
    chip_family: ChipFamily
    config: TargetConfig | None = None
    state: TargetState = TargetState.UNKNOWN
    debug_probe: DebugProbeType | None = None
    toolchain: Toolchain | None = None
    firmware: FirmwareVersion | None = None
    connected_at: datetime | None = None
    last_activity: datetime | None = None
    
    # Runtime state (when connected)
    pc: int | None = None
    sp: int | None = None
    lr: int | None = None
    fault_reason: FaultType | None = None
    
    def is_connected(self) -> bool:
        """Check if target is connected."""
        return self.state not in (TargetState.UNKNOWN, TargetState.DISCONNECTED)
    
    def can_debug(self) -> bool:
        """Check if target can be debugged."""
        return self.state in (TargetState.HALTED, TargetState.CONNECTED)
    
    def transition(self, new_state: TargetState) -> bool:
        """Transition to new state if valid."""
        valid_transitions: dict[TargetState, set[TargetState]] = {
            TargetState.UNKNOWN: {TargetState.CONNECTED, TargetState.DISCONNECTED},
            TargetState.CONNECTED: {TargetState.HALTED, TargetState.RUNNING, TargetState.FAULT, TargetState.RESET, TargetState.FLASHING, TargetState.DISCONNECTED},
            TargetState.HALTED: {TargetState.RUNNING, TargetState.FAULT, TargetState.RESET, TargetState.FLASHING, TargetState.DISCONNECTED},
            TargetState.RUNNING: {TargetState.HALTED, TargetState.FAULT, TargetState.DISCONNECTED},
            TargetState.FAULT: {TargetState.HALTED, TargetState.RESET, TargetState.DISCONNECTED},
            TargetState.RESET: {TargetState.CONNECTED, TargetState.HALTED, TargetState.RUNNING},
            TargetState.FLASHING: {TargetState.HALTED, TargetState.FAULT, TargetState.CONNECTED},
            TargetState.DISCONNECTED: {TargetState.UNKNOWN},
        }
        
        if new_state in valid_transitions.get(self.state, set()):
            self.state = new_state
            self.last_activity = datetime.now()
            return True
        return False


class ChipInterface(Protocol):
    """Protocol for chip-specific operations."""
    
    async def read_core_register(self, reg: str) -> int: ...
    async def write_core_register(self, reg: str, value: int) -> None: ...
    async def halt(self) -> None: ...
    async def resume(self) -> None: ...
    async def step(self) -> None: ...
    async def set_breakpoint(self, addr: int, bp_type: BreakpointType) -> int: ...
    async def remove_breakpoint(self, bp_num: int) -> None: ...
    async def read_memory(self, addr: int, size: int) -> bytes: ...
    async def write_memory(self, addr: int, data: bytes) -> None: ...
    async def reset(self, mode: ResetMode) -> None: ...


class ProbeInterface(Protocol):
    """Protocol for debug probe operations."""
    
    async def connect(self) -> IDCODE: ...
    async def disconnect(self) -> None: ...
    async def reset(self, mode: ResetMode) -> None: ...
    async def read_dp(self, addr: int) -> int: ...
    async def write_dp(self, addr: int, value: int) -> None: ...
    async def read_ap(self, addr: int) -> int: ...
    async def write_ap(self, addr: int, value: int) -> None: ...
    async def halt(self) -> None: ...
    async def resume(self) -> None: ...
    async def is_connected(self) -> bool: ...


@dataclass
class GDBFrame:
    """GDB stack frame."""
    
    level: int
    pc: int
    sp: int | None = None
    fp: int | None = None
    function: str | None = None
    file: str | None = None
    line: int | None = None
    args: dict[str, int] | None = None


@dataclass
class GDBBreakpoint:
    """GDB breakpoint."""
    
    number: int
    address: int
    bp_type: str
    enabled: bool = True
    hit_count: int = 0
    condition: str | None = None


@dataclass
class GDBRegister:
    """GDB register info."""
    
    name: str
    value: int
    index: int


@dataclass
class StackFrame:
    """Stack frame for backtrace."""
    
    address: int
    function_name: str | None
    source_file: str | None
    source_line: int | None
    arguments: dict[str, Any] | None = None
    locals: dict[str, Any] | None = None


@dataclass
class CrashInfo:
    """Crash/exception information."""
    
    fault_type: FaultType
    fault_address: int | None
    pc: int
    sp: int
    lr: int
    xPSR: int | None
    registers: dict[str, int]
    stack_trace: list[StackFrame]
    timestamp: datetime = field(default_factory=datetime.now)
    raw_cfsr: int | None = None  # Configurable Fault Status Register
    hfsr: int | None = None     # HardFault Status Register
    mmfar: int | None = None    # MemManage Fault Address Register
    bfar: int | None = None     # Bus Fault Address Register
    
    @property
    def is_hard_fault(self) -> bool:
        """Check if hard fault."""
        return self.fault_type == FaultType.HARD_FAULT
    
    @property
    def is_stack_overflow(self) -> bool:
        """Check if stack overflow."""
        return self.fault_type == FaultType.STACK_OVERFLOW


@dataclass
class CompatibilityResult:
    """Result of compatibility check."""
    
    compatible: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    min_toolchain_version: str | None = None
