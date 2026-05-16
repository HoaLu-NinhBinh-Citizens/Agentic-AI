"""
Autonomy State Module

Stub module for autonomy state management.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List


class AutonomyState(Enum):
    """Autonomy state."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StateSnapshot:
    """State snapshot."""
    state: AutonomyState
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)


__all__ = ["AutonomyState", "StateSnapshot"]
