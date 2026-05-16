"""Event model domain module."""

from dataclasses import dataclass
from typing import Any


@dataclass
class EventModel:
    """Event model."""
    id: str
    type: str
    data: dict[str, Any]
