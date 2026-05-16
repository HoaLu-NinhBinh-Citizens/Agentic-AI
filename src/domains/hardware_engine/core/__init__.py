"""Core module: data models and domain graphs."""

from src.domains.hardware_engine.core.models import (
    ValidationSeverity,
    RegisterAccess,
    PeripheralState,
    Chip,
    Peripheral,
    Register,
    Bitfield,
    Interrupt,
    Signal,
    Pin,
    PinFunction,
    PinAssignment,
    ClockAssignment,
    InterruptAssignment,
    RegisterWrite,
    ResourceAllocation,
    AllocationContext,
    AllocationResult,
    HardwareConstraint,
    ValidationFinding,
    ValidationResult,
    Citation,
    ClockDomain,
    InterruptAllocation,
    NVICConfig,
)
from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.interrupt_model import InterruptModel

__all__ = [
    # Enums
    "ValidationSeverity",
    "RegisterAccess",
    "PeripheralState",
    # Models
    "Chip",
    "Peripheral",
    "Register",
    "Bitfield",
    "Interrupt",
    "Signal",
    "Pin",
    "PinFunction",
    "PinAssignment",
    "ClockAssignment",
    "InterruptAssignment",
    "RegisterWrite",
    "ResourceAllocation",
    "AllocationContext",
    "AllocationResult",
    "HardwareConstraint",
    "ValidationFinding",
    "ValidationResult",
    "Citation",
    "ClockDomain",
    "InterruptAllocation",
    "NVICConfig",
    # Graphs
    "PeripheralGraph",
    "RegisterSchemaDB",
    "PinMap",
    "ClockTree",
    "InterruptModel",
]
