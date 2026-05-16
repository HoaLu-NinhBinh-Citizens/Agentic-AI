"""Runtime events domain module."""

from dataclasses import dataclass


@dataclass
class RuntimeEvent:
    """Runtime event."""
    type: str
    timestamp: float
