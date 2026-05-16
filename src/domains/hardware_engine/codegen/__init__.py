"""Codegen module: hardware-constrained code generation."""

from src.domains.hardware_engine.codegen.hw_constrained_gen import HardwareConstrainedGenerator
from src.domains.hardware_engine.codegen.templates import RegisterAccessTemplates
from src.domains.hardware_engine.codegen.assertions import HardwareAssertions

__all__ = [
    "HardwareConstrainedGenerator",
    "RegisterAccessTemplates",
    "HardwareAssertions",
]
