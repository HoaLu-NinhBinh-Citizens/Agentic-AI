"""Bootloader domain module."""

from typing import Any


class Bootloader:
    """Bootloader configuration."""
    
    def __init__(self):
        self._entry_point: int = 0x08000000
    
    def get_entry_point(self) -> int:
        """Get bootloader entry point."""
        return self._entry_point
