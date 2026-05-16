"""Core data models for the Hardware Semantic Engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RegisterAccess(str, Enum):
    READ_ONLY = "RO"
    WRITE_ONLY = "WO"
    READ_WRITE = "RW"
    READ_CLEAR = "RC"
    WRITE_CLEAR = "WC"


class PeripheralState(str, Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    RESET = "reset"
    UNKNOWN = "unknown"


# ─── Chip & Peripheral ──────────────────────────────────────────────


@dataclass
class Chip:
    name: str
    family: str
    core: str
    vendor: str
    package: str = ""
    speed_hz: int = 0
    flash_kb: int = 0
    sram_kb: int = 0


@dataclass
class Bitfield:
    name: str
    offset: int
    width: int
    access: str = "RW"
    description: str = ""
    values: Dict[str, Any] = field(default_factory=dict)
    reset_value: int = 0


@dataclass
class Register:
    name: str
    offset: int
    access: str = "RW"
    description: str = ""
    bitfields: List[Bitfield] = field(default_factory=list)
    reset_value: Optional[int] = None


@dataclass
class Interrupt:
    name: str
    irq_line: int
    priority_default: int = 0
    description: str = ""


@dataclass
class Signal:
    name: str
    peripheral: str
    pin: Optional[str] = None
    alternate_function: Optional[int] = None
    direction: str = "input"
    description: str = ""


@dataclass
class Peripheral:
    name: str
    base_address: int
    description: str = ""
    registers: List[Register] = field(default_factory=list)
    clock_enable_bit: Optional[str] = None
    reset_bit: Optional[str] = None
    interrupts: List[Interrupt] = field(default_factory=list)
    state: PeripheralState = PeripheralState.DISABLED
    signals: List[Signal] = field(default_factory=list)
    protocol: str = ""
    max_speed_hz: int = 0
    tags: List[str] = field(default_factory=list)


# ─── Pin ─────────────────────────────────────────────────────────────


@dataclass
class PinFunction:
    function: str
    peripheral: Optional[str] = None
    alternate_number: int = 0
    available: bool = True


@dataclass
class Pin:
    name: str
    port: str
    number: int
    analog_channels: List[str] = field(default_factory=list)
    functions: List[PinFunction] = field(default_factory=list)
    voltage_min: float = 0.0
    voltage_max: float = 3.3
    current_ma: float = 0.0
    description: str = ""
    reserved_by: Optional[str] = None


# ─── Clock ──────────────────────────────────────────────────────────


@dataclass
class ClockDomain:
    name: str
    source: str
    frequency_hz: int = 0
    prescaler: int = 1
    parent: Optional[str] = None
    enables: List[str] = field(default_factory=list)
    description: str = ""


# ─── Interrupt ───────────────────────────────────────────────────────


@dataclass
class InterruptAllocation:
    irq_line: int
    peripheral: str
    handler_name: str
    priority: int = 0
    subpriority: int = 0
    enabled: bool = False


@dataclass
class NVICConfig:
    total_channels: int
    priority_bits: int
    priority_levels: int


# ─── Hardware Constraint ──────────────────────────────────────────────


@dataclass
class HardwareConstraint:
    type: str
    peripheral: str
    description: str
    parameter: Optional[str] = None
    value: Any = None
    severity: ValidationSeverity = ValidationSeverity.ERROR


# ─── Allocation ──────────────────────────────────────────────────────


@dataclass
class AllocationContext:
    peripheral: str
    mode: str = "default"
    parameters: Dict[str, Any] = field(default_factory=dict)
    project: str = ""
    pin_assignments: Dict[str, str] = field(default_factory=dict)
    clock_config: Optional[ClockDomain] = None
    interrupt_config: Optional[NVICConfig] = None


@dataclass
class PinAssignment:
    signal: str
    pin: str
    alternate_function: int
    direction: str
    pull_config: str = "none"


@dataclass
class ClockAssignment:
    peripheral: str
    domain: str
    source: str
    frequency_hz: int
    prescaler: int


@dataclass
class InterruptAssignment:
    peripheral: str
    signal: str
    irq_line: int
    handler_name: str
    priority: int


@dataclass
class RegisterWrite:
    peripheral: str
    register: str
    field_name: str
    value: int
    operation: str = "write"
    description: str = ""


@dataclass
class ResourceAllocation:
    peripheral: str
    mode: str
    pin_assignments: List[PinAssignment] = field(default_factory=list)
    clock_assignment: Optional[ClockAssignment] = None
    interrupt_assignment: Optional[InterruptAssignment] = None
    register_writes: List[RegisterWrite] = field(default_factory=list)
    constraints: List[HardwareConstraint] = field(default_factory=list)
    citations: List[Dict] = field(default_factory=list)


@dataclass
class AllocationResult:
    valid: bool
    peripheral: str
    allocation: Optional[ResourceAllocation] = None
    constraints: List[HardwareConstraint] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)


# ─── Validation ─────────────────────────────────────────────────────


@dataclass
class ValidationFinding:
    severity: ValidationSeverity
    rule_id: str
    message: str
    location: str = ""
    peripheral: str = ""
    fix_suggestion: str = ""
    citation: Optional[Dict] = None


@dataclass
class ValidationResult:
    valid: bool
    errors: int = 0
    warnings: int = 0
    findings: List[ValidationFinding] = field(default_factory=list)

    def add_error(self, rule_id: str, message: str, location: str = "", peripheral: str = ""):
        self.findings.append(ValidationFinding(
            severity=ValidationSeverity.ERROR,
            rule_id=rule_id,
            message=message,
            location=location,
            peripheral=peripheral,
        ))
        self.errors += 1
        self.valid = False

    def add_warning(self, rule_id: str, message: str, location: str = "", peripheral: str = ""):
        self.findings.append(ValidationFinding(
            severity=ValidationSeverity.WARNING,
            rule_id=rule_id,
            message=message,
            location=location,
            peripheral=peripheral,
        ))
        self.warnings += 1

    def add_info(self, rule_id: str, message: str, location: str = "", peripheral: str = ""):
        self.findings.append(ValidationFinding(
            severity=ValidationSeverity.INFO,
            rule_id=rule_id,
            message=message,
            location=location,
            peripheral=peripheral,
        ))


# ─── Citation ────────────────────────────────────────────────────────


@dataclass
class Citation:
    document: str
    section: str
    page: int = 0
    excerpt: str = ""
    chip: str = ""
