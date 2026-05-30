"""Debugger Panel — Cursor-like debugging interface.

Provides a visual debugger with:
- Breakpoint management
- Variable inspection
- Call stack view
- Step controls (continue, step over, step into, step out)
- Watch expressions
- Debug console
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ─── Debugger state ──────────────────────────────────────────────────────────

class DebugState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    STEP_OVER = "step_over"
    STEP_INTO = "step_into"
    STEP_OUT = "step_out"
    STOPPING = "stopping"


class BreakpointType(Enum):
    LINE = "line"
    CONDITIONAL = "conditional"
    FUNCTION = "function"
    EXCEPTION = "exception"


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class Breakpoint:
    """A breakpoint."""
    id: str
    file_path: str
    line: int
    condition: str = ""
    enabled: bool = True
    hit_count: int = 0
    hit_condition: str = ""  # e.g., "== 5" or "> 10"
    log_message: str = ""

    def matches_line(self, file_path: str, line: int) -> bool:
        return self.file_path == file_path and self.line == line

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file_path,
            "line": self.line,
            "condition": self.condition,
            "enabled": self.enabled,
            "hitCount": self.hit_count,
            "hitCondition": self.hit_condition,
            "logMessage": self.log_message,
        }


@dataclass
class StackFrame:
    """A stack frame in the call stack."""
    id: str
    name: str
    file_path: str
    line: int
    column: int = 0
    locals: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "file": self.file_path,
            "line": self.line,
            "column": self.column,
            "locals": self.locals,
            "args": self.args,
        }


@dataclass
class Variable:
    """A variable in the debugger."""
    name: str
    value: Any
    type: str = ""
    reference: int = 0  # For objects/lists
    children: list[Variable] = field(default_factory=list)
    expanded: bool = False

    def __post_init__(self):
        if not self.type:
            self.type = type(self.value).__name__

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": repr(self.value)[:200],  # Truncate long values
            "type": self.type,
            "reference": self.reference,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class WatchExpression:
    """A watch expression."""
    id: str
    expression: str
    value: Any = None
    error: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "expression": self.expression,
            "value": repr(self.value)[:200] if self.error else repr(self.value),
            "error": self.error,
            "enabled": self.enabled,
        }


@dataclass
class DebugEvent:
    """A debug event (breakpoint hit, exception, etc.)."""
    type: str  # breakpoint, exception, step, pause, continue, exit
    frame: Optional[StackFrame] = None
    reason: str = ""
    timestamp: float = field(default_factory=time.time)
    exception_type: str = ""
    exception_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "frame": self.frame.to_dict() if self.frame else None,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "exceptionType": self.exception_type,
            "exceptionMessage": self.exception_message,
        }


# ─── Debugger Panel ───────────────────────────────────────────────────────────

class DebuggerPanel:
    """Cursor-like debugger panel with visual controls.

    Integrates with:
    - Debugpy for Python debugging
    - IDE bridge for sending updates
    - Terminal for debug console
    """

    def __init__(self):
        self._state = DebugState.STOPPED
        self._breakpoints: dict[str, Breakpoint] = {}
        self._frames: list[StackFrame] = []
        self._selected_frame: Optional[str] = None
        self._variables: list[Variable] = []
        self._watch: list[WatchExpression] = []
        self._callbacks: list[Callable[[dict], None]] = []
        self._debuggee: Optional[subprocess.Popen] = None
        self._debuggee_stdin: Optional[asyncio.StreamWriter] = None
        self._event_handlers: dict[str, list[Callable[[DebugEvent], None]]] = {}
        self._stats = {
            "breakpoints_created": 0,
            "breakpoints_hit": 0,
            "sessions_started": 0,
            "sessions_stopped": 0,
            "exceptions_caught": 0,
        }

    # ─── State ──────────────────────────────────────────────────────────────

    @property
    def state(self) -> DebugState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state in (DebugState.RUNNING, DebugState.STEP_OVER, DebugState.STEP_INTO, DebugState.STEP_OUT)

    # ─── Breakpoints ─────────────────────────────────────────────────────────

    def add_breakpoint(
        self,
        file_path: str,
        line: int,
        condition: str = "",
        breakpoint_type: BreakpointType = BreakpointType.LINE,
    ) -> Breakpoint:
        """Add a breakpoint."""
        bp_id = f"bp-{file_path}:{line}"
        bp = Breakpoint(
            id=bp_id,
            file_path=file_path,
            line=line,
            condition=condition,
        )
        self._breakpoints[bp_id] = bp
        self._stats["breakpoints_created"] += 1

        self._send_to_ide({
            "type": "debug/breakpoint_added",
            "breakpoint": bp.to_dict(),
        })
        return bp

    def remove_breakpoint(self, bp_id: str) -> bool:
        """Remove a breakpoint."""
        if bp_id in self._breakpoints:
            del self._breakpoints[bp_id]
            self._send_to_ide({
                "type": "debug/breakpoint_removed",
                "breakpointId": bp_id,
            })
            return True
        return False

    def toggle_breakpoint(self, bp_id: str) -> Optional[Breakpoint]:
        """Toggle breakpoint enabled state."""
        bp = self._breakpoints.get(bp_id)
        if bp:
            bp.enabled = not bp.enabled
            self._send_to_ide({
                "type": "debug/breakpoint_changed",
                "breakpoint": bp.to_dict(),
            })
            return bp
        return None

    def get_breakpoints(self, file_path: Optional[str] = None) -> list[Breakpoint]:
        """Get all breakpoints, optionally filtered by file."""
        if file_path:
            return [bp for bp in self._breakpoints.values() if bp.file_path == file_path]
        return list(self._breakpoints.values())

    # ─── Watch ───────────────────────────────────────────────────────────────

    def add_watch(self, expression: str) -> WatchExpression:
        """Add a watch expression."""
        watch = WatchExpression(id=f"watch-{len(self._watch)}", expression=expression)
        self._watch.append(watch)
        self._update_watch_value(watch)
        return watch

    def remove_watch(self, watch_id: str) -> bool:
        """Remove a watch expression."""
        self._watch = [w for w in self._watch if w.id != watch_id]
        return True

    def _update_watch_value(self, watch: WatchExpression) -> None:
        """Evaluate a watch expression."""
        if not watch.enabled or not self._frames:
            return

        frame = self._frames[0]
        try:
            # Simple evaluation in frame context
            local_vars = frame.locals.copy() if frame.locals else {}
            result = eval(watch.expression, {}, local_vars)
            watch.value = result
            watch.error = ""
        except Exception as exc:
            watch.value = None
            watch.error = str(exc)[:100]

    def _update_all_watches(self) -> None:
        """Update all watch expressions."""
        for watch in self._watch:
            self._update_watch_value(watch)

    # ─── Debug control ───────────────────────────────────────────────────────

    async def start(
        self,
        file_path: str,
        args: str = "",
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> bool:
        """Start debugging a file."""
        if self.is_running:
            await self.stop()

        self._state = DebugState.RUNNING
        self._stats["sessions_started"] += 1
        self._frames = []
        self._variables = []
        self._selected_frame = None

        # Notify IDE
        self._send_to_ide({
            "type": "debug/session_started",
            "file": file_path,
            "args": args,
        })

        # Start debuggee with debugpy
        try:
            import debugpy
            # Configure debugpy to listen
            debugpy.listen(("127.0.0.1", 5678))

            # Start the debuggee
            cmd = [sys.executable, file_path]
            if args:
                cmd.extend(args.split())

            self._debuggee = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env or None,
                cwd=cwd,
            )

            self._state = DebugState.PAUSED  # Will be paused at first breakpoint
            self._send_to_ide({
                "type": "debug/state_changed",
                "state": self._state.value,
            })

            return True

        except Exception as exc:
            self._state = DebugState.STOPPED
            self._send_to_ide({
                "type": "debug/error",
                "message": f"Failed to start debugger: {exc}",
            })
            return False

    async def stop(self) -> None:
        """Stop debugging."""
        if not self.is_running and self._state == DebugState.STOPPED:
            return

        self._state = DebugState.STOPPING

        if self._debuggee:
            self._debuggee.terminate()
            try:
                self._debuggee.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._debuggee.kill()
            self._debuggee = None

        self._state = DebugState.STOPPED
        self._frames = []
        self._variables = []
        self._selected_frame = None
        self._stats["sessions_stopped"] += 1

        self._send_to_ide({
            "type": "debug/session_stopped",
        })

    async def continue_debug(self) -> None:
        """Continue execution."""
        if self._state != DebugState.PAUSED:
            return
        self._state = DebugState.RUNNING
        self._send_to_ide({"type": "debug/state_changed", "state": "running"})

    async def pause(self) -> None:
        """Pause execution."""
        if not self.is_running:
            return
        self._state = DebugState.PAUSED
        self._send_to_ide({"type": "debug/state_changed", "state": "paused"})

    async def step_over(self) -> None:
        """Step over the current line."""
        if self._state != DebugState.PAUSED:
            return
        self._state = DebugState.STEP_OVER
        self._send_to_ide({"type": "debug/state_changed", "state": "step_over"})
        self._state = DebugState.PAUSED

    async def step_into(self) -> None:
        """Step into the current line."""
        if self._state != DebugState.PAUSED:
            return
        self._state = DebugState.STEP_INTO
        self._send_to_ide({"type": "debug/state_changed", "state": "step_into"})
        self._state = DebugState.PAUSED

    async def step_out(self) -> None:
        """Step out of the current function."""
        if self._state != DebugState.PAUSED:
            return
        self._state = DebugState.STEP_OUT
        self._send_to_ide({"type": "debug/state_changed", "state": "step_out"})
        self._state = DebugState.PAUSED

    # ─── Variable inspection ─────────────────────────────────────────────────

    def _update_variables(self, frame: StackFrame) -> None:
        """Update variables from the current frame."""
        self._variables = []

        # Add function arguments
        for name, value in frame.args.items():
            self._variables.append(Variable(name=name, value=value))

        # Add local variables
        for name, value in frame.locals.items():
            self._variables.append(Variable(name=name, value=value))

        # Add special variables
        if "__return__" in frame.locals:
            self._variables.insert(0, Variable(
                name="return",
                value=frame.locals["__return__"],
                type="return",
            ))

    def set_frame(self, frame_id: str) -> Optional[StackFrame]:
        """Set the selected stack frame."""
        frame = next((f for f in self._frames if f.id == frame_id), None)
        if frame:
            self._selected_frame = frame_id
            self._update_variables(frame)
            self._update_all_watches()
        return frame

    def evaluate(self, expression: str) -> Any:
        """Evaluate an expression in the current frame context."""
        if not self._frames:
            return None

        frame = self._frames[0]
        local_vars = frame.locals.copy() if frame.locals else {}
        try:
            return eval(expression, {}, local_vars)
        except Exception as exc:
            return f"Error: {exc}"

    # ─── Event handling ──────────────────────────────────────────────────────

    def on_debug_event(self, event_type: str, handler: Callable[[DebugEvent], None]) -> None:
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _emit_event(self, event: DebugEvent) -> None:
        """Emit a debug event."""
        handlers = self._event_handlers.get(event.type, [])
        handlers.extend(self._event_handlers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass

        self._send_to_ide({
            "type": "debug/event",
            "event": event.to_dict(),
        })

    # ─── IDE communication ───────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for IDE messages."""
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "breakpoints_total": len(self._breakpoints),
            "breakpoints_enabled": sum(1 for bp in self._breakpoints.values() if bp.enabled),
            "watch_count": len(self._watch),
            "frames_count": len(self._frames),
            "variables_count": len(self._variables),
        }

    # ─── Render ─────────────────────────────────────────────────────────────

    def render_panel(self) -> str:
        """Render the debugger panel as a string."""
        lines = [
            f"┌─ Debugger ───────────────────────────────┐",
            f"│ State: {self._state.value:<35} │",
            f"├─ Breakpoints ─────────────────────────────┤",
        ]

        if not self._breakpoints:
            lines.append("│ (no breakpoints)                         │")
        else:
            for bp in self._breakpoints.values():
                status = "●" if bp.enabled else "○"
                line = f"│ {status} {bp.file_path}:{bp.line:<30} │"
                if len(line) > 50:
                    line = f"│ {status} {bp.file_path}:{bp.line:<30}│"
                lines.append(line[:50].ljust(50) + "│")

        lines.append("├─ Call Stack ──────────────────────────────┤")
        if not self._frames:
            lines.append("│ (no frames)                              │")
        else:
            for i, frame in enumerate(self._frames[:10]):
                marker = "▶" if frame.id == self._selected_frame else " "
                name = f"{frame.name}(...)" if len(frame.name) > 20 else frame.name
                line = f"│{marker} #{i} {name:<25} @ {frame.line}    │"
                lines.append(line[:50].ljust(50) + "│")

        lines.append("├─ Variables ───────────────────────────────┤")
        if not self._variables:
            lines.append("│ (no variables)                           │")
        else:
            for var in self._variables[:10]:
                val = repr(var.value)[:20]
                line = f"│ {var.name:<15} = {val:<20}  │"
                lines.append(line[:50].ljust(50) + "│")

        lines.append("├─ Watch ────────────────────────────────────┤")
        if not self._watch:
            lines.append("│ (no watch expressions)                   │")
        else:
            for watch in self._watch[:5]:
                status = "●" if watch.enabled else "○"
                val = repr(watch.value)[:18] if not watch.error else f"Error"
                line = f"│ {status} {watch.expression:<15} = {val:<15}│"
                lines.append(line[:50].ljust(50) + "│")

        lines.append("└────────────────────────────────────────────┘")
        return "\n".join(lines)
