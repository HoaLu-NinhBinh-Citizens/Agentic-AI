"""Hardware events domain module."""

from dataclasses import dataclass


@dataclass
class HardwareEvent:
    """Hardware event."""
    peripheral: str
    action: str
