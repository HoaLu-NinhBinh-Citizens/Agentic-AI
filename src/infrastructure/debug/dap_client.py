"""DAP (Debug Adapter Protocol) client for Agentic-AI.

Provides debugging capabilities:
- Launch/attach to processes
- Set breakpoints
- Step through code
- Inspect variables
- Evaluate expressions
- Stack traces

Supports:
- Python (debugpy)
- Node.js (node --inspect)
- LLDB (lldb-dap)
- Chrome DevTools (pwa-chrome)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class DAPError(Exception):
    """DAP operation error."""
    pass


class DAPBreakpoint:
    """A breakpoint."""
    
    def __init__(
        self,
        source: str,
        line: int,
        condition: str | None = None,
        hit_condition: str | None = None,
    ):
        self.id = str(uuid4())
        self.source = source
        self.line = line
        self.condition = condition
        self.hit_condition = hit_condition
        self.verified = False


@dataclass
class DAPThread:
    """A debug thread."""
    id: int
    name: str


@dataclass
class DAPStackFrame:
    """A stack frame."""
    id: int
    name: str
    source: dict
    line: int
    column: int
    module: str | None = None


@dataclass
class DAPVariable:
    """A variable value."""
    name: str
    value: str
    type: str
    variables_reference: int = 0
    named_childs: list[DAPVariable] = field(default_factory=list)


@dataclass
class DAPStoppedEvent:
    """Thread stopped event."""
    thread_id: int
    reason: str  # breakpoint, step, exception, pause
    text: str = ""


class DAPConnection:
    """Connection to a debug adapter.
    
    Uses stdio protocol (JSON-RPC over stdin/stdout).
    """
    
    def __init__(self, adapter_command: list[str]):
        self.adapter_command = adapter_command
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list] = {}
        self._reader_task: asyncio.Task | None = None
        self._seq = 0
    
    async def start(self) -> None:
        """Start the debug adapter."""
        self._process = await asyncio.create_subprocess_exec(
            *self.adapter_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_messages())
    
    async def _read_messages(self) -> None:
        """Read messages from adapter."""
        assert self._process and self._process.stdout
        
        while True:
            try:
                # Read content
                content = await self._process.stdout.readline()
                if not content:
                    break
                
                # Parse
                message = json.loads(content.decode().strip())
                
                if "event" in message:
                    await self._handle_event(message)
                elif "response" in message:
                    await self._handle_response(message)
                    
            except Exception as e:
                if self._process.returncode is not None:
                    break
    
    async def _handle_event(self, message: dict) -> None:
        """Handle an event."""
        event_type = message.get("event", "")
        body = message.get("body", {})
        
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                asyncio.create_task(self._safe_handler(handler, body))
    
    async def _safe_handler(self, handler, body):
        """Safely call event handler."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(body)
            else:
                handler(body)
        except Exception:
            pass
    
    async def _handle_response(self, message: dict) -> None:
        """Handle a response."""
        req_id = message.get("request_seq", 0)
        if req_id in self._pending:
            future = self._pending.pop(req_id)
            if "body" in message:
                future.set_result(message["body"])
            elif "success" in message and not message["success"]:
                future.set_exception(DAPError(message.get("message", "Unknown error")))
    
    def on_event(self, event_type: str, handler) -> None:
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def send_request(self, command: str, args: dict | None = None) -> dict:
        """Send a request and wait for response."""
        req_id = self._seq
        self._seq += 1
        
        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        
        message = {
            "seq": req_id,
            "type": "request",
            "command": command,
            "arguments": args or {},
        }
        
        await self._send(message)
        return await future
    
    async def _send(self, message: dict) -> None:
        """Send a message."""
        if not self._process or not self._process.stdin:
            raise DAPError("Process not running")
        
        content = json.dumps(message) + "\n"
        self._process.stdin.write(content.encode())
        await self._process.stdin.drain()
    
    async def close(self) -> None:
        """Close the connection."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._process:
            self._process.terminate()
            await self._process.wait()


class DAPDebugger:
    """High-level debug operations."""
    
    def __init__(self, connection: DAPConnection):
        self.conn = connection
        self._threads: dict[int, DAPThread] = {}
        self._frames: dict[int, DAPStackFrame] = {}
        self._variables: dict[int, DAPVariable] = {}
        self._breakpoints: dict[str, list] = {}
        self._stopped_handler: asyncio.Future | None = None
    
    @classmethod
    async def launch_python(cls, script: Path, args: list[str] | None = None) -> DAPDebugger:
        """Launch Python debug session."""
        conn = DAPConnection(["python", "-m", "debugpy", "--connection-type", "stdio"])
        await conn.start()
        
        debugger = cls(conn)
        
        # Initialize
        await conn.send_request("initialize", {
            "adapterID": "agentic-ai",
            "supportsVariableType": True,
        })
        
        # Launch
        await conn.send_request("launch", {
            "type": "python",
            "request": "launch",
            "name": f"Debug {script.name}",
            "program": str(script),
            "args": args or [],
            "console": "integratedTerminal",
        })
        
        return debugger
    
    @classmethod
    async def attach_node(cls, port: int = 9229) -> DAPDebugger:
        """Attach to Node.js process."""
        conn = DAPConnection(["node", "inspect-brk", "--inspect-brk-port", str(port)])
        await conn.start()
        
        debugger = cls(conn)
        
        await conn.send_request("initialize", {"adapterID": "node"})
        
        await conn.send_request("attach", {
            "type": "node",
            "request": "attach",
            "port": port,
        })
        
        return debugger
    
    @classmethod
    async def launch_lldb(cls, binary: Path, args: list[str] | None = None) -> DAPDebugger:
        """Launch LLDB debug session."""
        conn = DAPConnection(["lldb-dap"])
        await conn.start()
        
        debugger = cls(conn)
        
        await conn.send_request("initialize", {"adapterID": "lldb"})
        
        await conn.send_request("launch", {
            "type": "lldb",
            "request": "launch",
            "name": binary.name,
            "program": str(binary),
            "args": args or [],
        })
        
        return debugger
    
    async def set_breakpoint(self, source: str, line: int) -> DAPBreakpoint:
        """Set a breakpoint."""
        bp = DAPBreakpoint(source, line)
        
        result = await self.conn.send_request("setBreakpoints", {
            "source": {"path": source},
            "breakpoints": [{"line": line}],
        })
        
        if result.get("breakpoints"):
            bp.verified = result["breakpoints"][0].get("verified", False)
        
        if source not in self._breakpoints:
            self._breakpoints[source] = []
        self._breakpoints[source].append(bp)
        
        return bp
    
    async def set_exception_breakpoints(self, exception_options: list[dict] | None = None) -> None:
        """Set exception breakpoints."""
        await self.conn.send_request("setExceptionBreakpoints", {
            "filters": [],
            "exceptionOptions": exception_options or [],
        })
    
    async def configuration_done(self) -> None:
        """Signal configuration is done."""
        await self.conn.send_request("configurationDone", {})
    
    async def threads(self) -> list[DAPThread]:
        """Get all threads."""
        result = await self.conn.send_request("threads", {})
        threads = result.get("threads", [])
        
        self._threads = {
            t["id"]: DAPThread(id=t["id"], name=t.get("name", "Unknown"))
            for t in threads
        }
        
        return list(self._threads.values())
    
    async def stack_trace(self, thread_id: int, levels: int = 20) -> list[DAPStackFrame]:
        """Get stack trace for a thread."""
        result = await self.conn.send_request("stackTrace", {
            "threadId": thread_id,
            "levels": levels,
        })
        
        frames = result.get("stackFrames", [])
        self._frames = {}
        
        for f in frames:
            frame = DAPStackFrame(
                id=f["id"],
                name=f.get("name", "Unknown"),
                source=f.get("source", {}),
                line=f.get("line", 0),
                column=f.get("column", 0),
            )
            self._frames[frame.id] = frame
        
        return list(self._frames.values())
    
    async def scopes(self, frame_id: int) -> list[dict]:
        """Get scopes for a frame."""
        result = await self.conn.send_request("scopes", {"frameId": frame_id})
        return result.get("scopes", [])
    
    async def variables(self, variables_reference: int) -> list[DAPVariable]:
        """Get variables in a scope."""
        result = await self.conn.send_request("variables", {
            "variablesReference": variables_reference,
        })
        
        vars = []
        for v in result.get("variables", []):
            var = DAPVariable(
                name=v.get("name", ""),
                value=v.get("value", ""),
                type=v.get("type", "unknown"),
                variables_reference=v.get("variablesReference", 0),
            )
            vars.append(var)
            self._variables[var.variables_reference] = var
        
        return vars
    
    async def evaluate(self, expression: str, frame_id: int | None = None) -> str:
        """Evaluate an expression."""
        args = {"expression": expression, "context": "repl"}
        if frame_id is not None:
            args["frameId"] = frame_id
        
        result = await self.conn.send_request("evaluate", args)
        return result.get("result", "")
    
    async def step_in(self, thread_id: int) -> None:
        """Step into."""
        await self.conn.send_request("stepIn", {"threadId": thread_id})
    
    async def step_out(self, thread_id: int) -> None:
        """Step out."""
        await self.conn.send_request("stepOut", {"threadId": thread_id})
    
    async def next(self, thread_id: int) -> None:
        """Step over."""
        await self.conn.send_request("next", {"threadId": thread_id})
    
    async def pause(self, thread_id: int) -> None:
        """Pause execution."""
        await self.conn.send_request("pause", {"threadId": thread_id})
    
    async def continue_(self, thread_id: int) -> None:
        """Continue execution."""
        await self.conn.send_request("continue", {"threadId": thread_id})
    
    async def disconnect(self) -> None:
        """Disconnect from debuggee."""
        await self.conn.send_request("disconnect", {"terminateDebuggee": True})
        await self.conn.close()


# Convenience functions

async def debug_python_script(script: Path, args: list[str] | None = None) -> DAPDebugger:
    """Start debugging a Python script."""
    return await DAPDebugger.launch_python(script, args)


async def debug_lldb_binary(binary: Path, args: list[str] | None = None) -> DAPDebugger:
    """Start debugging a binary with LLDB."""
    return await DAPDebugger.launch_lldb(binary, args)


class DAPSession:
    """A debugging session with event handling."""
    
    def __init__(self, debugger: DAPDebugger):
        self.debugger = debugger
        self._handlers: dict[str, list] = {}
    
    def on_stopped(self, handler) -> None:
        """Handle stopped event."""
        self.debugger.conn.on_event("stopped", handler)
    
    def on_breakpoint(self, handler) -> None:
        """Handle breakpoint hit."""
        self.debugger.conn.on_event("breakpoint", handler)
    
    def on_output(self, handler) -> None:
        """Handle output."""
        self.debugger.conn.on_event("output", handler)
    
    async def wait_stopped(self, timeout: float = 30.0) -> DAPStoppedEvent | None:
        """Wait for stopped event."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        def handler(body):
            if not future.done():
                event = DAPStoppedEvent(
                    thread_id=body.get("threadId", 0),
                    reason=body.get("reason", ""),
                    text=body.get("description", ""),
                )
                future.set_result(event)
        
        self.debugger.conn.on_event("stopped", handler)
        
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
    
    async def run_to_completion(self) -> None:
        """Run until completion or error."""
        threads = await self.debugger.threads()
        if threads:
            await self.debugger.continue_(threads[0].id)
