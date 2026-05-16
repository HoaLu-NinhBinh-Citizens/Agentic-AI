"""Hardware domain module."""

from typing import Any


class HardwareChip:
    """Represents a hardware chip."""
    
    def __init__(self, name: str, arch: str):
        self.name = name
        self.arch = arch
        self.peripherals: list[Any] = []
