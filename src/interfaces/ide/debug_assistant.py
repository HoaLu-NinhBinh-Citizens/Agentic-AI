"""
IDE Debug Assistant (STUB)

Status: STUB - 2026-05-12
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BreakpointType(Enum):
    """Breakpoint type."""
    SOURCE = "source"
    HARDWARE = "hardware"
    WATCHPOINT = "watchpoint"


@dataclass
class Breakpoint:
    """Breakpoint."""
    id: str
    file: str
    line: int
    bp_type: BreakpointType = BreakpointType.SOURCE
    enabled: bool = True
    condition: Optional[str] = None


@dataclass
class WatchExpression:
    """Watch expression."""
    id: str
    expression: str
    enabled: bool = True
    last_value: Any = None


@dataclass
class DebugState:
    """Debug state."""
    running: bool = False
    paused: bool = False
    current_line: Optional[int] = None
    current_file: Optional[str] = None
    call_stack: List[str] = field(default_factory=list)


class DebugAssistant:
    """Debug assistant (stub)."""

    def __init__(self):
        self.breakpoints: Dict[str, Breakpoint] = {}
        self.watch_expressions: Dict[str, WatchExpression] = {}
        self.state = DebugState()

    def add_breakpoint(self, bp: Breakpoint) -> None:
        self.breakpoints[bp.id] = bp

    def remove_breakpoint(self, bp_id: str) -> None:
        self.breakpoints.pop(bp_id, None)

    def add_watch(self, watch: WatchExpression) -> None:
        self.watch_expressions[watch.id] = watch

    def remove_watch(self, watch_id: str) -> None:
        self.watch_expressions.pop(watch_id, None)

    def step(self) -> None:
        pass

    def continue_debug(self) -> None:
        pass

    def get_state(self) -> DebugState:
        return self.state


class WatchType(Enum):
    """Watch type."""
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"
