"""Pinmux domain module."""

from typing import Any


class PinMux:
    """Pin multiplexing configuration."""
    
    def __init__(self):
        self._pins: dict[int, str] = {}
    
    def configure(self, pin: int, function: str) -> None:
        """Configure pin function."""
        self._pins[pin] = function
