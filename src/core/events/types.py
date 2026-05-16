"""Event types module."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    """Base event class."""
    
    type: str
    data: dict[str, Any]


@dataclass
class TaskEvent(Event):
    """Task-related event."""
    type: str = "task"
