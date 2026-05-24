"""DAP (Debug Adapter Protocol) client tools for Agentic-AI CLI.

Provides:
- Breakpoint management
- Step execution (step in/out/over)
- Variable inspection
- Stack trace navigation
- Thread management
- Attach to processes
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DebugEventType(Enum):
    """Debug events."""
    STOPPED = "stopped"
    CONTINUED = "continued"
    THREAD = "thread"
    OUTPUT = "output"
    BREAKPOINT = "breakpoint"
    MODULE = "module"
    EXITED = "exited"


@dataclass
class StackFrame:
    """A stack frame."""
    id: int
    name: str
    source: str
    line: int
    column: int
    endLine: int | None = None
    endColumn: int | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> StackFrame:
        src = data.get("source", {})
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            source=src.get("path", "") or src.get("name", ""),
            line=data.get("line", 0),
            column=data.get("column", 0),
            endLine=data.get("endLine"),
            endColumn=data.get("endColumn"),
        )


@dataclass
class Variable:
    """A variable value."""
    name: str
    value: str
    type: str = ""
    variablesReference: int = 0
    namedVariables: int = 0
    indexedVariables: int = 0
    
    @classmethod
    def from_dict(cls, data: dict) -> Variable:
        return cls(
            name=data.get("name", ""),
            value=data.get("value", ""),
            type=data.get("type", ""),
            variablesReference=data.get("variablesReference", 0),
            namedVariables=data.get("namedVariables", 0),
            indexedVariables=data.get("indexedVariables", 0),
        )


@dataclass
class Thread:
    """A thread."""
    id: int
    name: str
    running: bool = True
    
    @classmethod
    def from_dict(cls, data: dict) -> Thread:
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "Thread"),
            running=data.get("state", {}).get("running", True),
        )


@dataclass
class Breakpoint:
    """A breakpoint."""
    id: int
    verified: bool
    line: int
    source: str = ""
    condition: str = ""
    hitCondition: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> Breakpoint:
        src = data.get("source", {})
        return cls(
            id=data.get("id", 0),
            verified=data.get("verified", False),
            line=data.get("line", 0),
            source=src.get("path", "") if src else "",
            condition=data.get("condition", ""),
            hitCondition=data.get("hitCondition", ""),
        )


@dataclass
class StoppedEvent:
    """A stopped event."""
    reason: str  # step, breakpoint, exception, etc.
    threadId: int
    allThreadsStopped: bool
    text: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> StoppedEvent:
        return cls(
            reason=data.get("reason", ""),
            threadId=data.get("threadId", 0),
            allThreadsStopped=data.get("allThreadsStopped", True),
            text=data.get("text", ""),
        )


@dataclass
class OutputEvent:
    """An output event."""
    category: str  # stdout, stderr, console
    output: str
    file: str = ""
    line: int = 0
    
    @classmethod
    def from_dict(cls, data: dict) -> OutputEvent:
        return cls(
            category=data.get("category", "stdout"),
            output=data.get("output", ""),
            file=data.get("source", {}).get("path", "") if data.get("source") else "",
            line=data.get("line", 0),
        )


class DAPClient:
    """DAP (Debug Adapter Protocol) client.
    
    Communicates with debug adapters over stdio.
    """
    
    def __init__(self, adapter_command: list[str]):
        self.adapter_command = adapter_command
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._initialized = False
        self._terminated = False
        self._capabilities: dict[str, Any] = {}
    
    async def start(self, debug_type: str = "node") -> None:
        """Start the debug adapter."""
        self._process = await asyncio.create_subprocess_exec(
            *self.adapter_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Read adapter info
        await self._read_until("Content-Length:")
    
    async def stop(self) -> None:
        """Stop the debug adapter."""
        self._terminated = True
        if self._process:
            try:
                await self._send_request("disconnect", {})
            except:
                pass
            self._process.terminate()
            await self._process.wait()
            self._process = None
    
    async def _read_message(self) -> dict | None:
        """Read a DAP message."""
        if not self._process:
            return None
        
        try:
            # Read header
            header = b""
            while header != b"\r\n":
                header = await self._process.stdout.read(1)
                if not header:
                    return None
            
            content_length = 0
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    return None
                line_str = line.decode().strip()
                if not line_str:
                    break
                if line_str.startswith("Content-Length:"):
                    content_length = int(line_str.split(":")[1].strip())
            
            # Read content
            if content_length > 0:
                content = await self._process.stdout.readexactly(content_length)
                return json.loads(content.decode())
        except Exception as e:
            logger.error(f"DAP read error: {e}")
            return None
    
    async def _read_until(self, prefix: str) -> str:
        """Read until a prefix is found."""
        if not self._process:
            return ""
        
        result = b""
        while prefix.encode() not in result:
            char = await self._process.stdout.read(1)
            if not char:
                break
            result += char
        
        return result.decode()
    
    async def _send_message(self, message: dict) -> None:
        """Send a DAP message."""
        if not self._process:
            return
        
        content = json.dumps(message).encode()
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        
        self._process.stdin.write(header + content)
        await self._process.stdin.drain()
    
    async def _send_request(self, command: str, args: dict) -> dict:
        """Send a request and wait for response."""
        if not self._process:
            raise RuntimeError("Debug adapter not started")
        
        self._request_id += 1
        
        message = {
            "seq": self._request_id,
            "type": "request",
            "command": command,
            "arguments": args,
        }
        
        await self._send_message(message)
        
        # Wait for response
        while True:
            response = await self._read_message()
            if response and response.get("type") == "response" and response.get("command") == command:
                if response.get("success"):
                    return response.get("body", {})
                else:
                    raise DAPError(response.get("message", "Unknown error"))
            
            # Queue events
            if response and response.get("type") == "event":
                await self._event_queue.put(response)
    
    async def _send_notification(self, command: str, args: dict) -> None:
        """Send a notification (no response expected)."""
        if not self._process:
            return
        
        message = {
            "seq": 0,
            "type": "request",
            "command": command,
            "arguments": args,
        }
        
        await self._send_message(message)
    
    async def initialize(self, adapter_id: str = "agentic-dap") -> dict:
        """Initialize the debug session."""
        result = await self._send_request("initialize", {
            "adapterID": adapter_id,
            "supportsConfigurationDoneRequest": True,
            "supportsFunctionBreakpoints": True,
            "supportsConditionalBreakpoints": True,
            "supportsHitConditionalBreakpoints": True,
            "supportsEvaluateForHovers": True,
            "supportsStepBack": False,
            "supportsSetVariable": True,
            "supportsRestartFrame": False,
            "supportsGotoTargetsRequest": False,
            "supportsStepInTargetsRequest": False,
            "supportsCompletionsRequest": True,
            "supportsModulesRequest": False,
            "supportsExceptionInfoRequest": True,
            "supportsExceptionBreakpoints": True,
            "supportsValueFormattingOptions": True,
        })
        
        self._capabilities = result
        self._initialized = True
        return result
    
    async def launch(self, program: str, args: list[str] | None = None, **kwargs) -> None:
        """Launch a debuggee."""
        launch_args = {
            "noDebug": kwargs.get("noDebug", False),
        }
        
        # Try to detect runtime
        if program.endswith(".py"):
            launch_args["program"] = program
            launch_args["console"] = "internalConsole"
            # Use debugpy or dap protocol
            if "python" in kwargs:
                launch_args["python"] = kwargs["python"]
        elif program.endswith(".js") or program.endswith(".ts"):
            launch_args["program"] = program
            launch_args["console"] = "integratedTerminal"
        else:
            launch_args["program"] = program
            if args:
                launch_args["args"] = args
        
        await self._send_notification("launch", launch_args)
    
    async def attach(self, host: str = "localhost", port: int = 9229, **kwargs) -> None:
        """Attach to a running process."""
        attach_args = {
            "host": host,
            "port": port,
        }
        attach_args.update(kwargs)
        
        await self._send_notification("attach", attach_args)
    
    async def set_breakpoints(
        self,
        source: str,
        lines: list[int],
        conditions: dict[int, str] | None = None,
    ) -> list[Breakpoint]:
        """Set breakpoints at lines."""
        breakpoints = []
        for line in lines:
            bp = {"line": line}
            if conditions and line in conditions:
                bp["condition"] = conditions[line]
            breakpoints.append(bp)
        
        result = await self._send_request("setBreakpoints", {
            "source": {"path": source},
            "breakpoints": breakpoints,
        })
        
        return [Breakpoint.from_dict(bp) for bp in result.get("breakpoints", [])]
    
    async def set_function_breakpoint(self, name: str, condition: str = "") -> Breakpoint:
        """Set a function breakpoint."""
        args = {"name": name}
        if condition:
            args["condition"] = condition
        
        result = await self._send_request("setFunctionBreakpoints", {
            "breakpoints": [args],
        })
        
        bps = result.get("breakpoints", [])
        return Breakpoint.from_dict(bps[0]) if bps else Breakpoint(id=0, verified=False, line=0)
    
    async def set_exception_breakpoints(
        self,
        exception_options: list[dict] | None = None,
    ) -> None:
        """Set exception breakpoints."""
        args = {}
        if exception_options:
            args["exceptionOptions"] = exception_options
        
        await self._send_request("setExceptionBreakpoints", args)
    
    async def configuration_done(self) -> None:
        """Signal configuration is done."""
        await self._send_request("configurationDone", {})
    
    async def threads(self) -> list[Thread]:
        """Get all threads."""
        result = await self._send_request("threads", {})
        return [Thread.from_dict(t) for t in result.get("threads", [])]
    
    async def stack_trace(self, thread_id: int = 0, levels: int = 20) -> list[StackFrame]:
        """Get stack trace for a thread."""
        result = await self._send_request("stackTrace", {
            "threadId": thread_id,
            "levels": levels,
        })
        
        return [StackFrame.from_dict(f) for f in result.get("stackFrames", [])]
    
    async def scopes(self, frame_id: int) -> list[dict]:
        """Get scopes for a frame."""
        result = await self._send_request("scopes", {
            "frameId": frame_id,
        })
        
        return result.get("scopes", [])
    
    async def variables(self, variables_reference: int = 0) -> list[Variable]:
        """Get variables for a scope."""
        result = await self._send_request("variables", {
            "variablesReference": variables_reference,
        })
        
        return [Variable.from_dict(v) for v in result.get("variables", [])]
    
    async def evaluate(self, expression: str, frame_id: int | None = None) -> Variable:
        """Evaluate an expression."""
        args = {"expression": expression}
        if frame_id is not None:
            args["frameId"] = frame_id
        
        result = await self._send_request("evaluate", args)
        
        return Variable(
            name=expression,
            value=result.get("result", ""),
            type=result.get("type", ""),
            variablesReference=result.get("variablesReference", 0),
        )
    
    async def continue_(self, thread_id: int = 0) -> None:
        """Continue execution."""
        await self._send_request("continue", {"threadId": thread_id})
    
    async def next(self, thread_id: int = 0) -> None:
        """Step over (next)."""
        await self._send_request("next", {"threadId": thread_id})
    
    async def step_in(self, thread_id: int = 0) -> None:
        """Step into."""
        await self._send_request("stepIn", {"threadId": thread_id})
    
    async def step_out(self, thread_id: int = 0) -> None:
        """Step out."""
        await self._send_request("stepOut", {"threadId": thread_id})
    
    async def pause(self, thread_id: int = 0) -> None:
        """Pause execution."""
        await self._send_request("pause", {"threadId": thread_id})
    
    async def disconnect(self) -> None:
        """Disconnect from debuggee."""
        await self._send_request("disconnect", {"terminateDebuggee": True})
    
    async def wait_for_event(self, event_type: str, timeout: float = 30.0) -> dict | None:
        """Wait for a specific event."""
        try:
            while True:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=timeout,
                )
                
                if event.get("event") == event_type:
                    return event.get("body")
        
        except asyncio.TimeoutError:
            return None
    
    async def wait_for_stopped(self, timeout: float = 30.0) -> StoppedEvent | None:
        """Wait for stopped event."""
        body = await self.wait_for_event("stopped", timeout)
        if body:
            return StoppedEvent.from_dict(body)
        return None


class DAPError(Exception):
    """DAP error."""
    pass


# DAP Adapter detection
DAP_ADAPTERS = {
    ".py": ["debugpy", "-m", "debugpy"],
    ".js": None,  # Uses built-in Node.js debugger
    ".ts": None,
    ".go": ["dlv", "dap"],
}


def detect_dap_adapter(path: Path) -> list[str] | None:
    """Detect available DAP adapter for a file."""
    import shutil
    
    ext = path.suffix.lower()
    command = DAP_ADAPTERS.get(ext)
    
    if command and command[0]:
        if shutil.which(command[0]):
            return command
    
    # Node.js has built-in adapter
    if ext in (".js", ".ts", ".jsx", ".tsx"):
        return ["node", "--inspect-brk"]
    
    return None
