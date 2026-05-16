"""Firmware events domain module."""

from dataclasses import dataclass


@dataclass
class FirmwareEvent:
    """Firmware event."""
    type: str
    address: int
