"""Validator module: deterministic hardware rules and validation."""

from src.domains.hardware_engine.validator.hw_validator import HardwareValidator
from src.domains.hardware_engine.validator.rules import HardwareRules
from src.domains.hardware_engine.validator.errors import (
    HardwareError,
    PinConflictError,
    ClockError,
    InterruptError,
    RegisterError,
    AllocationError,
    ValidationError,
)

__all__ = [
    "HardwareValidator",
    "HardwareRules",
    "HardwareError",
    "PinConflictError",
    "ClockError",
    "InterruptError",
    "RegisterError",
    "AllocationError",
    "ValidationError",
]
